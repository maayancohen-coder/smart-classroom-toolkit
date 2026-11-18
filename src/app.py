"""Flask web layer: routes only. All logic lives in the attendance package."""
import hmac
import secrets
import sys
import time

from flask import (Flask, Response, abort, jsonify, make_response, redirect, render_template,
                   request, url_for)
from werkzeug.middleware.proxy_fix import ProxyFix

from attendance.config import Config
from attendance.counting import ClaudeVisionCounter, CountingError, CountResult, GeminiVisionCounter
from attendance.models import LocationReport, LocationSample
from attendance.report import to_csv, to_xlsx
from attendance.repository import DeviceRegistry, Roster, SessionStore
from attendance.service import AttendanceService, CheckInError
from attendance.tokens import TokenService
from attendance.slides import MAX_BYTES as MAX_SLIDES_BYTES, SlidesError, extract_terms, extract_text, hebrew_words
from attendance.terms import DEFAULT_TERMS
from attendance.handwriting import HandwritingError, build_transcriber
from attendance.homework import HomeworkStore, build_report, content_check
from attendance.transcript import Segment, assemble_lecturer_transcript, correct_transcript, parse_glossary

DEVICE_COOKIE = "did"
LECTURER_COOKIE = "lk"
ONE_YEAR = 60 * 60 * 24 * 365


def build_counter(config):
    """Pick the people counter from the configuration; None means manual entry only."""
    if config.GEMINI_API_KEY:
        return GeminiVisionCounter(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.COUNTER_TIMEOUT_SECONDS)
    if config.ANTHROPIC_API_KEY:
        return ClaudeVisionCounter(config.ANTHROPIC_API_KEY, config.COUNTER_MODEL, config.COUNTER_TIMEOUT_SECONDS)
    return None


def create_app(config: type[Config] = Config, roster: Roster | None = None) -> Flask:
    app = Flask(__name__)
    if config.TRUST_PROXY_HEADERS:
        # Behind a tunnel / reverse proxy: take the real client IP and scheme from X-Forwarded-*.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    service = AttendanceService(
        config,
        roster or Roster.from_csv(config.ROSTER_PATH),
        DeviceRegistry(),
        SessionStore(),
        TokenService(config.TOKEN_PERIOD_SECONDS, config.TOKEN_GRACE_PERIODS),
        counter=build_counter(config),
    )
    app.extensions["attendance_service"] = service

    # ---- helpers -----------------------------------------------------------------
    def is_lecturer() -> bool:
        supplied = request.cookies.get(LECTURER_COOKIE, "")
        return hmac.compare_digest(supplied, config.LECTURER_KEY)

    def require_lecturer():
        if not is_lecturer():
            abort(403)

    def get_session_or_404(session_id: str):
        session = service.store.get(session_id)
        if session is None:
            abort(404)
        return session

    def base_url() -> str:
        return config.PUBLIC_BASE_URL or request.host_url.rstrip("/")

    def device_id() -> tuple[str, bool]:
        existing = request.cookies.get(DEVICE_COOKIE)
        if existing and len(existing) >= 20:
            return existing, False
        return secrets.token_urlsafe(24), True

    def with_device_cookie(response, did: str, is_new: bool):
        if is_new:
            response.set_cookie(DEVICE_COOKIE, did, max_age=ONE_YEAR, httponly=True,
                                samesite="Lax", secure=request.is_secure)
        return response

    # ---- pages -------------------------------------------------------------------
    @app.get("/")
    def home():
        return render_template("home.html")

    @app.get("/lecturer")
    def lecturer_setup():
        key = request.args.get("key")
        if key is not None:
            if not hmac.compare_digest(key, config.LECTURER_KEY):
                abort(403)
            response = make_response(redirect(url_for("lecturer_setup")))
            response.set_cookie(LECTURER_COOKIE, key, httponly=True, samesite="Lax",
                                secure=request.is_secure)
            return response
        require_lecturer()
        return render_template("lecturer_setup.html", default_radius=config.DEFAULT_RADIUS_METERS)

    @app.get("/lecturer/<session_id>")
    def lecturer_live(session_id):
        require_lecturer()
        session = get_session_or_404(session_id)
        return render_template("lecturer_live.html", session=session,
                               period=config.TOKEN_PERIOD_SECONDS)

    @app.get("/lecturer/<session_id>/transcript")
    def lecturer_transcript(session_id):
        require_lecturer()
        session = get_session_or_404(session_id)
        return render_template("lecturer_transcript.html", session=session)

    @app.get("/c/<session_id>/<int:slot>/<signature>")
    def student_scan(session_id, slot, signature):
        did, is_new = device_id()
        try:
            ticket = service.scan(session_id, slot, signature, request.remote_addr or "")
        except CheckInError as exc:
            response = make_response(render_template("student_error.html", message=str(exc)), 400)
            return with_device_cookie(response, did, is_new)
        known = service.student_for_device(did)
        session = service.store.get(session_id)
        response = make_response(render_template(
            "student_checkin.html", nonce=ticket.nonce, course=session.course,
            known_name=known.name if known else None, needs_location=session.has_geofence,
            device_tag=did[-4:], device_new=is_new))
        response.headers["Cache-Control"] = "no-store"
        return with_device_cookie(response, did, is_new)

    # ---- student API -------------------------------------------------------------
    @app.post("/api/checkin")
    def api_checkin():
        data = request.get_json(silent=True) or {}
        did, is_new = device_id()
        samples = []
        for raw in (data.get("samples") or [])[:10]:
            try:
                samples.append(LocationSample(float(raw["lat"]), float(raw["lng"]),
                                              float(raw["accuracy"]), float(raw.get("ts", time.time()))))
            except (KeyError, TypeError, ValueError):
                continue
        location = LocationReport(samples=samples, denied=bool(data.get("denied")) or not samples)
        fingerprint = str(data.get("fp") or "")
        if not (8 <= len(fingerprint) <= 64 and fingerprint.isalnum()):
            fingerprint = ""
        try:
            client_now = float(data["client_now"]) if data.get("client_now") is not None else None
        except (TypeError, ValueError):
            client_now = None
        student_id = str(data.get("student_id") or "").strip() or None
        try:
            outcome = service.check_in(str(data.get("nonce") or ""), did, student_id, location,
                                       request.remote_addr or "", fingerprint, client_now,
                                       str(data.get("pin") or ""))
        except CheckInError as exc:
            return with_device_cookie(make_response(jsonify(ok=False, error=str(exc)), 400), did, is_new)
        # The student is told only that they were recorded - never their status, so a cheater
        # gets no feedback on which signal tripped.
        return with_device_cookie(
            jsonify(ok=True, name=outcome.student.name, duplicate=outcome.already_checked_in), did, is_new)

    # ---- lecturer API ------------------------------------------------------------
    @app.post("/api/session")
    def api_open_session():
        require_lecturer()
        data = request.get_json(silent=True) or {}

        def number(key):
            try:
                return float(data[key]) if data.get(key) not in (None, "") else None
            except (TypeError, ValueError):
                return None

        session = service.open_session(str(data.get("course") or ""), request.remote_addr or "",
                                       number("lat"), number("lng"), number("radius"))
        return jsonify(session_id=session.session_id, url=url_for("lecturer_live", session_id=session.session_id))

    @app.get("/api/session/<session_id>/qr")
    def api_qr(session_id):
        require_lecturer()
        session = get_session_or_404(session_id)
        path, expires_in = service.current_qr_path(session)
        return jsonify(url=base_url() + path, expires_in=round(expires_in, 2), closed=session.closed)

    @app.get("/api/session/<session_id>/report")
    def api_report(session_id):
        require_lecturer()
        session = get_session_or_404(session_id)
        rows = service.report_rows(session)
        counts = {"present": 0, "suspect": 0, "absent": 0}
        for row in rows:
            counts[row["status"]] += 1
        summary = service.head_count_summary(session)
        return jsonify(rows=rows, counts=counts, closed=session.closed,
                       rejected_scans=len(session.rejected),
                       headcount=summary.as_dict() if summary else None,
                       can_count_photo=service.counter is not None)

    @app.post("/api/session/<session_id>/headcount")
    def api_headcount(session_id):
        """Count people from an uploaded photo, or take a number typed by the lecturer."""
        require_lecturer()
        session = get_session_or_404(session_id)
        photo = request.files.get("photo")
        try:
            if photo is not None:
                image = photo.read(config.MAX_PHOTO_BYTES + 1)
                if not image or len(image) > config.MAX_PHOTO_BYTES:
                    return jsonify(ok=False, error="התמונה ריקה או גדולה מדי"), 400
                mime = photo.mimetype if photo.mimetype in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
                service.count_photo(session, image, mime)
            else:
                try:
                    value = int(request.form.get("count", (request.get_json(silent=True) or {}).get("count")))
                except (TypeError, ValueError):
                    return jsonify(ok=False, error="יש להעלות תמונה או להזין מספר"), 400
                if not 0 <= value <= 2000:
                    return jsonify(ok=False, error="מספר לא סביר"), 400
                service.record_head_count(session, CountResult(value, "manual"))
        except CountingError as exc:
            app.logger.warning("people counting failed: %s", exc)
            return jsonify(ok=False, error=str(exc)), 502
        except CheckInError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        summary = service.head_count_summary(session)
        return jsonify(ok=True, headcount=summary.as_dict())

    @app.post("/api/session/<session_id>/transcript")
    def api_transcript(session_id):
        """Correct a transcript with the lecturer's glossary and keep both versions with the session."""
        require_lecturer()
        session = get_session_or_404(session_id)
        data = request.get_json(silent=True) or {}
        glossary_text = str(data.get("glossary") or "")[:5_000]
        terms = parse_glossary(glossary_text)
        if data.get("defaults", True):
            terms = terms + [t for t in DEFAULT_TERMS if t.lower() not in {x.lower() for x in terms}]
        raw = str(data.get("raw") or "")[:200_000]
        dropped, questions = [], 0
        segments = []
        for item in (data.get("segments") or [])[:5000]:
            try:
                segments.append(Segment(str(item["text"])[:2000], float(item["level"]), float(item["t0"]), float(item["t1"])))
            except (KeyError, TypeError, ValueError):
                continue
        if segments:
            try:
                threshold = float(data.get("threshold"))
            except (TypeError, ValueError):
                threshold = 0.0
            assembled = assemble_lecturer_transcript(segments, threshold, terms, hebrew_words(session.slides_text))
            raw, dropped, questions = assembled.text, assembled.dropped, assembled.questions
        result = correct_transcript(raw, terms)
        session.transcript_raw, session.transcript_corrected = raw, result.text
        session.transcript_glossary = glossary_text
        return jsonify(ok=True, raw=raw, corrected=result.text, questions=questions, dropped=dropped,
                       missing=[m for m in result.missing if m.lower() in glossary_text.lower()],
                       fixes=[{"heard": f.heard, "term": f.term} for f in result.fixes])

    @app.post("/api/session/<session_id>/slides")
    def api_slides(session_id):
        """Read the text of the lecture slides; the file itself is not kept."""
        require_lecturer()
        session = get_session_or_404(session_id)
        upload = request.files.get("slides")
        if upload is None:
            return jsonify(ok=False, error="לא נבחר קובץ"), 400
        data = upload.read(MAX_SLIDES_BYTES + 1)
        if not data or len(data) > MAX_SLIDES_BYTES:
            return jsonify(ok=False, error="הקובץ ריק או גדול מדי (עד 15MB)"), 400
        try:
            text = extract_text(upload.filename or "", data)
        except SlidesError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        session.slides_name, session.slides_text = upload.filename or "", text[:300_000]
        terms = extract_terms(text)
        return jsonify(ok=True, name=session.slides_name, chars=len(text), terms=terms)

    @app.get("/api/session/<session_id>/transcript.txt")
    def api_transcript_download(session_id):
        require_lecturer()
        session = get_session_or_404(session_id)
        body = session.transcript_corrected or session.transcript_raw
        if not body:
            abort(404)
        return Response(body, mimetype="text/plain; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=transcript.txt"})

    @app.post("/api/session/<session_id>/close")
    def api_close(session_id):
        require_lecturer()
        service.close_session(get_session_or_404(session_id))
        return jsonify(ok=True)

    @app.post("/api/session/<session_id>/approve")
    def api_approve(session_id):
        """The lecturer accepts (or takes back the acceptance of) a suspect check-in."""
        require_lecturer()
        session = get_session_or_404(session_id)
        data = request.get_json(silent=True) or {}
        try:
            service.set_approval(session, str(data.get("student_id") or ""), bool(data.get("approved", True)))
        except CheckInError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True)

    @app.post("/api/session/<session_id>/reset_device")
    def api_reset_device(session_id):
        require_lecturer()
        get_session_or_404(session_id)
        student_id = str((request.get_json(silent=True) or {}).get("student_id") or "")
        service.reset_student(student_id)
        return jsonify(ok=True)

    @app.get("/api/session/<session_id>/report.<fmt>")
    def api_download(session_id, fmt):
        require_lecturer()
        session = get_session_or_404(session_id)
        rows = service.report_rows(session)
        head = service.head_count_summary(session)
        summary = head.as_dict() if head else None
        stamp = time.strftime("%Y-%m-%d_%H%M", time.localtime(session.started_at))
        if fmt == "xlsx":
            body, mime = to_xlsx(rows, session.course, summary), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif fmt == "csv":
            body, mime = to_csv(rows, summary), "text/csv; charset=utf-8"
        else:
            abort(404)
        return Response(body, mimetype=mime,
                        headers={"Content-Disposition": f"attachment; filename=attendance_{stamp}.{fmt}"})

    # ---- homework ----------------------------------------------------------------
    homework = HomeworkStore()
    app.extensions["homework_store"] = homework
    app.extensions["transcriber"] = build_transcriber(config)   # tests replace it with a fake
    MIN_TEXT_CHARS = 40
    IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}

    def read_upload(field: str) -> tuple[str, str]:
        """Text of an uploaded file (or pasted text). Scans and photos go to the handwriting reader."""
        upload = request.files.get(field)
        if upload is None or not upload.filename:
            return (request.form.get(field + "_text") or "").strip(), ""
        data = upload.read(MAX_SLIDES_BYTES + 1)
        if not data or len(data) > MAX_SLIDES_BYTES:
            raise ValueError("הקובץ ריק או גדול מדי (עד 15MB)")
        name = upload.filename.lower()
        image_mime = next((m for ext, m in IMAGE_TYPES.items() if name.endswith(ext)), None)
        text = ""
        if image_mime is None:
            try:
                text = extract_text(upload.filename, data).strip()
            except SlidesError as exc:
                raise ValueError(str(exc)) from exc
        if len(text) >= MIN_TEXT_CHARS:
            return text, upload.filename
        if image_mime is None and not name.endswith(".pdf"):
            return text, upload.filename
        transcriber = app.extensions["transcriber"]
        if transcriber is None:
            raise ValueError("הקובץ סרוק או בכתב יד ואין בו טקסט. כדי לקרוא אותו צריך להגדיר מפתח "
                             "GEMINI_API_KEY או ANTHROPIC_API_KEY בשרת. אפשר גם להדביק את הטקסט ידנית.")
        try:
            text = transcriber.transcribe(data, image_mime or "application/pdf")
        except HandwritingError as exc:
            raise ValueError(str(exc)) from exc
        if not text:
            raise ValueError("לא הצלחתי לקרוא טקסט מהקובץ")
        return text, upload.filename

    def assignment_or_404(assignment_id: str):
        assignment = homework.get(assignment_id)
        if assignment is None:
            abort(404)
        return assignment

    @app.get("/lecturer/homework")
    def lecturer_homework():
        require_lecturer()
        return render_template("lecturer_homework.html", reader=app.extensions["transcriber"].name if app.extensions["transcriber"] else "")

    @app.get("/api/homework/list")
    def api_homework_list():
        require_lecturer()
        return jsonify([{"id": a.assignment_id, "course": a.course, "title": a.title,
                         "submissions": len(a.submissions), "has_reference": bool(a.reference_text),
                         "has_materials": bool(a.materials_text), "has_assignment": bool(a.assignment_text)}
                        for a in homework.all()])

    def save_files(assignment) -> None:
        for field, attr in (("assignment", "assignment_text"), ("reference", "reference_text"),
                            ("materials", "materials_text")):
            text, _ = read_upload(field)
            if text:
                setattr(assignment, attr, text[:300_000])

    @app.post("/api/homework")
    def api_homework_create():
        require_lecturer()
        course, title = (request.form.get("course") or "").strip(), (request.form.get("title") or "").strip()
        if not course or not title:
            return jsonify(ok=False, error="חסר שם קורס או שם מטלה"), 400
        assignment = homework.create(course, title)
        try:
            save_files(assignment)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc), id=assignment.assignment_id), 400
        return jsonify(ok=True, id=assignment.assignment_id)

    @app.post("/api/homework/<assignment_id>/files")
    def api_homework_files(assignment_id):
        require_lecturer()
        assignment = assignment_or_404(assignment_id)
        try:
            save_files(assignment)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        return jsonify(ok=True)

    @app.get("/api/homework/<assignment_id>/report")
    def api_homework_report(assignment_id):
        require_lecturer()
        return jsonify(build_report(assignment_or_404(assignment_id)))

    @app.get("/api/homework/<assignment_id>/submission/<student_id>")
    def api_homework_submission(assignment_id, student_id):
        require_lecturer()
        submission = assignment_or_404(assignment_id).submissions.get(student_id)
        if submission is None:
            abort(404)
        return jsonify(name=submission.name, filename=submission.filename, text=submission.text)

    @app.get("/homework")
    def student_homework():
        return render_template("student_homework.html")

    @app.get("/api/homework/courses")
    def api_homework_courses():
        return jsonify([{"course": course, "assignments": [{"id": a.assignment_id, "title": a.title,
                                                            "has_materials": bool(a.materials_text)} for a in items]}
                        for course, items in homework.courses().items()])

    @app.post("/api/homework/<assignment_id>/check")
    def api_homework_check(assignment_id):
        """Self-check for a student before submitting: course content only, nothing is stored."""
        assignment = assignment_or_404(assignment_id)
        try:
            text, _ = read_upload("file")
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        if not text:
            return jsonify(ok=False, error="לא התקבל טקסט"), 400
        if not assignment.materials_text:
            return jsonify(ok=False, error="המרצה עוד לא העלה חומר קורס לבדיקה"), 400
        check = content_check(text, assignment.materials_text, assignment.assignment_text)
        return jsonify(ok=True, text=text, coverage=check["coverage"], missing=check["missing"],
                       outside=check["outside"], key_terms=check["key_terms"], used=check["used"])

    @app.post("/api/homework/<assignment_id>/submit")
    def api_homework_submit(assignment_id):
        assignment = assignment_or_404(assignment_id)
        student = service.roster.get((request.form.get("student_id") or "").strip())
        if student is None:
            return jsonify(ok=False, error="מספר הסטודנט לא נמצא ברשימת הקורס"), 400
        if config.REQUIRE_PIN:
            pin = (request.form.get("pin") or "").strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                return jsonify(ok=False, error="יש להזין קוד אישי (PIN) של 4-6 ספרות"), 400
            verdict = service.pins.check_or_set(student.student_id, pin)
            if verdict == service.pins.LOCKED:
                return jsonify(ok=False, error="יותר מדי ניסיונות. נסו שוב בעוד כמה דקות"), 429
            if verdict == service.pins.WRONG:
                return jsonify(ok=False, error="הקוד האישי שגוי"), 400
        try:
            text, filename = read_upload("file")
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        if len(text) < 5:
            return jsonify(ok=False, error="לא התקבל טקסט. צרפו קובץ או הדביקו את הפתרון"), 400
        replaced = homework.submit(assignment, student.student_id, student.name, filename or "text", text)
        return jsonify(ok=True, replaced=replaced, name=student.name, chars=len(text))

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("\n" + "=" * 60)
    print(f"  Lecturer link : http://localhost:{port}/lecturer?key={Config.LECTURER_KEY}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
