"""Flask web layer: routes only. All logic lives in the attendance package."""
import csv
import hmac
import io
import secrets
import sys
import time

from flask import (Flask, Response, abort, jsonify, make_response, redirect, render_template,
                   request, session as login, url_for)
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
from attendance.courses import Catalog
from attendance.notes import NoteBoard, TooFast
from attendance.summary import summarize
from attendance.handwriting import HandwritingError, build_transcriber
from attendance.homework import (MIN_PEERS_FOR_STUDENTS, HomeworkStore, Submission, build_report, build_common_mistakes_prompt, build_review_prompt,
                                 class_similarity, content_check)
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
    app.secret_key = hmac.new(config.LECTURER_KEY.encode(), b"login-cookie", "sha256").hexdigest()
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True, PERMANENT_SESSION_LIFETIME=60 * 60 * 12)
    catalog = Catalog.from_json(config.COURSES_PATH, service.roster)
    app.extensions["catalog"] = catalog
    notes, messages = NoteBoard(), NoteBoard()

    # ---- helpers -----------------------------------------------------------------
    def is_lecturer() -> bool:
        supplied = request.cookies.get(LECTURER_COOKIE, "")
        return hmac.compare_digest(supplied, config.LECTURER_KEY)

    def require_lecturer():
        if not is_lecturer():
            abort(403)

    def current_student():
        return service.roster.get(login.get("student_id", ""))

    def require_student():
        student = current_student()
        if student is None:
            abort(401)
        return student

    def lecturer_courses():
        lid = login.get("lecturer_id")
        return catalog.for_lecturer(lid) if lid else catalog.all()

    def course_or_404(course_id: str):
        course = catalog.get(course_id)
        if course is None:
            abort(404)
        return course

    def student_course_or_404(course_id: str):
        student = require_student()
        course = course_or_404(course_id)
        if not course.has_student(student.student_id):
            abort(403)
        return student, course

    def sessions_of(course):
        return [x for x in service.store.all() if x.course_id == course.course_id or (not x.course_id and x.course == course.name)]

    def active_session(course):
        return next((x for x in sessions_of(course) if not x.closed), None)

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
        return render_template("home.html", student=current_student(), lecturer=is_lecturer())

    @app.get("/login")
    def login_page():
        return render_template("login.html", lecturers=[{"id": l.lecturer_id, "name": l.name} for l in catalog.lecturers()],
                               pin_required=config.REQUIRE_PIN)

    @app.post("/api/login/student")
    def api_login_student():
        data = request.get_json(silent=True) or {}
        student = service.roster.get(str(data.get("student_id") or "").strip())
        if student is None:
            return jsonify(ok=False, error="Student number not found in the roster"), 400
        if config.REQUIRE_PIN:
            pin = str(data.get("pin") or "").strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                return jsonify(ok=False, error="Enter a personal PIN of 4-6 digits"), 400
            verdict = service.pins.check_or_set(student.student_id, pin)
            if verdict == service.pins.LOCKED:
                return jsonify(ok=False, error="Too many attempts. Try again in a few minutes"), 429
            if verdict == service.pins.WRONG:
                return jsonify(ok=False, error="Wrong PIN"), 400
        login.clear()
        login["student_id"] = student.student_id
        login.permanent = True
        return jsonify(ok=True, url="/my")

    @app.post("/api/login/lecturer")
    def api_login_lecturer():
        data = request.get_json(silent=True) or {}
        lecturer = catalog.lecturer(str(data.get("lecturer_id") or ""))
        if lecturer is None or not hmac.compare_digest(str(data.get("key") or "").strip(), config.LECTURER_KEY):
            return jsonify(ok=False, error="Wrong login details"), 400
        if config.REQUIRE_LECTURER_PASSWORD:
            password = str(data.get("password") or "")
            if not 4 <= len(password) <= 64:
                return jsonify(ok=False, error="Enter your personal password (4-64 characters)"), 400
            verdict = service.pins.check_or_set("lecturer:" + lecturer.lecturer_id, password)
            if verdict == service.pins.LOCKED:
                return jsonify(ok=False, error="Too many attempts. Try again in a few minutes"), 429
            if verdict == service.pins.WRONG:
                return jsonify(ok=False, error="Wrong login details"), 400
        login.clear()
        login["lecturer_id"] = lecturer.lecturer_id
        login.permanent = True
        response = jsonify(ok=True, url="/lecturer")
        response.set_cookie(LECTURER_COOKIE, config.LECTURER_KEY, httponly=True, samesite="Lax", secure=request.is_secure)
        return response

    @app.get("/lecturer/passwords.csv")
    def lecturer_passwords():
        """Lecturer only, for testing: who has chosen a password and what it is (when SHOW_PASSWORDS is on)."""
        require_lecturer()
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["role", "id", "name", "password_set", "password"])
        for lec in catalog.lecturers():
            key = "lecturer:" + lec.lecturer_id
            writer.writerow(["lecturer", lec.lecturer_id, lec.name, service.pins.has_pin(key), service.pins.chosen(key) or ""])
        for st in service.roster.all():
            writer.writerow(["student", st.student_id, st.name, service.pins.has_pin(st.student_id), service.pins.chosen(st.student_id) or ""])
        response = make_response("\ufeff" + out.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = "attachment; filename=passwords.csv"
        return response

    @app.get("/logout")
    def logout():
        login.clear()
        response = make_response(redirect(url_for("home")))
        response.delete_cookie(LECTURER_COOKIE)
        return response

    # ---- student: my courses, a course, a live lecture -------------------------------
    @app.get("/my")
    def student_courses():
        student = current_student()
        if student is None:
            return redirect(url_for("login_page"))
        cards = [{"id": c.course_id, "name": c.name, "live": active_session(c) is not None}
                 for c in catalog.for_student(student.student_id)]
        return render_template("student_courses.html", student=student, courses=cards,
                               live_count=sum(1 for c in cards if c["live"]))

    @app.get("/attend")
    def student_attend():
        student = current_student()
        if student is None:
            return redirect(url_for("login_page"))
        cards = [{"id": c.course_id, "name": c.name, "live": active_session(c) is not None}
                 for c in catalog.for_student(student.student_id)]
        return render_template("attend.html", student=student, courses=cards)

    @app.get("/scan")
    def student_scan_page():
        student = current_student()
        if student is None:
            return redirect(url_for("login_page"))
        course = catalog.get(request.args.get("course", ""))
        return render_template("scan.html", student=student, course=course)

    @app.get("/course/<course_id>")
    def student_course(course_id):
        if current_student() is None:
            return redirect(url_for("login_page"))
        student, course = student_course_or_404(course_id)
        live = active_session(course)
        assignments = []
        for a in homework.courses().get(course.name, []):
            mine = a.submissions.get(student.student_id)
            assignments.append({"id": a.assignment_id, "title": a.title, "submitted": mine is not None,
                                "filename": mine.filename if mine else "", "text": mine.text if mine else "",
                                "at": int(mine.submitted_at * 1000) if mine else 0})
        return render_template("student_course.html", student=student, course=course, live=live, assignments=assignments)

    @app.get("/api/course/<course_id>/summaries")
    def api_course_summaries(course_id):
        _, course = student_course_or_404(course_id)
        out = []
        for x in sessions_of(course):
            if x.summary_published and x.transcript_corrected:
                terms = [t.strip() for t in x.transcript_glossary.replace(",", "\n").splitlines() if t.strip()]
                out.append({"started_at": x.started_at, **summarize(x.transcript_corrected, terms)})
        return jsonify(out)

    @app.post("/api/course/<course_id>/message")
    def api_course_message(course_id):
        student, course = student_course_or_404(course_id)
        data = request.get_json(silent=True) or {}
        try:
            messages.add(course.course_id, student.student_id, student.name, str(data.get("text") or ""))
        except TooFast:
            return jsonify(ok=False, error="You can send one message every few seconds"), 429
        except ValueError:
            return jsonify(ok=False, error="The message is empty or the inbox is full"), 400
        return jsonify(ok=True)

    @app.get("/live/<session_id>")
    def student_live(session_id):
        student = require_student()
        session = get_session_or_404(session_id)
        course = catalog.get(session.course_id) if session.course_id else catalog.by_name(session.course)
        if session.closed or course is None or not course.has_student(student.student_id):
            abort(404)
        return render_template("student_live.html", session=session, course=course, student=student)

    @app.post("/api/session/<session_id>/note")
    def api_note(session_id):
        student = require_student()
        session = get_session_or_404(session_id)
        course = catalog.get(session.course_id) if session.course_id else catalog.by_name(session.course)
        if session.closed or course is None or not course.has_student(student.student_id):
            return jsonify(ok=False, error="The lecture is not active"), 400
        data = request.get_json(silent=True) or {}
        try:
            notes.add(session_id, student.student_id, student.name, str(data.get("text") or ""), bool(data.get("anonymous")))
        except TooFast:
            return jsonify(ok=False, error="You can send one note every few seconds"), 429
        except ValueError:
            return jsonify(ok=False, error="The note is empty or the board is full"), 400
        return jsonify(ok=True)

    @app.get("/api/session/<session_id>/my-notes")
    def api_my_notes(session_id):
        student = require_student()
        return jsonify([{"text": n.text} for n in notes.by_student(session_id, student.student_id)])

    # ---- lecturer: course page, notes, messages, summary ----------------------------
    @app.get("/lecturer/course/<course_id>")
    def lecturer_course(course_id):
        require_lecturer()
        course = course_or_404(course_id)
        return render_template("lecturer_course.html", course=course)

    @app.get("/api/course/<course_id>/inbox")
    def api_course_inbox(course_id):
        require_lecturer()
        course = course_or_404(course_id)
        return jsonify([{"name": m.name, "student_id": m.student_id, "text": m.text, "at": m.at}
                        for m in reversed(messages.list(course.course_id))])

    @app.get("/api/course/<course_id>/lectures")
    def api_course_lectures(course_id):
        require_lecturer()
        course = course_or_404(course_id)
        return jsonify([{"id": x.session_id, "started_at": x.started_at, "closed": x.closed,
                         "present": len(x.checkins), "has_transcript": bool(x.transcript_corrected),
                         "published": x.summary_published} for x in sessions_of(course)])

    @app.get("/api/session/<session_id>/notes")
    def api_session_notes(session_id):
        require_lecturer()
        get_session_or_404(session_id)
        after = request.args.get("after", type=int) or 0
        return jsonify([{"id": n.note_id, "name": n.name or "Anonymous", "text": n.text, "at": n.at}
                        for n in notes.list(session_id, after)])

    @app.get("/api/session/<session_id>/summary")
    def api_session_summary(session_id):
        require_lecturer()
        x = get_session_or_404(session_id)
        terms = [t.strip() for t in x.transcript_glossary.replace(",", "\n").splitlines() if t.strip()]
        return jsonify(published=x.summary_published, **summarize(x.transcript_corrected or x.transcript_raw, terms))

    @app.post("/api/session/<session_id>/summary/publish")
    def api_summary_publish(session_id):
        require_lecturer()
        x = get_session_or_404(session_id)
        x.summary_published = bool((request.get_json(silent=True) or {}).get("published"))
        return jsonify(ok=True, published=x.summary_published)

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
        return render_template("lecturer_setup.html", default_radius=config.DEFAULT_RADIUS_METERS,
                               courses=[{"id": c.course_id, "name": c.name} for c in lecturer_courses()])

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

        picked = catalog.get(str(data.get("course_id") or ""))
        session = service.open_session(picked.name if picked else str(data.get("course") or ""), request.remote_addr or "",
                                       number("lat"), number("lng"), number("radius"))
        session.course_id = picked.course_id if picked else ""
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
                    return jsonify(ok=False, error="The photo is empty or too large"), 400
                mime = photo.mimetype if photo.mimetype in ("image/jpeg", "image/png", "image/webp") else "image/jpeg"
                service.count_photo(session, image, mime)
            else:
                try:
                    value = int(request.form.get("count", (request.get_json(silent=True) or {}).get("count")))
                except (TypeError, ValueError):
                    return jsonify(ok=False, error="Upload a photo or enter a number"), 400
                if not 0 <= value <= 2000:
                    return jsonify(ok=False, error="Unreasonable number"), 400
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
            return jsonify(ok=False, error="No file chosen"), 400
        data = upload.read(MAX_SLIDES_BYTES + 1)
        if not data or len(data) > MAX_SLIDES_BYTES:
            return jsonify(ok=False, error="The file is empty or too large (up to 15MB)"), 400
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

    def read_upload(field: str, upload=None) -> tuple[str, str]:
        """Text of an uploaded file (or pasted text). Scans and photos go to the handwriting reader."""
        upload = upload or request.files.get(field)
        if upload is None or not upload.filename:
            return (request.form.get(field + "_text") or "").strip(), ""
        data = upload.read(MAX_SLIDES_BYTES + 1)
        if not data or len(data) > MAX_SLIDES_BYTES:
            raise ValueError("The file is empty or too large (up to 15MB)")
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
            raise ValueError("The file is a scan or handwriting with no text layer. To read it, a "
                             "GEMINI_API_KEY or ANTHROPIC_API_KEY must be set on the server. You can also paste the text by hand.")
        try:
            text = transcriber.transcribe(data, image_mime or "application/pdf")
        except HandwritingError as exc:
            raise ValueError(f"{exc} (the file had {len(text)} characters of selectable text, so it was sent to the reading service)") from exc
        if not text:
            raise ValueError("Could not read any text from the file")
        return text, upload.filename

    def assignment_or_404(assignment_id: str):
        assignment = homework.get(assignment_id)
        if assignment is None:
            abort(404)
        return assignment

    @app.get("/lecturer/homework")
    def lecturer_homework():
        require_lecturer()
        return render_template("lecturer_homework.html", courses=[c.name for c in lecturer_courses()], reader=app.extensions["transcriber"].name if app.extensions["transcriber"] else "")

    @app.get("/api/homework/list")
    def api_homework_list():
        require_lecturer()
        return jsonify([{"id": a.assignment_id, "course": a.course, "title": a.title,
                         "submissions": len(a.submissions), "has_reference": bool(a.reference_text),
                         "has_materials": bool(a.materials_text), "has_assignment": bool(a.assignment_text),
                         "allow_student_comparison": a.allow_student_comparison}
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
            return jsonify(ok=False, error="Course name or assignment title is missing"), 400
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

    llm_last: dict[str, float] = {}

    def roster_names() -> tuple:
        return tuple(s.name for s in service.roster.all())

    def run_llm(prompt: str):
        reader = app.extensions["transcriber"]
        if reader is None:
            return None, "No AI service is set up. Set GEMINI_API_KEY (or ANTHROPIC_API_KEY) on the server."
        try:
            return reader.complete(prompt), ""
        except HandwritingError as exc:
            return None, str(exc)

    @app.get("/api/ai-status")
    def api_ai_status():
        """Lecturer: a one-line live test of the AI service (key, model, answer time, exact error)."""
        require_lecturer()
        reader = app.extensions["transcriber"]
        if reader is None:
            return jsonify(ok=False, error="No key: GEMINI_API_KEY is not set on the server")
        started = time.time()
        try:
            answer = reader.complete("Reply with the single word OK.")
            return jsonify(ok=True, service=reader.name, model=getattr(reader, "model", ""), seconds=round(time.time() - started, 1), answer=answer[:40])
        except HandwritingError as exc:
            return jsonify(ok=False, service=reader.name, model=getattr(reader, "model", ""), seconds=round(time.time() - started, 1), error=str(exc))

    @app.post("/api/homework/<assignment_id>/review/<student_id>")
    def api_homework_review(assignment_id, student_id):
        """Lecturer: an LLM review of one submission, optionally compared with the classmates' work."""
        require_lecturer()
        assignment = assignment_or_404(assignment_id)
        submission = assignment.submissions.get(student_id)
        if submission is None:
            abort(404)
        data = request.get_json(silent=True) or {}
        mode = "solution" if data.get("mode") == "solution" else "course_only"
        peers = bool(data.get("peers"))
        text, error = run_llm(build_review_prompt(assignment, submission, mode, peers, roster_names()))
        if text is None:
            return jsonify(ok=False, error=error), 400
        return jsonify(ok=True, review=text, mode=mode, peers=peers)

    @app.post("/api/homework/<assignment_id>/llm-check")
    def api_homework_llm_check(assignment_id):
        """Student: an AI review of the answer before submitting. Course material only; no classmates' work,
        no lecturer solution; nothing is stored."""
        student = require_student()
        assignment = assignment_or_404(assignment_id)
        now = time.time()
        if now - llm_last.get(student.student_id, 0.0) < 30:
            return jsonify(ok=False, error="Please wait 30 seconds between AI reviews"), 429
        try:
            text, _ = read_upload("file")
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        if len(text) < 5:
            return jsonify(ok=False, error="No text received"), 400
        llm_last[student.student_id] = now
        own = Submission(student.student_id, student.name, "draft", text, now)
        return student_feedback(assignment, own)

    def student_feedback(assignment, own):
        """AI review for a student: course material only, plus an anonymous comparison with the class when allowed."""
        compare = assignment.allow_student_comparison
        others = [s for s in assignment.submissions.values() if s.student_id != own.student_id]
        use_peers = compare and len(others) >= MIN_PEERS_FOR_STUDENTS
        review, error = run_llm(build_review_prompt(assignment, own, "course_only", use_peers, roster_names(), "student"))
        if review is None:
            return jsonify(ok=False, error=error), 400
        similarity_info = class_similarity(assignment, own) if compare else {"enough": False, "others": len(others)}
        return jsonify(ok=True, review=review, compared=use_peers, similarity=similarity_info, comparison_allowed=compare)

    @app.post("/api/homework/<assignment_id>/my-feedback")
    def api_homework_my_feedback(assignment_id):
        """Feedback on the answer the logged-in student already submitted."""
        student = require_student()
        assignment = assignment_or_404(assignment_id)
        own = assignment.submissions.get(student.student_id)
        if own is None:
            return jsonify(ok=False, error="Submit your answer first"), 400
        now = time.time()
        if now - llm_last.get(student.student_id, 0.0) < 30:
            return jsonify(ok=False, error="Please wait 30 seconds between AI reviews"), 429
        llm_last[student.student_id] = now
        return student_feedback(assignment, own)

    @app.post("/api/homework/<assignment_id>/common-mistakes")
    def api_homework_common_mistakes(assignment_id):
        """Lecturer: the mistakes that repeat across all submissions of one assignment (AI, anonymous)."""
        require_lecturer()
        assignment = assignment_or_404(assignment_id)
        if len(assignment.submissions) < 2:
            return jsonify(ok=False, error="At least two submissions are needed to find repeating mistakes"), 400
        text, error = run_llm(build_common_mistakes_prompt(assignment, roster_names()))
        if text is None:
            return jsonify(ok=False, error=error), 400
        return jsonify(ok=True, review=text, count=len(assignment.submissions))

    @app.post("/api/homework/<assignment_id>/bulk")
    def api_homework_bulk(assignment_id):
        """Lecturer: import many submissions at once. Each file is named <student number>.<pdf|png|jpg|txt>."""
        require_lecturer()
        assignment = assignment_or_404(assignment_id)
        saved, problems = 0, []
        for upload in request.files.getlist("files"):
            stem = upload.filename.rsplit(".", 1)[0].strip()
            student = service.roster.get(stem)
            if student is None:
                problems.append(f"{upload.filename}: the file name must be a student number from the roster")
                continue
            try:
                text, filename = read_upload("files", upload)
            except ValueError as exc:
                problems.append(f"{upload.filename}: {exc}")
                continue
            if len(text) < 5:
                problems.append(f"{upload.filename}: no text found")
                continue
            homework.submit(assignment, student.student_id, student.name, filename, text)
            saved += 1
        return jsonify(ok=saved > 0, saved=saved, problems=problems)

    @app.post("/api/homework/<assignment_id>/settings")
    def api_homework_settings(assignment_id):
        require_lecturer()
        assignment = assignment_or_404(assignment_id)
        data = request.get_json(silent=True) or {}
        assignment.allow_student_comparison = bool(data.get("allow_student_comparison"))
        return jsonify(ok=True, allow_student_comparison=assignment.allow_student_comparison)

    @app.get("/homework")
    def student_homework():
        return render_template("student_homework.html", student_id=login.get("student_id", ""), pick=request.args.get("assignment", ""))

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
            return jsonify(ok=False, error="No text received"), 400
        if not assignment.materials_text:
            return jsonify(ok=False, error="The lecturer has not uploaded course material to check against yet"), 400
        check = content_check(text, assignment.materials_text, assignment.assignment_text)
        return jsonify(ok=True, text=text, coverage=check["coverage"], missing=check["missing"],
                       outside=check["outside"], key_terms=check["key_terms"], used=check["used"])

    @app.post("/api/homework/<assignment_id>/submit")
    def api_homework_submit(assignment_id):
        assignment = assignment_or_404(assignment_id)
        student = service.roster.get((request.form.get("student_id") or "").strip())
        if student is None:
            return jsonify(ok=False, error="Student number not found in the course roster"), 400
        if config.REQUIRE_PIN:
            pin = (request.form.get("pin") or "").strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                return jsonify(ok=False, error="Enter a personal PIN of 4-6 digits"), 400
            verdict = service.pins.check_or_set(student.student_id, pin)
            if verdict == service.pins.LOCKED:
                return jsonify(ok=False, error="Too many attempts. Try again in a few minutes"), 429
            if verdict == service.pins.WRONG:
                return jsonify(ok=False, error="Wrong PIN"), 400
        try:
            text, filename = read_upload("file")
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        if len(text) < 5:
            return jsonify(ok=False, error="No text received. Attach a file or paste the solution"), 400
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
