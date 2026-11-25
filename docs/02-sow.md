# Statement of Work (SoW)

Status: v2 (updated for what was built)

## 1. Purpose

This document states what we will deliver for Exercise 2 of Intro to Software Engineering, what is left out, how we will know the work is done, and what could go wrong. It is the plan the two authors set for the exercise.

## 2. Background

Attendance in class is slow or easy to fake. A shared QR code can be photographed and sent to a friend; a location app only shows that someone is near the building. The project is a web-based teaching toolkit. The attendance tool is the core. The course portal (sign-in, courses, live notes, messages), the lecture transcript and summary, and the homework tool with AI review were also built as working demos on the hosted site (Course Hub); polls and comments are design documents only.

## 3. Objectives

1. Give the lecturer an attendance sheet they can trust, with the doubtful check-ins marked and explained.
2. Let a student mark attendance in seconds from the phone browser, with nothing to install.
3. Make it hard to mark attendance for someone else, and show the lecturer when it is attempted.
4. Document the design well enough that another team could build it.

## 4. Scope

### 4.1 In scope

| Area | What we deliver |
|---|---|
| Attendance tool | Working demo: rotating QR code, mandatory location permission, personal PIN per student, device binding, suspect marking with reasons, live lecturer page, Excel/CSV export, manual head-count entry |
| Course portal | Working demo: sign-in for students and lecturers with a personal PIN or password chosen once, a course list for each user from a catalogue file, live notes during a lecture, messages to the lecturer, published lecture summaries |
| Transcript and summary | Working demo: live transcript in the browser or an uploaded recording (audio extracted in the browser, transcribed by an AI service), correction of terms from the lecture slides, repair and summary by AI, publishing to the students |
| Homework | Working demo: assignments per course, student submissions (typed, PDF, photo or handwriting), report for the lecturer, similarity between submissions, AI review (lecturer and student, in Hebrew, with an anonymous comparison with the class), repeating mistakes across the class, bulk import |
| Quick polls, student comments | Design documents only |
| Documents | Tools report, SoW, SRS, use cases, components, class and sequence diagrams, testing strategy, demo notes, summary |
| Presentation | A 10-minute in-class presentation with a live demo |

### 4.2 Out of scope

| Item | Reason |
|---|---|
| Biometrics (fingerprint, face) and passkeys | Decided against for privacy |
| Counting people from a class photo | Dropped after the attempts in the tools report (section 3.6); the manual head-count entry and the gap logic remain |
| Moodle / Zoom integration, native apps, Bluetooth / NFC | Not required, or not available in the iPhone browser |
| A database and self-registration | The demo keeps data in memory; the storage classes can be replaced later. Users are not registered by the system: students come from the roster file and lecturers from the course catalogue file |

## 5. Deliverables and acceptance criteria

| # | Deliverable | Accepted when |
|---|---|---|
| D1 | Attendance demo, hosted and reachable from a phone | The lecturer opens a session, a phone scans the QR code, and the check-in appears on the lecturer page. A check-in without location permission is refused. |
| D2 | Cheating scenarios | A second student marked from the same phone (private window) is shown as suspect or refused; a wrong PIN is refused; a photographed old QR code is rejected. All three were exercised on a real phone. |
| D3 | Automated tests | All automated tests pass (133 at the time of writing: attendance scenarios, head count, portal, transcript, slides, homework, passwords and recordings). |
| D4 | Tools report | Every tool has a reason and, where we tried it, a real result, including the failures of the AI service (retired model name, overload, quota). |
| D5 | SRS, use cases, components, diagrams, testing strategy | Every must requirement of the attendance tool is traced to a use case and to a test (traceability tables). |
| D6 | Demo script | A rehearsed 10-minute script with a fallback if the network fails. |
| D7 | Summary | Lessons learned and the known limits. |

## 6. Roles

| Person | Responsibility |
|---|---|
| Maayan Cohen and Talya Elmaliah | Both authors worked on all parts together: the design documents, the attendance demo, the tests, the tools report, and the presentation. |

## 7. Schedule

The assignment is due on 26 November 2026.

| Date | Milestone |
|---|---|
| Done | README, use cases, SRS, components, diagrams, testing strategy, attendance demo on a real iPhone, tools report, SoW, demo script |
| Done (to 22 Nov) | Course portal, transcript and recording upload, homework tool with AI review, English interface, polls and comments designs, documents updated for what was built, merge into `main` |
| 23-24 Nov | Consistency check of all documents and the traceability tables; summary |
| 25 Nov | Full rehearsal of the 10-minute demo on the university network |
| 26 Nov | Submission and presentation |

## 8. Assumptions and constraints

- Students have a smartphone with a camera and a browser that supports location.
- The demo runs on a free hosting plan: it sleeps after inactivity and forgets its data. We open the page a few minutes before the demo and export the sheet before closing.
- Everything is free to use. No paid services. The AI features use the free tier of the Gemini API, which has quotas and may use submitted data to improve the service, so real student data would need a paid tier or an agreement.
- AI answers are suggestions for a person to check; they are never a grade.
- The roster is a file provided by the lecturer.

## 9. Changes from the original plan

| Change | Reason |
|---|---|
| Photo head-count dropped from the demo | The free vision service did not give a stable result (tools report, 3.6). |
| Course portal, transcript with recordings and the homework tool built as working demos | The first plan had designs and one small experiment each; the experiments turned into working features |
| Interface changed to English | A decision of the authors; Hebrew content (names, AI reviews, transcripts) is still displayed correctly |
| Personal PIN added | To tie a phone to a person without biometrics, so a private window no longer helps a cheater. |
| Location became mandatory | A student who refuses location can no longer mark attendance. |
| Crowd-based location check added | Indoor GPS is accurate to tens of meters; the group of students gives a better centre than one point. |

All documents now describe what was built. In the class and sequence diagrams (document 06) the first design stays in sections 1.4, 1.5, 2.4 and 2.5, and sections 1.6, 2.6 and 2.7 show the demo as built.

## 10. Risks

| Risk | Effect | Handling |
|---|---|---|
| The hosted server sleeps or restarts before the demo | Data lost, a 50 s delay | Open the page early; export before closing; keep a local copy of the demo as a fallback |
| Network or location problems in the classroom | Demo cannot be shown live | Rehearse on the university network; prepare screenshots as a last resort |
| Indoor location is inaccurate | A real student looks far away | A wide radius, the QR code, and weak signals instead of automatic rejection |
| A student shares a PIN or the first person to enter an ID sets the PIN | A cheat is not detected | Other signals (same coordinates, same phone profile); lecturer can reset a PIN; the limits are documented |
| The AI service is overloaded, retired or out of quota during the demo | AI review, summary and transcription fail | The page shows the exact reason; a live test button for the lecturer; choose a model with free quota before the demo; recorded fallback |
| Student data is sent to an external AI service | Privacy | Names and ID numbers are removed first, classmates are anonymous, the screens say so; use a paid tier for real data |
| Not enough time for all documents | Incomplete submission | The schedule above puts the attendance documents first |

## 11. Approval

To be signed (name and date) by both authors.
