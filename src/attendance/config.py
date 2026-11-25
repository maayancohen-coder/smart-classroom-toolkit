"""Central configuration. Every value can be overridden with an environment variable."""
import os
import secrets


def _env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


class Config:
    # Rotating QR token: a new token every TOKEN_PERIOD_SECONDS.
    # A token stays valid for TOKEN_GRACE_PERIODS extra periods (scan + network delay).
    TOKEN_PERIOD_SECONDS = _env_int("TOKEN_PERIOD_SECONDS", 5)
    TOKEN_GRACE_PERIODS = _env_int("TOKEN_GRACE_PERIODS", 2)

    # A valid but "old" token is a weak hint of a relayed QR (photo / video call).
    MAX_TOKEN_AGE_SECONDS = _env_int("MAX_TOKEN_AGE_SECONDS", 10)

    # After a valid scan the student has this long to submit (first-time ID entry, location prompt).
    TICKET_TTL_SECONDS = _env_int("TICKET_TTL_SECONDS", 120)

    # Geofence around the lecturer's location when the session was opened.
    DEFAULT_RADIUS_METERS = _env_int("DEFAULT_RADIUS_METERS", 120)
    MAX_LOCATION_ACCURACY_METERS = _env_int("MAX_LOCATION_ACCURACY_METERS", 500)

    # Spoofing heuristics: indoor phone locations are never this precise.
    MIN_PLAUSIBLE_ACCURACY_METERS = float(os.environ.get("MIN_PLAUSIBLE_ACCURACY_METERS", 2))

    # Campus network: the lecturer's public IP is trusted automatically; extra CIDRs can be added.
    CAMPUS_NETWORKS = [c.strip() for c in os.environ.get("CAMPUS_NETWORKS", "").split(",") if c.strip()]

    ROSTER_PATH = os.environ.get("ROSTER_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "students.csv"))

    COURSES_PATH = os.environ.get("COURSES_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "courses.json"))

    # Only trust X-Forwarded-For / CF-Connecting-IP when running behind a tunnel or reverse proxy.
    TRUST_PROXY_HEADERS = os.environ.get("TRUST_PROXY_HEADERS", "1") == "1"

    # Optional fixed public URL (otherwise taken from the lecturer's request).
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

    # Protects the lecturer dashboard and API. Printed at startup if not set.
    LECTURER_KEY = (os.environ.get("LECTURER_KEY") or "").strip() or secrets.token_urlsafe(8)  # strip: a pasted space must not lock the lecturer out

    # People counting from the class photo (head-count gap).
    HEADCOUNT_TOLERANCE_PERCENT = float(os.environ.get("HEADCOUNT_TOLERANCE_PERCENT", 10))
    MAX_PHOTO_BYTES = _env_int("MAX_PHOTO_BYTES", 8_000_000)
    # Vision model used for counting. Without a key the lecturer can still type the count by hand.
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    COUNTER_MODEL = os.environ.get("COUNTER_MODEL", "claude-sonnet-5-5")
    # Free alternative: Google Gemini. Create a key in Google AI Studio and check the current model name there.
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
    GEMINI_THINKING = os.environ.get("GEMINI_THINKING", "low")      # "low" or "" (empty = do not send a thinking setting)
    # Counting a crowded photo can take a while with a "thinking" model.
    COUNTER_TIMEOUT_SECONDS = float(os.environ.get("COUNTER_TIMEOUT_SECONDS", 110))

    # Location quality and cheating signals.
    RAPID_REPEAT_SECONDS = _env_int("RAPID_REPEAT_SECONDS", 120)       # same phone profile + network, different student
    STALE_FIX_SECONDS = _env_int("STALE_FIX_SECONDS", 60)             # a cached GPS fix older than this is suspicious
    CLUSTER_MIN_POINTS = _env_int("CLUSTER_MIN_POINTS", 6)            # check-ins needed before the class group is trusted
    CLUSTER_MIN_RADIUS_METERS = float(os.environ.get("CLUSTER_MIN_RADIUS_METERS", 30))

    # Identity and location are mandatory.
    REQUIRE_PIN = True                  # personal PIN per student (ties a person to a check-in on any phone)
    BLOCK_WITHOUT_LOCATION = True       # no location permission -> no check-in at all (when the class has a geofence)
    FIREBASE_CREDENTIALS = os.environ.get("FIREBASE_CREDENTIALS", "")  # service-account JSON; empty = memory only
    PASSWORDS_PATH = os.environ.get("PASSWORDS_PATH", "")      # file that keeps chosen passwords across restarts (empty = memory only)
    SHOW_PASSWORDS = os.environ.get("SHOW_PASSWORDS", "1") == "1"   # demo/testing: the lecturer can download the chosen passwords
    REQUIRE_LECTURER_PASSWORD = True    # personal lecturer password, chosen on the first sign-in, in addition to the key
    PIN_MAX_ATTEMPTS = 5
    PIN_LOCK_SECONDS = 300
