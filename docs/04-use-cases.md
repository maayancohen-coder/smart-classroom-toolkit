# Use Cases and User Stories

Status: v2 (updated for the implemented demo)

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
| UC13 | Get a transcript and summary of a lecture (live or from a recording) | Lecturer | AI tool |
| UC14 | Get an LLM review of homework | Student, Lecturer | AI tool |
| UC15 | Compare homework with other students' work | Lecturer, Student | AI tool |
| UC16 | Sign in and see my courses | Student, Lecturer | Core |
| UC17 | Write notes, message the lecturer and read published summaries | Student | Portal |

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

### UC13: Get a transcript and summary of a lecture (live or from a recording)

- **Actor:** Lecturer
- **Preconditions:** A lecture is open. Optionally the lecture slides are available.
- **Main flow (recording):**
  1. Lecturer opens the transcript page of the lecture and uploads the slides (optional) and the recording (video or audio).
  2. The browser extracts the sound from the file on the lecturer's computer and cuts it into parts of about 6 minutes.
  3. The system sends each part to the speech service (Gemini) and receives its text; the page shows "part N of M".
  4. The system joins the text and corrects technical terms using the glossary (slides and the lecturer's list), locally. The lecturer clicks any correction that is wrong to undo it.
  5. The lecturer can repair the text with the AI, edit it, and write a summary with the AI (or keep the automatic one), then reads it and can download it.
  6. Optionally the lecturer keeps the recording for the students (up to 100 MB).
  7. The lecturer publishes the lecture: students of the course see the summary, the full transcript and the recording player.
- **Main flow (live):** instead of steps 1 to 3 the lecturer records with the microphone; the browser's speech recognition produces the text and the system keeps the lecturer's voice and relevant student questions.
- **Alternate flows:**
  - 0a. The lecture already took place and was never opened: the lecturer adds it to the course by its date and continues from step 1.
  - 1a. File too large (over about 500 MB) or unsupported format: the page asks for another file, or for an audio-only export.
  - 3a. The AI service is unavailable or its quota is spent: the page shows the reason and the lecturer starts again; the parts already transcribed are not kept.
- **Notes:** The result is a suggestion for a human to check. Only the text is stored, unless the lecturer chooses to keep the recording for the students. The class must be told before a recording is transcribed (the page says so). Accuracy is measured in the tools report. The AI repair and summary are suggestions the lecturer checks before publishing.

### UC14: Submit homework and get feedback

- **Actor:** Student (and lecturer)
- **Preconditions:** The lecturer created an assignment for the course (questions, optional lecturer solution and course material). The student is signed in or enters the student number and PIN.
- **Main flow:**
  1. The student opens the assignment of a course and attaches a file (PDF, photo or handwritten scan) or pastes the text.
  2. Optionally the student checks the text against the course material (not saved) or asks for an AI review.
  3. The student submits. The system extracts the text (a vision model reads scans) and stores the submission and the file.
  4. The student opens the course page, sees that the homework is submitted and can open the submitted text and file.
- **Alternate flows:**
  - 1a. Unsupported or unreadable file: the system asks for another file or for pasted text.
  - 2a. The AI service is unavailable or its quota is spent: the page shows the reason; submission does not depend on it.
  - 3a. Submitting again replaces the earlier submission.
- **Notes:** The AI review is written in Hebrew, is a suggestion and not a grade, and the screen says that the text is sent to an external AI service after redaction of names and ID numbers.

### UC15: Review and compare homework (lecturer and student feedback)

- **Actor:** Lecturer; a student for their own feedback
- **Preconditions:** Several submissions of the same assignment exist (uploaded by students or imported by the lecturer).
- **Main flow (lecturer):**
  1. The lecturer opens the assignment report: similarity to the lecturer's solution, course terms used and missing, terms outside the course material, similar pairs.
  2. The lecturer runs an AI review of one submission, by the course material only or against the lecturer's solution, optionally compared with the classmates (anonymous).
  3. The lecturer asks for the common mistakes: the system sends all answers (anonymous, numbered) to the LLM and shows the mistakes that repeat, what the class did well and what to re-teach.
- **Main flow (student feedback):** the student asks for AI feedback on the submission; when at least 3 other students submitted and the lecturer allows it, the feedback includes an anonymous comparison with the class.
- **Notes:** A student never sees another student's work or name and the feedback does not quote classmates. The lecturer can switch the class comparison off per assignment. Names and ID numbers are removed before text is sent to the LLM.

### UC16: Sign in and see my courses

- **Actor:** Student, lecturer
- **Main flow:**
  1. The user opens the site and chooses Student or Lecturer.
  2. A student enters the student number and PIN; a lecturer chooses their name and enters the lecturer key and personal password. The first PIN or password entered becomes the user's own and cannot be changed.
  3. The system shows the courses of the user from the course catalogue. A student also sees which courses have a live lecture.
- **Alternate flows:** a wrong PIN or password is refused; after 5 wrong attempts the account is locked for 5 minutes.

### UC17: Write notes, message the lecturer and read published summaries

- **Actor:** Student
- **Main flow:**
  1. In a course with a live lecture the student joins it and writes short notes; the lecturer sees them in real time.
  2. In the course page the student sends a short message to the lecturer.
  3. After the lecture the student reads the summary if the lecturer published it.
- **Notes:** Notes and messages are rate limited and limited in length.

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
| Where does the lecture recording come from? | The lecturer uploads the file (video or audio, up to about 500 MB); there is no Zoom or Meet integration. The sound is extracted in the lecturer's browser. |
| How is the transcript kept accurate? | Demo: live speech recognition or Gemini speech-to-text on an uploaded recording, then a local correction by sound using the slides as a glossary. Designed: an LLM correction pass. Accuracy is measured on a real sample in the tools report. |
| Whose homework can be compared? | The lecturer sees the comparison of submissions of one assignment. A student gets only an anonymous, general comparison with the class (no quotes, at least 3 other submissions, can be switched off by the lecturer). |
| Is the data kept? | Not across a restart or a new deployment in the demo; see the SRS constraints. |
