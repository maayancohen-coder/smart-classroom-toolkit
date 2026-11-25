# Software Requirements Specification (SRS)

Status: v2 (updated for the implemented demo)

## 1. Introduction

### 1.1 Purpose

This document defines what the smart-classroom-toolkit must do and the qualities it must have. It is derived from the use cases in `04-use-cases.md`.

### 1.2 Scope

A web application (Course Hub) for lecturers and students with a course portal and these tools: reliable attendance, student comments, quick polls, lecture transcript and summary, and homework review. The interface is in English. See the README for the scope and the planned depth of each tool.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| Session | One lecture, opened by a lecturer |
| Token | A short-lived signed value encoded in the QR code |
| Check-in | A student's attempt to mark attendance in a session |
| Suspect | A check-in that failed at least one strong check, or two weak checks |
| Gap | Number of check-ins minus the number of people counted in the room (typed by the lecturer, or counted from a class photo) |
| PIN | A personal code of 4 to 6 digits that a student chooses on the first check-in and enters on every later one |
| Phone profile | A hash of the phone model, screen, language and time zone; it is not a secret and not unique to a person |
| Class group | The centre and spread of the locations of the check-ins in one session |
| ASR | Automatic speech recognition (speech-to-text) |
| LLM | Large language model |
| Course portal | The pages a signed-in student or lecturer sees: their courses, live lecture, notes, messages, homework and published summaries |
| Redaction | Removing names and ID numbers from text before it is sent to an external AI service |

### 1.4 Priority

Requirements are marked **M** (must) or **S** (should). Attendance requirements are all **M**. The remaining tools are **S** unless stated.

## 2. Functional requirements

### 2.1 Sessions (UC1, UC6)

| ID | Requirement | Priority |
|---|---|---|
| FR-1 | The system shall let a lecturer open a session by entering a course name. | M |
| FR-2 | The system shall let the lecturer optionally record the classroom location and radius when opening the session. | M |
| FR-3 | The system shall let the lecturer close a session, after which students cannot check in. | M |
| FR-4 | The system shall load the class roster (student ID and name) from a file provided by the lecturer. | M |

### 2.2 Rotating QR code (UC2)

| ID | Requirement | Priority |
|---|---|---|
| FR-5 | The system shall display a QR code for the active session. | M |
| FR-6 | The QR code shall contain a token that is signed with a secret known only to the server and changes every 5 seconds (configurable). | M |
| FR-7 | The system shall accept a token only within a short window (current period plus 2 previous periods, configurable) and shall refuse older tokens. | M |

### 2.3 Attendance check-in (UC3)

| ID | Requirement | Priority |
|---|---|---|
| FR-8 | The system shall let a student check in by scanning the QR code with the phone camera, without installing an application. | M |
| FR-9 | The system shall ask a student for their student ID, and bind the phone to that student the first time it is used. | M |
| FR-9a | The system shall require a personal PIN of 4 to 6 digits on every check-in. The first time a student checks in, the PIN they enter becomes their PIN; later check-ins must match it, also from another phone or a private window. | M |
| FR-9b | The system shall store only a salted hash of the PIN, and shall lock a student for 5 minutes after 5 wrong PINs. | M |
| FR-10 | The system shall refuse a student ID that is not in the roster. | M |
| FR-11 | The system shall ask the student's phone for its location and record up to several readings with their accuracy. | M |
| FR-11a | If the session has a classroom location and the student's phone does not provide a location (permission denied or unavailable), the system shall refuse the check-in and ask the student to allow location. Nothing is recorded. | M |
| FR-12 | The system shall run these checks on every check-in. Strong: device binding, classroom location, location plausibility (accuracy better than 2 m), exactly the same coordinates as another student. Weak: token freshness, frozen location (identical readings), stale location reading (older than 60 s), same phone profile as another student, a repeated check-in from the same phone profile and network within 120 s, campus network. | M |
| FR-12a | Once at least 6 check-ins have an accurate location, the system shall compute the centre and spread of the class group and shall mark a check-in suspect when its location is clearly outside that group, even if it is inside the lecturer's radius (note: "outside the class group"). | M |
| FR-13 | The system shall mark a check-in **suspect** if at least one strong check fails or at least two weak checks fail, and otherwise **present**. | M |
| FR-14 | The system shall store the reason for every failed check with the check-in. | M |
| FR-15 | The system shall not show the student the status or reasons, only that the check-in was recorded. | M |
| FR-16 | The system shall ignore a repeated check-in of the same student in the same session and confirm that attendance is already recorded. | M |
| FR-17 | The system shall flag as suspect a check-in from a phone bound to another student. A check-in of a bound student from another phone is suspect unless the student proves their identity with the correct PIN. | M |
| FR-18 | The system shall allow the lecturer to reset the phone binding and the PIN of a student. | S |
| FR-19 | The system shall be extensible with new checks without changing existing checks. | M |

### 2.4 Head-count gap (UC4)

**Status:** the gap logic and the manual entry (FR-23, FR-24, FR-24a) are implemented. Counting people from a photo (FR-20 to FR-22) is designed, with a swappable counter component, but was dropped from the demo because the free vision service did not give a stable result in our attempts (tools report, 3.6).

| ID | Requirement | Priority |
|---|---|---|
| FR-20 | The system should let the lecturer upload one or more class photos. **Designed, not in the demo** (see the note under 2.4). | S |
| FR-21 | The system should count the people in each photo and use the highest count for the session. **Designed, not in the demo.** | S |
| FR-22 | The system shall delete the photo after counting and store only the count. | S |
| FR-23 | The system shall show the gap between the number of check-ins and the counted people. | M |
| FR-24 | If the gap is larger than 10% of the check-ins (configurable), the system shall highlight the check-ins with the most failed checks. | M |
| FR-24a | The system shall let the lecturer enter the head count by hand; the gap logic is the same. | M |

### 2.5 Attendance sheet (UC5, UC12)

| ID | Requirement | Priority |
|---|---|---|
| FR-25 | The system shall show every student in the roster as present, suspect or absent, with check-in time and reasons. | M |
| FR-26 | The system shall update the sheet while the session is open. | M |
| FR-27 | The system shall export the sheet to Excel and CSV. | M |
| FR-25a | The system shall let the lecturer approve a suspect check-in, which makes the student present while the reasons stay visible and the entry is marked "approved by lecturer", and shall let the lecturer undo the approval. Only the lecturer can do this. | M |
| FR-28 | After a session is closed, only the lecturer shall be able to add a student to the attendance. The entry shall be marked as added manually. | M |

### 2.6 Comments and polls (UC8 to UC11)

| ID | Requirement | Priority |
|---|---|---|
| FR-29 | The system shall let a lecturer create a poll with a question and options and publish it to the session. | S |
| FR-30 | The system shall accept one answer per student per poll and show live counts to the lecturer. | S |
| FR-31 | The system shall suggest a poll question from the current slide using an LLM. | S |
| FR-32 | The system shall let a student send a text comment and choose whether it is anonymous or carries their name. | S |
| FR-32a | A comment sent during the lecture shall appear to the lecturer in real time. A comment sent after the lecture (offline) shall be stored with the session and be visible to the lecturer later. | S |
| FR-33 | The system shall not store or show the identity of the author of an anonymous comment. | S |

### 2.7 Transcript and summary (UC13)

**Status:** implemented in the demo. The transcript comes (1) live, from the lecturer's browser (Chrome), or (2) from a recording: the lecturer uploads audio or video of a current or past lecture, the browser extracts the sound on the lecturer's computer, cuts it into parts of about 6 minutes, and the server sends each part to an AI speech service (Gemini). The server then corrects technical terms by sound from a glossary (slides and the lecturer's list, locally, no LLM); the lecturer can undo any correction that is wrong. The lecturer can repair the text with the AI, edit it, and write a summary with the AI (or use the automatic extractive one). The lecturer publishes the lecture: students then see the summary, the full transcript and, if the lecturer kept it, the recording.

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-34 | The system shall let the lecturer upload a lecture recording (video or audio, up to about 500 MB) and optional slides (PowerPoint, PDF or text). | S | Done |
| FR-34a | If the recording is a video, the sound shall be extracted from it. In the demo this is done in the lecturer's browser, so only audio leaves the computer. | S | Done (in the browser) |
| FR-35 | The system shall produce a transcript, live from the microphone or from an uploaded recording. | S | Done |
| FR-36 | The system shall correct the transcript using the slides' text and the lecturer's list as a glossary of terms. The correction is local, by sound similarity, and limited so that a term replaces at most a few words. | S | Done (local) |
| FR-36a | The lecturer shall be able to undo any single term correction, and to repair the text with an AI service (part by part, content unchanged) and edit it by hand. | S | Done |
| FR-37 | The system shall produce a summary of the corrected transcript: an automatic extractive one, or an AI-written one in Hebrew that the lecturer checks and saves. | S | Done |
| FR-38 | The system shall let the lecturer edit and download the transcript and summary and publish them to the students of the course. | S | Done |
| FR-38a | The lecturer shall be able to add a lecture that already took place (by date) to a course and upload its recording and transcript, also after the live lecture was closed. | S | Done |
| FR-38b | If the lecturer chooses to keep the recording (up to 100 MB), the students of the course shall be able to play it, only after the lecture is published. | S | Done |
| FR-39 | The system shall show the progress of a recording transcription (part N of M) and the reason for a failure. In the demo this is shown on the page while it runs; there is no background job that continues after the page is closed, and a failed part means starting again. | S | Done (progress on the page) |

Not in the demo: a server-side background job and extracting audio on the server (for example with ffmpeg). A kept recording is saved to Firestore with the rest of the state. The transcript of a recording includes every speaker; the lecturer-voice filter exists only in the live transcript.

### 2.8 Homework (UC14, UC15)

| ID | Requirement | Priority |
|---|---|---|
| FR-40 | The system shall let a lecturer create an assignment for a course with optional files: the questions, the lecturer's solution and the course material. Files may be PDF, text or an image; text is extracted and scans or handwriting are read by a vision model. | S |
| FR-40a | The system shall let a student submit a solution to an assignment of a course (a file or pasted text) and shall let the student open the submission, and the uploaded file, later from the course page. A new submission replaces the earlier one. | S |
| FR-40b | The system shall let the lecturer import many submissions at once, each file named by the student number. | S |
| FR-41 | The system shall give the lecturer a report per assignment: similarity to the lecturer's solution, the share of course terms used, terms missing, English terms that are not in the course material, and the most similar classmate. | S |
| FR-41a | The system shall let the student run a check against the course material before submitting, without saving or sending it to the lecturer. | S |
| FR-42 | The system shall flag pairs of submissions that are very similar (at least 50% shared word sequences, the assignment text excluded). | S |
| FR-42a | The system shall show the lecturer the terms that many students miss or that many students use outside the course material. | S |
| FR-43 | The system shall never show a student another student's work or name. | S |
| FR-44 | The system shall let the lecturer get an LLM review of one submission, judged either by the course material only or against the lecturer's solution, optionally compared with the classmates' answers. | S |
| FR-44a | The system shall let the student get an LLM review of their own submission, judged by the course material. When at least 3 other students have submitted and the lecturer allows it, the review shall include an anonymous comparison with the class that does not quote or paraphrase any classmate. | S |
| FR-44b | The system shall let the lecturer get from an LLM the mistakes that repeat across all submissions of an assignment, what the class did well and what to re-teach, with answers referred to by number only. | S |
| FR-44c | The review text shall be written in Hebrew; mathematical expressions and technical terms stay in their original form. | S |
| FR-45 | Before text is sent to an LLM the system shall remove ID numbers and the names of the submitter and of the class (redaction) and shall mark the submitted text as data that must not be obeyed as instructions. | S |
| FR-46 | The system shall let the lecturer switch off, per assignment, the comparison with classmates in the students' feedback. | S |
| FR-47 | The system shall limit a student to one LLM request every 30 seconds. | S |

### 2.9 Course portal and accounts (UC16, UC17)

| ID | Requirement | Priority |
|---|---|---|
| FR-48 | The system shall let a student sign in with the student number and the personal PIN, and a lecturer sign in with the lecturer key and a personal password. | M |
| FR-48a | The personal PIN (student) and personal password (lecturer) shall be chosen on the first sign-in and cannot be changed afterwards, except by a lecturer reset of a student's PIN (FR-18). | M |
| FR-48b | For testing, the lecturer shall be able to download a file listing for each student and lecturer whether a password is set and, when the server is configured to keep it, the chosen value. This can be switched off. | S |
| FR-49 | The system shall show each student the courses they take and each lecturer the courses they teach, from a course catalogue file kept with the code. | M |
| FR-50 | The system shall show a student whether a lecture is live in each course and let the student join it. | S |
| FR-51 | A student shall be able to write short notes during a live lecture, and to see their own notes. The lecturer shall see the notes in real time. Notes are rate limited. | S |
| FR-52 | A student shall be able to send a short message to the lecturer of a course; the lecturer shall see the messages of the course. | S |
| FR-53 | The lecturer shall be able to publish the lecture summary to the students of the course, who then see it in the course page. | S |
| FR-54 | The student home page shall offer homework submission and attendance, and attendance shall offer scanning the QR code with the in-page camera. | S |

## 3. Non-functional requirements

### 3.1 Security

| ID | Requirement |
|---|---|
| NFR-1 | Tokens shall be signed with HMAC and compared in constant time. A forged or modified token shall be rejected. |
| NFR-2 | A check-in ticket shall be single-use and shall expire after 2 minutes (configurable). |
| NFR-3 | Lecturer functions shall require authentication (lecturer key and personal password). A student shall not be able to call a lecturer function, and a student shall see only their own submissions and the courses they take. |
| NFR-4 | All traffic shall use HTTPS. |
| NFR-5 | The device identifier shall be a random value stored in a cookie that is not readable by page scripts. |
| NFR-6 | The system shall limit the rate of check-in attempts per client to slow down guessing and scripted abuse. In the demo only the PIN lock (FR-9b) is implemented; general rate limiting is future work. |

### 3.2 Privacy

| ID | Requirement |
|---|---|
| NFR-7 | Class photos shall be deleted right after counting. Only the count is kept. |
| NFR-8 | Location readings shall be used for verification and kept only with the check-in, to explain the result. |
| NFR-9 | Live transcription in the lecturer's browser uses the browser's speech service (for Chrome, Google), and an uploaded recording is sent, as audio parts, to an external AI service (Gemini) and contains students' voices. The audio is not stored by the system, only the text. The lecturer shall make sure the class is informed; the transcript page says so. |
| NFR-10 | Homework data sent to an external LLM (Gemini) shall be limited to what the review needs: names and ID numbers are removed first (FR-45), classmates are anonymous, and the screens tell the user that the text is sent to an external AI service. Students are informed that a comparison with the class is performed. The free API tier may use submitted data to improve the service, so real student data needs a paid tier or an agreement. |
| NFR-11 | The system shall not use face recognition. |

### 3.3 Performance and scalability

| ID | Requirement |
|---|---|
| NFR-12 | The system shall support 200 students checking in within a minute, with a response time of at most 2 seconds for 95% of check-ins. |
| NFR-13 | The attendance sheet shall refresh at least every 3 seconds. |
| NFR-14 | Transcription shall not block other functions. |

### 3.4 Usability

| ID | Requirement |
|---|---|
| NFR-15 | A student shall be able to check in with one scan and, after the first time, by typing only the personal PIN. |
| NFR-16 | The lecturer shall open a session with one action and shall not need to do anything during the lecture. |
| NFR-17 | The student pages shall work on current iPhone and Android browsers, with no installation. |
| NFR-18 | The interface is in English. Hebrew content (names, AI reviews, transcripts) shall display correctly, each text block in its own direction. |

### 3.5 Reliability and quality

| ID | Requirement |
|---|---|
| NFR-19 | If the session has a classroom location and the phone does not provide a location, the check-in shall be refused (FR-11a). If the classroom location was not set, no location is required. |
| NFR-20 | If an external service (ASR, LLM, people counter) fails, the rest of the system shall keep working and the job shall be retryable. |
| NFR-21 | ASR accuracy shall be measured on a real lecture sample and reported in the tools report. No accuracy is promised before the measurement. |
| NFR-22 | LLM outputs shall be marked as suggestions to be checked by a person, and shall never be shown as a grade. |
| NFR-22a | If the AI service fails or its quota is spent, the page shall show the exact reason, and the lecturer shall have a live test of the AI service (key, model, answer time). |

### 3.6 Maintainability

| ID | Requirement |
|---|---|
| NFR-23 | Each attendance check shall be an independent class behind a common interface, with its own unit tests. |
| NFR-24 | Thresholds (token period, grace window, radius, gap tolerance) shall be configuration values, not code. |

## 4. Constraints and assumptions

- Web application only; no native apps and no NFC or Bluetooth.
- The class roster is provided by the lecturer; there is no integration with Moodle or the university portal.
- Recordings are uploaded by the lecturer; there is no Zoom or Meet integration.
- Storage is in memory, and a snapshot is saved to Firebase Cloud Firestore after every change and loaded on start, so a restart or a new deployment keeps sessions, recordings, assignments, submissions and passwords. A database behind the existing storage layer is designed (see the components document) and not part of the demo.
- Students have a phone with a camera, a browser, and mobile data or campus Wi-Fi.
- Indoor location accuracy is limited to tens of meters.
- External AI services are used for ASR, people counting and LLM tasks; the exact tools are selected in the tools report.

### 4.1 Identifying a person, and its limits

- A phone is recognised by a random cookie (NFR-5). A **private window** or cleared site data gives a new cookie, so the cookie alone cannot tie a phone to a person.
- What ties a **person** to a check-in is the personal PIN (FR-9a). A student who opens a private window to mark a friend must know the friend's PIN, and five wrong guesses lock the friend's account for 5 minutes (FR-9b). The PIN is not biometric; biometrics and passkeys were rejected for privacy and are only a possible future upgrade.
- Signals that still help when the PIN is not enough: the same coordinates as another student, the same phone profile (model, screen, language, time zone) and the same network in a short time, and a location outside the class group.
- Tested by hand on an iPhone: a private tab marking a second student was recorded as suspect with its reasons; a wrong PIN in a private tab was refused; denying location prevented the check-in; an old QR code was refused as expired.
- **Accepted limits:** (1) the first person to enter a student's ID chooses that student's PIN, so the lecturer can reset it if the student reports a problem; (2) a student can give the PIN to a friend voluntarily; (3) two phones of the same model look alike, so the phone profile is only a weak signal; (4) indoor location is accurate to tens of meters and cannot separate neighbouring rooms.

## 5. Traceability

| Use case | Requirements |
|---|---|
| UC1, UC6 | FR-1 to FR-4 |
| UC2 | FR-5 to FR-7 |
| UC3 | FR-8 to FR-19, including FR-9a, FR-9b, FR-11a, FR-12a |
| UC4 | FR-20 to FR-24a |
| UC5, UC12 | FR-25 to FR-28 |
| UC7 | FR-18 |
| UC8 to UC11 | FR-29 to FR-33 |
| UC13 | FR-34 to FR-39 |
| UC14, UC15 | FR-40 to FR-47 |
| UC16, UC17 | FR-48 to FR-54 |
