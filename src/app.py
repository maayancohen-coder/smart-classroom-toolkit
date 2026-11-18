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

    @app.post("/api/session/<session_id>/close")
    def api_close(session_id):
        require_lecturer()
        service.close_session(get_session_or_404(session_id))
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

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print("\n" + "=" * 60)
    print(f"  Lecturer link : http://localhost:{port}/lecturer?key={Config.LECTURER_KEY}")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=False)
