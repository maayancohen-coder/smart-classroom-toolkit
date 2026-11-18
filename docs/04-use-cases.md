# Use Cases and User Stories

Status: draft v1

## 1. Actors

| Actor | Description |
|---|---|
| **Lecturer** | Opens lectures, shows the QR code, uploads a class photo, reads the attendance sheet, runs polls |
| **Student** | Marks attendance, answers polls, sends comments from their own phone |
| **People Counter** (system component) | Counts people in a class photo. Not a human actor, but it is an external-facing service the system calls |
| **Speech-to-Text service** (system component) | Turns a lecture recording into text |
| **LLM service** (system component) | Corrects the transcript, writes summaries, reviews homework, suggests poll questions |

## 2. Use case overview

| ID | Use case | Actor | Priority |
|---|---|---|---|
| UC1 | Open a lecture session | Lecturer | Core |
| UC2 | Display the rotating QR code | Lecturer | Core |
| UC3 | Mark attendance | Student | Core |
| UC4 | Upload a class photo and get the head-count gap | Lecturer | Designed (the demo takes a typed count) |
| UC5 | View and export the attendance sheet | Lecturer | Core |
| UC6 | Close a lecture session | Lecturer | Core |
| UC7 | Reset a student's phone binding | Lecturer | Secondary |
| UC8 | Create a quick poll | Lecturer | Light tool |
| UC9 | Answer a poll | Student | Light tool |
| UC10 | Send a comment or suggestion | Student | Light tool |
| UC11 | View poll results and comments | Lecturer | Light tool |
| UC12 | Add a student to the attendance after the lecture is closed | Lecturer | Secondary |
| UC13 | Get a transcript and summary of a lecture recording | Lecturer | AI tool |
| UC14 | Get an LLM review of homework | Student, Lecturer | AI tool |
| UC15 | Compare homework with other students' work | Lecturer, Student | AI tool |

## 3. User stories

| ID | Story | Acceptance criteria |
|---|---|---|
| US1 | As a lecturer, I want to open a lecture with one action, so I do not lose lecture time. | One button; a QR code is visible immediately |
| US2 | As a lecturer, I want the QR code to change every few seconds, so a photo of it cannot be shared with someone outside. | A code older than the allowed window is rejected |
| US3 | As a student, I want to mark attendance in seconds, so it does not interrupt the lecture. | One scan, no app installation; first time only requires my student ID |
| US4 | As a lecturer, I want to know whether the student was physically near the classroom, so remote check-ins are caught. | Check-ins outside the classroom area are flagged as suspect |
| US5 | As a lecturer, I want to compare the number of check-ins to the number of people in a class photo, so I can tell if the list is inflated. | The gap is shown as a number next to the attendance total |
| US6 | As a lecturer, I want a sheet of students marked present, suspect or absent, with the reason for each suspect, so I can decide who to follow up on. | Sheet available online and as Excel/CSV |
| US7 | As a lecturer, I want one phone to be tied to one student, so one phone cannot mark attendance for a group. | A second student ID on the same phone is flagged |
| US8 | As a lecturer, I want to fix a student's phone binding when they change phones. | Reset action per student |
| US9 | As a lecturer, I want to ask a quick question during the lecture and see the results, so I know whether the class understood. | Poll created in a few seconds; live result counts |
| US10 | As a student, I want to send a comment during or after the lecture, so I can give feedback without interrupting, and choose whether it carries my name or is anonymous. | Short text; the student chooses "anonymous" or "with my name" for each comment; delivered to the lecturer accordingly |
| US11 | As a student, I do not want my location or photo stored longer than needed. | Class photos deleted after counting; only the count is kept |
| US12 | As a lecturer, I want to add a student to the attendance after the lecture closed (for example a student with a phone problem), and only I can do that. | Students cannot check in after closing; the lecturer can add a student, and the entry is marked as added manually |
| US13 | As a lecturer, I want to upload a lecture recording and get an accurate transcript and a summary, so students who missed the lecture can catch up. | Transcript in the lecture language; technical terms from the slides are spelled correctly; summary is shown next to the transcript |
| US14 | As a student, I want a detailed review of my homework before I submit it, so I can improve it. | Review lists strengths, mistakes and suggestions; shown only to me and, if I choose, to the lecturer |
| US15 | As a lecturer, I want to compare homework submissions, so I can spot copying and common mistakes. | Comparison covers only submissions of this assignment; students are informed that comparison is done |
| US16 | As a lecturer, I want to be offered a poll question generated from the current slide, so I can launch a poll quickly. | Suggestion can be edited before it is published |

## 4. Detailed use cases (core)

### UC1: Open a lecture session

- **Actor:** Lecturer
- **Goal:** Start collecting attendance for a lecture.
- **Preconditions:** Lecturer is signed in. The class roster (student ID and name) is loaded.
- **Main flow:**
  1. Lecturer chooses "Open lecture" and enters the course name.
  2. Lecturer allows the browser to share the classroom location (optional).
  3. System creates the session, stores the classroom location and radius, and shows the lecture screen.
- **Alternate flows:**
  - 2a. Lecturer does not share a location: the location check is turned off for this session, and the sheet says so.
- **Postcondition:** An active session exists.

### UC2: Display the rotating QR code

- **Actor:** Lecturer
- **Preconditions:** A session is active.
- **Main flow:**
  1. System generates a signed token that is valid for a short window.
  2. System renders it as a QR code on the lecture screen.
  3. System generates a new token every few seconds and refreshes the code.
- **Postcondition:** At any moment, only the most recent tokens are accepted.

### UC3: Mark attendance

- **Actor:** Student
- **Goal:** Record presence in the lecture.
- **Preconditions:** A session is active. The student has a phone with a camera and a browser.
- **Main flow:**
  1. Student scans the QR code with the phone camera, which opens the check-in page.
  2. System verifies the token is valid and recent.
  3. Student enters their student ID (if the phone is not yet known) and their personal PIN. The first time, the PIN they enter becomes theirs.
  4. Student allows location sharing. Without it the check-in is refused.
  5. System verifies the PIN and runs the attendance checks (token freshness, device binding, classroom location, location plausibility, same coordinates, stale or frozen location, phone profile, class group, campus network).
  6. System records the check-in with a status (present or suspect) and the reasons.
  7. Student sees "attendance recorded". The status is **not** shown to the student.
- **Alternate flows:**
  - 2a. Token expired or invalid: the check-in is refused and the student is asked to scan again.
  - 3a. Student ID not found in the roster: error, student can correct the number.
  - 3b. Wrong PIN: the check-in is refused. After 5 wrong PINs the student is locked for 5 minutes.
  - 4a. Location denied or unavailable: the check-in is refused and the student is asked to allow location. Nothing is recorded.
  - 6a. The student already checked in: the system confirms and does not create a duplicate.
  - 6b. The phone is already linked to another student: recorded as suspect. A student who uses a new phone with the correct PIN is not suspect for that reason.
- **Postcondition:** The check-in is stored; the sheet updates.

### UC4: Upload a class photo and get the head-count gap

- **Actor:** Lecturer
- **Preconditions:** A session is active or has just ended.
- **Main flow:**
  1. Lecturer uploads one or more photos of the class.
  2. System sends the photo to the People Counter.
  3. People Counter returns the number of people detected.
  4. System deletes the photo and stores only the number.
  5. System compares the count with the number of check-ins and shows the gap.
  6. If the gap exceeds the tolerance, the system highlights the most suspect check-ins. The tolerance is **10% of the number of check-ins** (configurable), to allow for students hidden in back rows or behind others.
- **Alternate flows:**
  - 3a. The counter fails or the image is unusable: system asks for another photo and keeps the session unchanged.
- **Status:** designed; the demo supports only the manual head count. Counting from a photo was dropped from the demo (tools report, 3.6).
- **Notes:** The gap says how many, not who. Back rows may be undercounted, hence the tolerance.

### UC5: View and export the attendance sheet

- **Actor:** Lecturer
- **Main flow:**
  1. Lecturer opens the sheet during or after the lecture.
  2. System shows every student in the roster with a status: present, suspect (with reasons) or absent.
  3. Lecturer exports it to Excel or CSV.
- **Alternate flow:**
  - 2a. Lecturer decides that a suspect student was really in the class and presses "approve". The student becomes present, the reasons stay in the notes marked "approved by lecturer", and the lecturer can undo it.

### UC6: Close a lecture session

- **Actor:** Lecturer
- **Main flow:** Lecturer closes the lecture. The system stops accepting check-ins from students. Only the lecturer can add students afterwards (UC12).

### UC7: Reset a student's phone binding

- **Actor:** Lecturer
- **Main flow:** Lecturer selects a student and resets their phone binding. The student's next check-in binds the new phone.

### UC12: Add a student after the lecture is closed

- **Actor:** Lecturer (only)
- **Preconditions:** The session is closed. The student is in the roster.
- **Main flow:**
  1. Lecturer selects the closed lecture and chooses "Add student".
  2. Lecturer selects the student from the roster.
  3. System marks the student present and records that the entry was **added manually by the lecturer**, with the time.
- **Notes:** Students themselves can never check in after the lecture is closed. Manual entries do not count toward the head-count comparison logic as suspects, but are shown separately in the sheet.

### UC13: Get a transcript and summary of a lecture recording

- **Actor:** Lecturer
- **Preconditions:** The lecture has a recording file (for example exported from Zoom or Meet). Optionally, the lecture slides are available.
- **Main flow:**
  1. Lecturer uploads the recording and, optionally, the slides.
  2. If the file is a video, the system extracts the audio track. System sends the audio to the Speech-to-Text service and receives a raw transcript.
  3. System sends the raw transcript, together with the slides' text as a glossary, to the LLM service, which corrects technical terms and punctuation.
  4. System sends the corrected transcript to the LLM service and receives a summary.
  5. Lecturer reads the transcript and summary and can edit them or download them.
- **Alternate flows:**
  - 1a. File too large or unsupported format: the system asks for another file.
  - 2a. Service unavailable or fails: the job is marked failed, and the lecturer can retry.
  - 5a. Lecturer shares the summary with the class (optional).
- **Notes:** The result is a suggestion for a human to check. Accuracy is measured in the tools report.

### UC14: Get an LLM review of homework

- **Actor:** Student or lecturer
- **Preconditions:** A homework file is available (for example PDF or text).
- **Main flow:**
  1. The user uploads the homework and, if available, the assignment text.
  2. System sends them to the LLM service with the review instructions.
  3. System returns a structured review: strengths, mistakes, missing parts, suggestions.
- **Alternate flows:**
  - 1a. Unsupported or unreadable file: the system asks for another file.
  - 3a. The review is only visible to the student unless the student shares it.

### UC15: Compare homework with other students' work

- **Actor:** Lecturer (and a student, only against reference material the lecturer provides)
- **Preconditions:** Several submissions of the same assignment were uploaded by the lecturer, or the lecturer provided reference solutions.
- **Main flow:**
  1. Lecturer selects the assignment and starts the comparison.
  2. System asks the LLM service to compare the submissions and report similarities and common mistakes.
  3. System shows the report to the lecturer.
- **Notes:** A student never sees another student's work. Students are told that comparison is performed. This is detailed in the SRS (privacy).

## 5. Light tools (short form)

- **UC8 Create a quick poll:** lecturer enters a question and options; system publishes it to students in the active session. The system can also suggest a question generated by the LLM from the current slide (US16).
- **UC9 Answer a poll:** student sees the open poll on the check-in page or by scanning the QR code, selects one option, one answer per student.
- **UC10 Send a comment:** student writes a short text, during the lecture (shown to the lecturer in real time) or after it (offline, stored for later), and chooses **anonymous** or **with my name**; it is stored with the session. For an anonymous comment the system does not store or show the student's identity.
- **UC11 View results and comments:** lecturer sees live poll counts and the list of comments.

## 6. Decisions

| Question | Decision |
|---|---|
| Can students check in after the lecture is closed? | No. Only the lecturer can add students to a closed lecture (UC12), and the entry is marked as added manually. |
| What tolerance for the head-count gap? | 10% of the number of check-ins, configurable. Not validated: the class-photo experiment was dropped (tools report, 3.6). |
| Are comments anonymous? | The student chooses for each comment: anonymous or with their name. |
| Where does the lecture recording come from? | The lecturer uploads the file; there is no Zoom or Meet integration. |
| How is the transcript kept accurate? | A speech-to-text model, then an LLM corrects terms using the slides as a glossary. Accuracy is measured on a real sample in the tools report. |
| Whose homework can be compared? | The lecturer can compare submissions of one assignment. A student can only compare against reference material provided by the lecturer. |
