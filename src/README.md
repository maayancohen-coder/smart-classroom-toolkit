# Course Hub (code)

The working demo for I2SE Exercise 2: attendance with a rotating QR code, location and a personal PIN; a course portal; lecture transcripts and summaries; homework review with AI. The documents are in `../docs/`.

The hosted demo runs on Render from the `demo-deploy` branch.

## Run it on your computer

1. Python 3.12 or newer. Install once: `pip install -r requirements.txt`
2. Start it from this folder: `python app.py`
3. The terminal prints the lecturer link, `http://localhost:8000/lecturer?key=...`. Open it in the browser.
4. Phones need **HTTPS** to share their location, so for a phone use the hosted site, or any HTTPS address that reaches your computer. Set `PUBLIC_BASE_URL` to that address so the QR code contains it.

Students and courses come from `data/students.csv` (`student_id,name`) and `data/courses.json`. Replace them with the lecturer's files.

## Settings (environment variables)

| Name | What it does |
|---|---|
| `LECTURER_KEY` | The key in the lecturer link. If empty, a random one is printed at start. |
| `GEMINI_API_KEY` | Turns on the AI features (reading scans, audio transcription, reviews, summaries). Without it they show a clear message. |
| `GEMINI_MODEL`, `GEMINI_THINKING` | The model (default `gemini-3.1-flash-lite`) and its thinking setting. The **Test the AI service** button on the homework page shows what works for your key. |
| `PUBLIC_BASE_URL` | The public address used inside the QR code. |
| `SHOW_PASSWORDS` | `1` lets the lecturer download the chosen passwords (for testing); set `0` for real use. |
| `FIREBASE_CREDENTIALS` | The Firebase service-account JSON. When set, the state is saved to Cloud Firestore and loaded on start. Empty means memory only. |
| `PASSWORDS_PATH` | A file that keeps passwords across restarts. Empty means memory only. |
| `ROSTER_PATH`, `COURSES_PATH` | Other roster and course files. |

Data (sessions, notes, assignments, submissions, transcripts, recordings, passwords) is kept in memory. With `FIREBASE_CREDENTIALS` it is also saved to Cloud Firestore after every change and loaded again when the server starts (`attendance/persistence.py`); without it, it is lost when the server restarts.

## Structure

| Path | Role |
|---|---|
| `app.py` | Routes (web layer only) |
| `attendance/tokens.py`, `checks.py`, `evaluator.py`, `service.py` | Rotating QR, the attendance checks (Strategy), the decision, and the use cases |
| `attendance/repository.py`, `models.py`, `courses.py`, `notes.py` | Storage classes (in memory), data classes, the course catalogue, live notes |
| `attendance/persistence.py` | Saves a snapshot of the stores to Cloud Firestore and loads it on start; large files are saved once, in parts |
| `attendance/transcript.py`, `slides.py`, `terms.py`, `summary.py` | Transcript correction from a glossary, terms from slides, summaries |
| `attendance/homework.py`, `handwriting.py` | Homework reports and prompts, and the AI adapter (Gemini or Claude) |
| `templates/` | The pages |
| `tests/` | The automated tests |

## Tests

`python -m pytest -q tests` (138 tests, a few seconds, no network needed)

## How a check-in is decided

- One **strong** failed check (far or missing location, fake location, device binding, same coordinates as another student) makes the check-in suspect.
- **Weak** checks (slow scan, frozen location, same phone profile, campus network) make it suspect only when two fail.
- The student never sees the status. The lecturer sees the reasons and decides.
