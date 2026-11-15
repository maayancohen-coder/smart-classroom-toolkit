# Use Cases and User Stories

Status: draft v1

## 1. Actors

| Actor | Description |
|---|---|
| **Lecturer** | Opens lectures, shows the QR code, uploads a class photo, reads the attendance sheet, runs polls |
| **Student** | Marks attendance, answers polls, sends comments from their own phone |
| **People Counter** (system component) | Counts people in a class photo. Not a human actor, but it is an external-facing service the system calls |

## 2. Use case overview

| ID | Use case | Actor | Priority |
|---|---|---|---|
| UC1 | Open a lecture session | Lecturer | Core |
| UC2 | Display the rotating QR code | Lecturer | Core |
| UC3 | Mark attendance | Student | Core |
| UC4 | Upload a class photo and get the head-count gap | Lecturer | Core |
| UC5 | View and export the attendance sheet | Lecturer | Core |
| UC6 | Close a lecture session | Lecturer | Core |
| UC7 | Reset a student's phone binding | Lecturer | Secondary |
| UC8 | Create a quick poll | Lecturer | Light tool |
| UC9 | Answer a poll | Student | Light tool |
| UC10 | Send a comment or suggestion | Student | Light tool |
| UC11 | View poll results and comments | Lecturer | Light tool |
| UC12 | Add a student to the attendance after the lecture is closed | Lecturer | Secondary |

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
  3. If this phone is not yet known, student enters their student ID.
  4. Student allows location sharing.
  5. System runs the attendance checks (token freshness, device binding, classroom location, location plausibility, campus network).
  6. System records the check-in with a status (present or suspect) and the reasons.
  7. Student sees "attendance recorded". The status is **not** shown to the student.
- **Alternate flows:**
  - 2a. Token expired or invalid: the check-in is refused and the student is asked to scan again.
  - 3a. Student ID not found in the roster: error, student can correct the number.
  - 4a. Location denied: check-in is recorded as suspect.
  - 6a. The student already checked in: the system confirms and does not create a duplicate.
  - 6b. The phone is already linked to another student: recorded as suspect.
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
- **Notes:** The gap says how many, not who. Back rows may be undercounted, hence the tolerance.

### UC5: View and export the attendance sheet

- **Actor:** Lecturer
- **Main flow:**
  1. Lecturer opens the sheet during or after the lecture.
  2. System shows every student in the roster with a status: present, suspect (with reasons) or absent.
  3. Lecturer exports it to Excel or CSV.

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

## 5. Light tools (short form)

- **UC8 Create a quick poll:** lecturer enters a question and options; system publishes it to students in the active session.
- **UC9 Answer a poll:** student sees the open poll on the check-in page or by scanning the QR code, selects one option, one answer per student.
- **UC10 Send a comment:** student writes a short text during an active session and chooses **anonymous** or **with my name**; it is stored with the session. For an anonymous comment the system does not store or show the student's identity.
- **UC11 View results and comments:** lecturer sees live poll counts and the list of comments.

## 6. Decisions

| Question | Decision |
|---|---|
| Can students check in after the lecture is closed? | No. Only the lecturer can add students to a closed lecture (UC12), and the entry is marked as added manually. |
| What tolerance for the head-count gap? | 10% of the number of check-ins, configurable. To be validated with the class-photo experiment. |
| Are comments anonymous? | The student chooses for each comment: anonymous or with their name. |
