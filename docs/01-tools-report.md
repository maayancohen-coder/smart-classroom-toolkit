# Tools Report

Status: v2 (section 3.9 added for the AI features that were built)

This report lists the tools we considered for the attendance tool, what we tried on real devices, what worked, and what we dropped. Every result in section 3 comes from a real run (a laptop, an iPhone, and the hosted demo), not from documentation.

## 1. Selection criteria

- **Nothing to install for students.** It must work from the phone camera and the phone browser, on iPhone and Android.
- **Free**, because this is a course project.
- **Reachable from a phone on any network**, including the university Wi-Fi, without a hotspot.
- **Simple enough to explain in 10 minutes** (KISS), and testable without phones.

## 2. Tools chosen

| Need | Chosen | Alternatives considered | Why |
|---|---|---|---|
| Web server | Python 3.12 + Flask | Django, FastAPI, Node/Express | Small, readable, enough for a few routes. |
| Production server | gunicorn, 1 worker + 4 threads | Flask dev server | The dev server is not meant to be public. One worker is required because the state is in memory (see 3.5). |
| Rotating QR | Signed value (HMAC), new every 5 s, drawn in the browser | Static QR, one-time codes stored in a database | No database needed; a photo of the screen expires in seconds. |
| Location | Browser Geolocation API (`watchPosition`, high accuracy) | IP location, Wi-Fi name, Bluetooth beacons, a native app | Works in the browser with the student's permission and needs no hardware or app. |
| Phone identity | Random device cookie + personal PIN + browser profile hash | Biometrics / passkeys (WebAuthn), SMS codes, personal links by email | The user decided against biometrics. A PIN needs no extra service. Passkeys remain a possible future upgrade. |
| Storage | In memory behind `Repository` classes | SQLite, PostgreSQL | KISS for the demo; the classes can be swapped for a database. |
| Excel / CSV export | `openpyxl` and the standard `csv` module | Pandas | One small dependency. |
| Tests | `pytest` and the Flask test client | `unittest`, Selenium | 133 automated tests run in a few seconds, with one simulated phone per client. |
| Hosting for the demo | Render (free web service, branch `demo-deploy`) | Local server, Cloudflare Tunnel, localhost.run, ngrok | See 3.4 and 3.5. |
| People counting from a photo | Not adopted (adapter kept, manual count works) | Claude vision, Gemini vision | See 3.6. |

## 3. Experiments

### 3.1 Location accuracy

- **Goal:** know how accurate a phone and a laptop browser are, so we can choose a radius.
- **Method:** opened the hosted page, allowed location, and compared the reported distance to the classroom point.
- **Result:** the desktop browser was off by about 35 m; the iPhone reported distances of 75-76 m from the lecturer's point in the same building area. Indoor positioning is accurate to tens of meters, so it cannot tell two neighbouring rooms apart.
- **Decision:** the radius is a setting of the lecturer (default 120 m). The QR code and the class-group check cover the room level. The phone now collects readings for up to 12 s and stops once the accuracy is 20 m or better.

### 3.2 Location realism and cheating signals

- **Goal:** tell a real phone from fake GPS.
- **Result:** a real phone resting on a desk repeated identical coordinates. We first marked this "suspect", which was wrong, so "frozen location" became a **weak** signal. Two students reporting exactly the same coordinates is treated as a **strong** signal.
- **Decision:** a student is suspect after one strong failure or two weak ones (document 03, FR-12).

### 3.3 Rotating QR on a real phone

- **Method:** scanned the screen with the phone camera.
- **Result:** it scans reliably. One scan took 13.5 s from the code appearing to the page opening, and the system flagged it as a "slow scan, possible relay" (a weak signal), but still accepted it, because the code is valid for the current period plus two grace periods.
- **Decision:** period 5 s, grace 2, maximum accepted age 10 s for "fresh" scans.

### 3.4 Reaching the server from a phone

- **Goal:** the phone must open the page and get its location, which requires HTTPS.
- **Tried:** Cloudflare Tunnel and localhost.run from the laptop. Both **hung** on the home and university network and never gave a working address.
- **Result:** hosting on Render worked on the first attempt, with HTTPS included, and it works on the university Wi-Fi without a hotspot.
- **Decision:** Render for the demo.

### 3.5 Hosting limits found on Render (free plan)

- A deploy takes 40-50 s after each commit.
- The server **sleeps after inactivity** and wakes up in about 50 s; **all in-memory data is lost** when it sleeps or redeploys (sessions, check-ins, phone bindings, PINs).
- We therefore run one worker, open the page a few minutes before the demo, and export the sheet to Excel or CSV before closing.
- Lesson learned: an environment variable typed into the wrong field (name and value swapped) silently gave the server a random lecturer key and a 403 error. The code now ignores spaces around the key.

### 3.6 People counting from a photo (not adopted)

- **Goal:** compare the number of check-ins to the number of people in the room.
- **Tried:** a Gemini vision adapter (free tier). Results: the first model name had been retired (404); after fixing it, requests timed out or returned a generic error, even with a 110 s timeout. We did not manage to get a stable count.
- **Decision:** we dropped the photo feature for the demo. The adapter (`PeopleCounter`) and the manual head-count entry stay, so the gap logic is still tested and a counter can be plugged in later. It is shown to the user only when a counter is configured.
- **Not measured:** the accuracy of any model on real class photos. We make no claim about it.

### 3.7 Private window and phone identity

- **Goal:** one phone must not mark attendance for two people.
- **Test:** one iPhone, a normal tab for student A, a private tab for student B, same QR.
- **Result before the PIN:** a private tab gets a new device cookie, so the cookie alone does not catch it. The check-in of student B was recorded **suspect** with three reasons: frozen location, exactly the same coordinates as another student, and the same phone profile as another student. The lecturer sees it immediately.
- **Result with the personal PIN:** every check-in needs the student's PIN (4-6 digits, stored as a salted hash, locked for 5 minutes after 5 wrong tries). Marking a friend who already has a PIN fails without it, in a private window too. This is covered by automated scenarios and was also confirmed by hand on the iPhone: a wrong PIN in a private window was rejected.
- **Limits we accept:** the first person to enter a student's ID chooses the PIN (the lecturer can reset it); a student can give the PIN to a friend; two phones of the same model look alike, so the profile hash is only a weak signal.

### 3.8 Homework review with an LLM (small experiment)

- **Goal:** check what an LLM review of a real submission looks like, and what the homework service (UC14) must do before sending a file out.
- **Test:** one real submission of ours (28-page PDF, Computer Networks assignment 1, Hebrew with English terms). The text was extracted with `pypdf`, joined per page, and reviewed by the LLM with a fixed prompt: list strengths, mistakes, missing parts and suggestions, and quote the page for every claim. Only one condition was run: the assignment text was not available, so the review judged the work on its own.
- **Result, useful:** the review found concrete, checkable points. It recomputed the numbers in the work (the three filter percentages, the response time 19.951666 - 19.797716 = 0.153950 s, and 1368 + 325 = 1693 bytes) and all were correct. It also found real weaknesses: the client IP changes between captures (10.1.24.27, 10.9.1.164, 10.9.4.93) and the text does not say why; one answer (server-side processing as "better security") is weak, because the real reason is that server-side checks cannot be bypassed by the user; section 22 repeats section 20; and a leftover note to ourselves ("you can rely on the screenshots") remained inside the text of section 21.
- **Result, limits:** four pages (6, 7, 19, 21) are screenshots with no text, so the review could not check any claim that depends on them. The extracted text came out one word per line and needed cleaning first. The review could not tell whether the work answers what the lecturer asked, because the assignment text was missing.
- **Privacy finding (NFR-10):** the first page holds the authors' names and ID numbers. The service must remove names and 9-digit numbers before sending the text to an external model, and tell the student what is sent.
- **Decision:** the experiment led to building the homework tool (FR-40 to FR-47) with the redaction of names and ID numbers (see 3.9). The review is a suggestion; the lecturer or student decides.
- **Not measured:** how often the review is wrong, and the comparison of several submissions (FR-42). We make no claim about them.

### 3.9 AI features in the built system (real runs on the hosted site)

- **Tools chosen:** Gemini API (free tier) through one adapter, with a Claude implementation as an alternative; text from PDF with `pypdf`; scans, photos and handwriting read by the vision model; lecture audio transcribed by the same service.
- **What happened in real runs:**
  1. The default model `gemini-2.5-flash` answered 404 ("no longer available to new users"). We changed the default to `gemini-3.8-flash` and made the model a setting (`GEMINI_MODEL`).
  2. Requests then returned 503 ("high demand"). We added retries with waiting.
  3. Requests then ended in a timeout after 110 s, even for the simplest question ("reply OK"). A first guess blamed the thinking setting of the new model; the live test button showed the real cause: a 429 (quota exceeded) on `gemini-3.8-flash` for our free key, which our retries had hidden behind the waiting. A spent quota now fails at once with its reason.
  4. The list of models available to the key (a button on the homework page) showed many alternatives. `gemini-3.1-flash-lite` answered "OK" in 1.6 seconds. It is what the hosted site uses and now also the default in the code.
  5. The first AI review of a correct typed submission (linear algebra, determinant) reached the right conclusion but wrote its own re-calculation inside the answer under "Mistakes" ("wait, let me re-calculate ... no mistakes found") and did not name every correct question. The instructions now ask for conclusions only, "none found" when there is no mistake, and a list of the correct questions, and for the whole review to be written in Hebrew. The new wording was not yet compared with the old one on the same submission.
  6. An uploaded lecture recording was transcribed by hand on the hosted site and produced a transcript (one run; its length and accuracy were not recorded). The browser flow was also run on a 13-minute generated video, which was cut into three parts, with a fake service.
- **Decisions:** the model name and the key are settings; the lecturer has a live test of the AI service and a list of available models; every AI text is marked as a suggestion; names and ID numbers are removed before sending; a student's AI requests are limited to one per 30 seconds.
- **Known issue found in an earlier run:** the lecturer-voice calibration of the live transcript set the loudness threshold too high, so the lecturer's own speech was dropped. The calibration factor was lowered (from 0.5 to 0.35 of the lecturer's median level) and the threshold can still be set by hand with the slider; the new factor was not yet tested live.
- **Not measured:** the accuracy of the speech-to-text on a real lecture, the accuracy of handwriting reading, and how often an AI review is wrong. We make no claim about them. The free tier may use submitted data to improve the service; real student data needs a paid tier.

## 4. Tools not adopted, and why

| Tool | Reason |
|---|---|
| Biometrics / passkeys (WebAuthn) | Decided against, for privacy. Listed as a future upgrade. |
| Bluetooth beacons, Wi-Fi name checks | Need hardware or are not readable from a browser. |
| Native app | Contradicts "nothing to install". |
| Cloudflare Tunnel, localhost.run | Did not work on our network (3.4). |
| Vision API for people counting | Not stable in our attempts (3.6). |
| A database (SQLite, PostgreSQL) | The free hosting plan erases its disk on every deployment, so a local database would not keep the data; an outside free database was left as a future step (storage layer is already separate). |

## 5. Risks that remain

- Indoor location accuracy of tens of meters.
- The free server may sleep or restart during the demo; in-memory data is lost.
- The free AI service can fail, be overloaded or run out of quota; the pages show the reason and the lecturer can test it before the demo.
- A student can share a PIN; the system detects some cases (same coordinates, same phone profile) and does not claim to stop all of them.

## 6. References inside this repository

- Requirements: `03-srs.md` (FR-8 to FR-19, section 4.1).
- Tests and findings of the first real-device run: `07-testing-strategy.md`.
