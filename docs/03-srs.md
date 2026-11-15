# Software Requirements Specification (SRS)

Status: draft v1

## 1. Introduction

### 1.1 Purpose

This document defines what the smart-classroom-toolkit must do and the qualities it must have. It is derived from the use cases in `04-use-cases.md`.

### 1.2 Scope

A web application for lecturers and students with five tools: reliable attendance, student comments, quick polls, lecture transcript and summary, and homework review. See the README for the scope and the planned depth of each tool.

### 1.3 Definitions

| Term | Meaning |
|---|---|
| Session | One lecture, opened by a lecturer |
| Token | A short-lived signed value encoded in the QR code |
| Check-in | A student's attempt to mark attendance in a session |
| Suspect | A check-in that failed at least one strong check, or two weak checks |
| Gap | Number of check-ins minus the number of people counted in the class photo |
| ASR | Automatic speech recognition (speech-to-text) |
| LLM | Large language model |

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
| FR-9 | The system shall ask a student for their student ID the first time a phone is used, and bind that phone to that student. | M |
| FR-10 | The system shall refuse a student ID that is not in the roster. | M |
| FR-11 | The system shall ask the student's phone for its location and record up to several readings with their accuracy. | M |
| FR-12 | The system shall run these checks on every check-in: token freshness (weak), device binding (strong), classroom location (strong), location plausibility (strong), campus network (weak). | M |
| FR-13 | The system shall mark a check-in **suspect** if at least one strong check fails or at least two weak checks fail, and otherwise **present**. | M |
| FR-14 | The system shall store the reason for every failed check with the check-in. | M |
| FR-15 | The system shall not show the student the status or reasons, only that the check-in was recorded. | M |
| FR-16 | The system shall ignore a repeated check-in of the same student in the same session and confirm that attendance is already recorded. | M |
| FR-17 | The system shall flag as suspect a check-in from a phone bound to another student, and a check-in of a bound student from another phone. | M |
| FR-18 | The system shall allow the lecturer to reset the phone binding of a student. | S |
| FR-19 | The system shall be extensible with new checks without changing existing checks. | M |

### 2.4 Head-count gap (UC4)

| ID | Requirement | Priority |
|---|---|---|
| FR-20 | The system shall let the lecturer upload one or more class photos. | M |
| FR-21 | The system shall count the people in each photo and use the highest count for the session. | M |
| FR-22 | The system shall delete the photo after counting and store only the count. | M |
| FR-23 | The system shall show the gap between the number of check-ins and the counted people. | M |
| FR-24 | If the gap is larger than 10% of the check-ins (configurable), the system shall highlight the check-ins with the most failed checks. | M |

### 2.5 Attendance sheet (UC5, UC12)

| ID | Requirement | Priority |
|---|---|---|
| FR-25 | The system shall show every student in the roster as present, suspect or absent, with check-in time and reasons. | M |
| FR-26 | The system shall update the sheet while the session is open. | M |
| FR-27 | The system shall export the sheet to Excel and CSV. | M |
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

| ID | Requirement | Priority |
|---|---|---|
| FR-34 | The system shall let the lecturer upload a lecture recording (video or audio file, for example exported from Zoom, Meet or Google Classroom) and optional slides. | S |
| FR-34a | If the recording is a video, the system shall extract its audio track before transcription. | S |
| FR-35 | The system shall produce a transcript with an ASR service. | S |
| FR-36 | The system shall correct the transcript with an LLM using the slides' text as a glossary of terms. | S |
| FR-37 | The system shall produce a summary of the corrected transcript with an LLM. | S |
| FR-38 | The system shall let the lecturer edit, download, and optionally share the transcript and summary. | S |
| FR-39 | The system shall run transcription as a background job and show its progress and failure. | S |

### 2.8 Homework review (UC14, UC15)

| ID | Requirement | Priority |
|---|---|---|
| FR-40 | The system shall let a student or lecturer upload homework and receive an LLM review with strengths, mistakes, missing parts and suggestions. | S |
| FR-41 | The review shall be visible only to the uploader unless they share it. | S |
| FR-42 | The system shall let a lecturer compare submissions of one assignment and report similarities and common mistakes. | S |
| FR-43 | The system shall never show a student another student's work. | S |

## 3. Non-functional requirements

### 3.1 Security

| ID | Requirement |
|---|---|
| NFR-1 | Tokens shall be signed with HMAC and compared in constant time. A forged or modified token shall be rejected. |
| NFR-2 | A check-in ticket shall be single-use and shall expire after 2 minutes (configurable). |
| NFR-3 | Lecturer functions shall require authentication. A student shall not be able to call a lecturer function. |
| NFR-4 | All traffic shall use HTTPS. |
| NFR-5 | The device identifier shall be a random value stored in a cookie that is not readable by page scripts. |
| NFR-6 | The system shall limit the rate of check-in attempts per client to slow down guessing and scripted abuse. |

### 3.2 Privacy

| ID | Requirement |
|---|---|
| NFR-7 | Class photos shall be deleted right after counting. Only the count is kept. |
| NFR-8 | Location readings shall be used for verification and kept only with the check-in, to explain the result. |
| NFR-9 | Lecture recordings contain students' voices. The lecturer shall confirm that the class was informed before uploading. |
| NFR-10 | Homework data sent to an external LLM shall be limited to what the review needs. Students shall be informed that comparison is performed. |
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
| NFR-15 | A student shall be able to check in with one scan and, after the first time, with no typing. |
| NFR-16 | The lecturer shall open a session with one action and shall not need to do anything during the lecture. |
| NFR-17 | The student pages shall work on current iPhone and Android browsers, with no installation. |
| NFR-18 | The interface shall support Hebrew (right to left). |

### 3.5 Reliability and quality

| ID | Requirement |
|---|---|
| NFR-19 | If location is unavailable or denied, the system shall record the check-in as suspect and not reject it. |
| NFR-20 | If an external service (ASR, LLM, people counter) fails, the rest of the system shall keep working and the job shall be retryable. |
| NFR-21 | ASR accuracy shall be measured on a real lecture sample and reported in the tools report. No accuracy is promised before the measurement. |
| NFR-22 | LLM outputs shall be marked as suggestions to be checked by a person. |

### 3.6 Maintainability

| ID | Requirement |
|---|---|
| NFR-23 | Each attendance check shall be an independent class behind a common interface, with its own unit tests. |
| NFR-24 | Thresholds (token period, grace window, radius, gap tolerance) shall be configuration values, not code. |

## 4. Constraints and assumptions

- Web application only; no native apps and no NFC or Bluetooth.
- The class roster is provided by the lecturer; there is no integration with Moodle or the university portal.
- Recordings are uploaded by the lecturer; there is no Zoom or Meet integration.
- Students have a phone with a camera, a browser, and mobile data or campus Wi-Fi.
- Indoor location accuracy is limited to tens of meters.
- External AI services are used for ASR, people counting and LLM tasks; the exact tools are selected in the tools report.

## 5. Traceability

| Use case | Requirements |
|---|---|
| UC1, UC6 | FR-1 to FR-4 |
| UC2 | FR-5 to FR-7 |
| UC3 | FR-8 to FR-19 |
| UC4 | FR-20 to FR-24 |
| UC5, UC12 | FR-25 to FR-28 |
| UC7 | FR-18 |
| UC8 to UC11 | FR-29 to FR-33 |
| UC13 | FR-34 to FR-39 |
| UC14, UC15 | FR-40 to FR-43 |
