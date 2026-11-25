# Testing Strategy

Status: v2 (133 automated tests)

This document explains how we check that the system does what the SRS requires. It is organized around the classes in document 06, because each class is tested on its own and then together with the others.

## 1. Goals

- Prove that every **must** requirement of the attendance tool is checked by at least one test.
- Find wrong decisions early: a student marked suspect by mistake, or a cheater marked present.
- Keep the tests fast and repeatable, so they can be run before every commit.
- Measure, and not assume, the quality of the AI parts (speech-to-text, people counting, LLM).

## 2. Test levels

| Level | What is tested | How |
|---|---|---|
| **Unit** | One class alone, with its neighbours replaced by test doubles | `pytest`, no network, no real clock |
| **Integration** | Several classes together, through the service layer | `pytest` with the real classes and fakes for external services |
| **API / scenario** | A full user scenario through the HTTP routes | `pytest` with the web framework's test client; one client per simulated phone |
| **Non-functional** | Security, privacy, performance | Targeted tests and a small load script |
| **AI quality** | Accuracy of speech-to-text, people counting and LLM output | Measured on real samples (see section 7) |
| **Real-device / acceptance** | The demo on real phones in the classroom | Manual checklist (section 8) |

## 3. Approach

- **Fakes instead of real services.** Every external service has a fake class (`FakePeopleCounter`, `FakeSpeechToText`, `FakeLLMClient`). A test chooses what the fake returns, so tests never depend on the internet, cost nothing, and are repeatable.
- **Controlled time.** The token service takes the current time as a parameter, so a test can create a token that is 3 seconds or 3 minutes old without waiting.
- **One check, one test file.** Each `AttendanceCheck` subclass is tested alone, which is possible because of the Strategy design.
- **Tests names say the scenario**, for example `test_second_student_on_same_phone_is_suspect`.
- **Test data:** the class roster (10 sample students), a fixed classroom location, "real-looking" location readings (imprecise and jittery), and "fake" readings (perfect and frozen).

## 4. Tests per class

### 4.1 Attendance: logic classes

| Class | What we test | Type |
|---|---|---|
| `TokenService` | A fresh token is valid. A token with a wrong signature is rejected. A token older than the grace window is rejected. A token from a future slot is rejected. The age of a valid token is computed correctly. Two sessions with different secrets reject each other's tokens. | Unit |
| `TicketStore` | A ticket can be consumed once; a second use fails. An expired ticket fails. An unknown ticket fails. | Unit |
| `DeviceRegistry` | A free phone and a free student bind. A phone already bound to another student cannot bind. A student already bound to another phone cannot bind. After `reset`, binding is possible again. Two simultaneous attempts to bind the same phone: only one succeeds. | Unit |
| `TokenFreshnessCheck` | Passes below the limit, fails above it, boundary exactly at the limit. | Unit |
| `DeviceBindingCheck` | Passes for an unknown phone with an unbound student. Passes for the correct pair. Fails for a phone bound to someone else. Fails for a student bound to another phone. | Unit |
| `GeofenceCheck` | Inside the radius passes. Outside fails. Accuracy is taken into account (a poor-accuracy reading near the edge passes). Location denied fails. No location configured passes. Reading too imprecise fails. | Unit |
| `LocationSpoofCheck` | Realistic jittery readings pass. Accuracy better than the plausible minimum fails. Three identical readings fail. No readings pass (left to the geofence). | Unit |
| `FrozenLocationCheck`, `StaleLocationCheck` | Three identical readings are only a weak failure. Readings older than 60 s are only a weak failure. Fresh, jittery readings pass. | Unit |
| `DuplicateCoordinatesCheck` | The same coordinates (6 decimals) as another student fail strongly; different students 5 m apart pass. | Unit |
| `SharedFingerprintCheck`, `RapidRepeatCheck` | The same phone profile for a different student is a weak failure; the same profile, the same network and under 120 s apart is a second weak failure; two phones of the same model on different networks stay present. | Unit |
| `PinStore` | The first PIN is accepted; the same PIN passes; a wrong PIN fails; five wrong PINs lock for 5 minutes, also for the right PIN; reset allows a new PIN. | Unit |
| `ClassCluster` | Fewer than 6 accurate check-ins give no cluster; a student far from 7 students sitting together is outside; a student inside the group is not. | Unit |
| `NetworkCheck` | An address inside the trusted network passes. Outside fails. No trusted network configured passes. | Unit |
| `AttendanceEvaluator` | Decision table in section 5. | Unit |
| `AttendanceService` | Full check-in with the real checks and a fake roster: present, suspect (each reason), duplicate check-in, unknown student, closed session, manual add after closing. | Integration |
| `Roster` | Loads a file with Hebrew names. Unknown ID returns nothing. A malformed file gives a clear error. | Unit |

### 4.2 Attendance: gap and export

| Class | What we test | Type |
|---|---|---|
| `HeadCountComparer` | Gap equals check-ins minus counted people. A gap inside the 10% tolerance is not flagged. A gap above is flagged and returns the check-ins with the most failed checks. Counted people higher than check-ins gives a negative gap and no flag. Zero check-ins. | Unit |
| `PeopleCounter` (with `FakePeopleCounter`) | The service calls the counter, deletes the photo, and keeps only the number. A counter failure leaves the session unchanged. | Integration |
| `ModelPeopleCounter` | Not in the demo: the free vision service gave no stable result (tools report, 3.6). | AI quality |
| `CsvExporter`, `XlsxExporter` | The file opens, has the header, one row per student, Hebrew text is intact, suspect rows show their reasons. | Unit |

### 4.3 Polls and comments

| Class | What we test | Type |
|---|---|---|
| `PollService` | A poll needs at least two options. One answer per student; a second answer is rejected. No answers after the poll is closed. Results count correctly. | Unit |
| `CommentService` | A named comment stores the author. An anonymous comment stores **no** author. A comment after the lecture is stored with the session. | Unit |
| `QuestionSuggester` (with `FakeLLMClient`) | The slide text is passed to the LLM, the suggestion is returned and can be edited. An LLM failure does not block creating a poll by hand. | Unit |

### 4.4 AI services (as designed; section 4.5 says what was built and tested)

| Class | What we test | Type |
|---|---|---|
| `AudioExtractor` | A video file gives an audio file. An audio file passes through. A corrupt file gives a clear error. | Unit |
| `TranscriptCorrector` (with `FakeLLMClient`) | The glossary from the slides is sent with the text. The corrected text replaces the raw text. | Unit |
| `Summarizer` (with `FakeLLMClient`) | The summary is requested from the corrected text. An empty transcript is handled. | Unit |
| `JobRunner` | A job moves from pending to running to done. A failing step gives status failed with the reason. A failed job can be retried. Several jobs do not block each other. | Unit and integration |
| `MediaService` | End to end with fakes: upload, job, transcript and summary stored. An external failure leaves the rest of the system working. | Integration |
| `HomeworkService` | A review is visible only to the uploader. A student cannot get another student's submission. A lecturer comparison covers only the chosen assignment. | Integration |
| `RemoteSpeechToText`, `RemoteLLMClient` | A real call on one sample, to check the connection and the format of the answer. | Manual, once |

### 4.5 AI services as built

| Part | What we test | Type |
|---|---|---|
| `Transcriber` adapter (Gemini) | The request carries the file or audio and the right instruction; an overloaded service is retried; a spent quota fails at once with its reason; the error text names the cause | Unit with a faked network call |
| Homework review | The prompt contains the assignment, the materials or the lecturer's solution; names and ID numbers are removed; the submitted text is inside data markers; the answer is requested in Hebrew; classmates are anonymous | Unit with a fake reader |
| Student feedback | Needs at least 3 other submissions for a class comparison, respects the lecturer's switch, never quotes classmates, at most one request per 30 seconds | Integration through the routes |
| Common mistakes | Needs two submissions, lecturer only, answers are numbered and anonymous | Integration |
| Recording | Audio parts are accepted from the lecturer only, errors reach the page, a recording is kept only if the lecturer chooses, and students can play it only after publishing | Integration |
| Transcript repair and summary | Prompts contain the glossary and the data markers; only the lecturer can call them; the summary needs a transcript | Integration |
| Browser flow of a recording | A 13-minute video was loaded in Chromium, cut into three parts and transcribed with a fake service | Manual, scripted once |

Not tested automatically and not measured: the accuracy of the speech-to-text on a real lecture, the accuracy of handwriting reading and the quality of the AI reviews. The first real runs are in the tools report; no accuracy figure is claimed.

## 5. Decision table for the evaluator

The evaluator is the heart of the system, so every combination of strong and weak failures is tested.

| Strong checks failed | Weak checks failed | Expected status |
|---|---|---|
| 0 | 0 | PRESENT |
| 0 | 1 | PRESENT |
| 0 | 2 | SUSPECT |
| 1 | 0 | SUSPECT |
| 1 | 1 | SUSPECT |
| 2 or more | any | SUSPECT |

The reasons of all failed checks must appear in the result, also when the status is PRESENT (for example one weak failure).

## 6. Scenario tests (through the web routes)

Each scenario uses a separate simulated phone.

| Scenario | Expected result | Requirements |
|---|---|---|
| Honest student scans and checks in | PRESENT | FR-8, FR-12, FR-13 |
| Student far from the classroom | SUSPECT, reason mentions distance | FR-12 |
| Location denied | Check-in refused, nothing recorded | FR-11a, NFR-19 |
| Unrealistically perfect location (accuracy under 2 m) | SUSPECT | FR-12 |
| Identical coordinates in every reading, realistic accuracy | PRESENT with a note (weak signal only) | FR-12 |
| One phone, two students | The second is SUSPECT | FR-17 |
| Same student, new phone | With the correct PIN: PRESENT. Without PIN verification (PIN switched off): SUSPECT; after lecturer reset it is PRESENT | FR-17, FR-18 |
| No PIN given | Refused | FR-9a |
| Wrong PIN | Refused; after 5 wrong PINs even the right PIN is refused for 5 minutes | FR-9a, FR-9b |
| Private window marking a friend, with the friend's wrong PIN | Refused | FR-9a |
| Lecturer resets a student | The PIN can be chosen again | FR-18 |
| Lecturer approves a suspect | PRESENT, reasons kept and marked "approved by lecturer"; the class-group check does not flag it again | FR-25a |
| Lecturer undoes an approval | SUSPECT again | FR-25a |
| Approving a student who did not check in, or approving as a non-lecturer | Refused | FR-25a, NFR-3 |
| Exactly the same coordinates as another student | SUSPECT, reason "same coordinates" | FR-12 |
| Cached (old) location reading | PRESENT with a note (weak signal only) | FR-12 |
| Same phone profile as another student | SUSPECT together with another weak signal | FR-12 |
| Student inside the radius but away from the class group (7 students together) | SUSPECT, reason "outside the class group" | FR-12a |
| Token older than the window | Refused | FR-7 |
| Forged token | Refused | NFR-1 |
| Same ticket used twice | Second use refused | NFR-2 |
| Unknown student ID | Refused, can retry | FR-10 |
| Same student twice | One entry, second confirmed | FR-16 |
| Student tries to check in after closing | Refused | FR-3 |
| Lecturer adds a student after closing | Entry marked as added manually | FR-28 |
| Student response never shows the status | Response has no status | FR-15 |
| Head count (typed) with a gap above 10% | Gap reported, suspect check-ins highlighted | FR-23, FR-24, FR-24a |
| Comment sent anonymously | No author in the lecturer view | FR-33 |

133 automated tests are written and passing in the demo code:

| File | Tests | Covers |
|---|---|---|
| `test_flow.py` | 35 | Attendance scenarios through the web routes (rotating code, location, PIN, device checks, evaluator, export, lecturer functions) |
| `test_headcount.py` | 19 | Head count, gap and tolerance logic |
| `test_slides.py` | 9 | Text and terms from slides (PPTX, PDF, text) and refusal of bad files |
| `test_transcript.py` | 20 | Glossary correction and its limits, undoing a correction, lecturer-voice filter, student questions, download |
| `test_portal.py` | 12 | Sign-in, course lists, live notes, messages, published summaries, the student's own submission, a past lecture with a transcript, the recording played only after publishing |
| `test_homework.py` | 26 | Assignments, submissions, report, similarity, course-content check, scans through the reader, AI review, redaction, retry and quota handling, student feedback and class comparison, common mistakes, bulk import, opening the uploaded file, AI status, Hebrew prompts |
| `test_passwords.py` | 5 | PIN and password chosen once, lecturer download, persistence in a file, hiding the values |
| `test_recording.py` | 7 | Audio parts, errors, text repair, AI summary, saving, lecturer-only access |

All external services are replaced by fakes in these tests, so they check our code and the shape of the requests, not the quality of the AI answers.

## 7. Non-functional and AI-quality tests

### 7.1 Security

- A request to any lecturer route without authentication is refused (NFR-3).
- A forged, modified or replayed token or ticket is refused (NFR-1, NFR-2).
- Repeated wrong PINs from one client are locked out (FR-9b). General rate limiting (NFR-6) is future work.
- The device cookie is not readable by page scripts (NFR-5).

### 7.2 Privacy

- After counting, the class photo no longer exists on the server (NFR-7).
- An anonymous comment contains no author in the database or the view (FR-33).
- No route returns another student's homework to a student (FR-43).

### 7.3 Performance

- A script sends 200 check-ins within a minute. Pass criterion: 95% answered within 2 seconds (NFR-12).
- The sheet is refreshed at least every 3 seconds with 200 check-ins (NFR-13).

### 7.4 AI quality (measured, not assumed)

| What | Method | Result goes to |
|---|---|---|
| People counting | Attempted with a free vision service; no stable result, so no accuracy is claimed. The feature is not in the demo (tools report, 3.6). | Tools report |
| Speech-to-text | Transcribe 3 to 5 minutes of a real lecture. Correct it by hand. Compute the word error rate (WER) for each candidate engine. | Tools report |
| Term correction | Count technical terms that are wrong before and after the LLM correction with the slides as glossary. | Tools report |
| LLM summary and homework review | There is no single right answer, so use a checklist: the summary covers the main topics of the lecture, invents nothing that is not in the transcript, and the review points at real parts of the homework. Two people mark each item. | Tools report |

## 8. Real-device and demo checklist

| Check | Pass |
|---|---|
| iPhone (Safari): scan, location prompt, check-in | |
| Android (Chrome): scan, location prompt, check-in | |
| Location permission denied | Check-in refused with a clear message, no crash |
| Phone on mobile data and on campus Wi-Fi | Both work |
| Hebrew text and right-to-left layout on the phone | Correct |
| QR visible on the projector from the back of the room | Readable |
| 10 or more students check in at once | The sheet updates |
| Photo of the real classroom gives a count | Not in the demo |
| Secure link opens on a phone that is not on the lecturer's network | Works |

### Findings from the first real-device run (iPhone, hosted demo)

| Finding | Cause | Action |
|---|---|---|
| A real student was marked SUSPECT with "location frozen across readings". | A phone resting on a desk can report the same coordinates in every reading. | The check was made a **weak** signal; one weak failure alone no longer makes a student suspect. A scenario test covers it. |
| Marking two students from one phone was not flagged at first. | The device identifier was new on each scan (hosted server had restarted, which clears memory). After a stable run the phone was recognised ("known device") and no second ID could be entered. | Keep the diagnostic device tag in the demo. Document the private-window limitation (SRS 4.1). |
| The free hosting server sleeps after inactivity and forgets all data. | In-memory storage by design for the demo. | Open the page a few minutes before the demo; export the sheet to Excel or CSV before closing. |
| Desktop browser location is only accurate to tens of meters (about 35 m error). | Indoor positioning. | Use a radius of 500 m in the demo; the QR and the class-group check cover the room-level check. |
| A private window on the same phone marking a second student was recorded as present before the new checks. | The cookie changes in a private window. | Added checks for the same phone profile, the same coordinates and the class group, and a personal PIN. A private tab marking a second student is now recorded as suspect with its reasons, and a wrong PIN in a private tab is refused (confirmed by hand on an iPhone). |
| A hosting environment variable with its name and value swapped gave a 403 on the lecturer page. | The server used a random lecturer key. | Spaces around the key are ignored; checking the variable is part of the demo preparation. |

A dry run of the 10-minute demo is performed once the day before.

## 9. Entry and exit criteria

- **Entry:** the class under test exists and its unit tests are written first or together with it.
- **Exit for the demo:** all unit and scenario tests pass; the real-device checklist is complete; known failures are listed with a workaround.
- **Known risks:** indoor location accuracy, the back rows in the people count, projector brightness and QR readability, and the availability of external services during the demo (the fakes allow an offline fallback).

## 10. Traceability

| Requirement group | Tested by |
|---|---|
| FR-1 to FR-7 | `TokenService`, `AttendanceService` and scenario tests |
| FR-8 to FR-19 | Check tests, evaluator decision table, scenarios |
| FR-9a, FR-9b, FR-11a, FR-12a | Scenario tests (PIN, location refusal, class group), `PinStore` and `ClassCluster` tests |
| FR-20 to FR-24a | `HeadCountComparer`, `PeopleCounter` with a fake; the photo measurement was not done |
| FR-25 to FR-28 | Exporter tests, manual add scenario |
| FR-29 to FR-33 | `PollService`, `CommentService` |
| FR-34 to FR-39 | `test_transcript.py`, `test_slides.py`, `test_recording.py`; the WER measurement was not done |
| FR-40 to FR-47 | `test_homework.py` |
| FR-48 to FR-54 | `test_portal.py`, `test_passwords.py`, `test_flow.py` |
| NFR-1 to NFR-6 | Security tests |
| NFR-7 to NFR-11 | Privacy tests |
| NFR-12 to NFR-14 | Performance tests |
| NFR-15 to NFR-18 | Real-device checklist |
| NFR-19 to NFR-22 | Scenario tests, AI quality measurements |
| NFR-23, NFR-24 | One test file per check, configuration test |
