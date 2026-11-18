# Statement of Work (SoW)

Status: draft v1

## 1. Purpose

This document states what we will deliver for Exercise 2 of Intro to Software Engineering, what is left out, how we will know the work is done, and what could go wrong. It is the agreement between the two authors and the course staff.

## 2. Background

Attendance in class is slow or easy to fake. A shared QR code can be photographed and sent to a friend; a location app only shows that someone is near the building. The project is a web-based teaching toolkit. The attendance tool is the core and has a working demo; the other tools are designed (see the README for the depth of each).

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
| Quick polls, student comments | Full design documents |
| Transcript and summary, homework review | Use cases, components, chosen tools, and one small experiment each |
| Documents | Tools report, SoW, SRS, use cases, components, class and sequence diagrams, testing strategy, demo notes, summary |
| Presentation | A 10-minute in-class presentation with a live demo |

### 4.2 Out of scope

| Item | Reason |
|---|---|
| Biometrics (fingerprint, face) and passkeys | Decided against for privacy |
| Counting people from a class photo | Dropped after the attempts in the tools report (section 3.6); the manual head-count entry and the gap logic remain |
| Moodle / Zoom integration, native apps, Bluetooth / NFC | Not required, or not available in the iPhone browser |
| A database and user accounts | The demo keeps data in memory; the storage classes can be replaced later |

## 5. Deliverables and acceptance criteria

| # | Deliverable | Accepted when |
|---|---|---|
| D1 | Attendance demo, hosted and reachable from a phone | The lecturer opens a session, a phone scans the QR code, and the check-in appears on the lecturer page. A check-in without location permission is refused. |
| D2 | Cheating scenarios | A second student marked from the same phone (private window) is shown as suspect or refused; a wrong PIN is refused; a photographed old QR code is rejected. All three were exercised on a real phone. |
| D3 | Automated tests | All automated scenarios pass (49 at the time of writing). |
| D4 | Tools report | Every tool has a reason and, where we tried it, a real result. |
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
| Done | README, use cases, SRS, components, diagrams, testing strategy, attendance demo on a real iPhone, tools report |
| 18-20 Nov | SoW, demo script, update SRS and tests document for the PIN and the removed photo count |
| 21-23 Nov | Designs for the polls, comments, transcript and homework tools; one small experiment each for the last two |
| 24 Nov | Consistency check of all documents and the traceability tables; summary |
| 25 Nov | Full rehearsal of the 10-minute demo on the university network |
| 26 Nov | Submission and presentation |

## 8. Assumptions and constraints

- Students have a smartphone with a camera and a browser that supports location.
- The demo runs on a free hosting plan: it sleeps after inactivity and forgets its data. We open the page a few minutes before the demo and export the sheet before closing.
- Everything is free to use. No paid services.
- The roster is a file provided by the lecturer.

## 9. Changes from the original plan

| Change | Reason |
|---|---|
| Photo head-count dropped from the demo | The free vision service did not give a stable result (tools report, 3.6). |
| Personal PIN added | To tie a phone to a person without biometrics, so a private window no longer helps a cheater. |
| Location became mandatory | A student who refuses location can no longer mark attendance. |
| Crowd-based location check added | Indoor GPS is accurate to tens of meters; the group of students gives a better centre than one point. |

The README, the SRS (FR-20 to FR-24) and the testing strategy still describe the photo count and must be updated to match this table.

## 10. Risks

| Risk | Effect | Handling |
|---|---|---|
| The hosted server sleeps or restarts before the demo | Data lost, a 50 s delay | Open the page early; export before closing; keep a local copy of the demo as a fallback |
| Network or location problems in the classroom | Demo cannot be shown live | Rehearse on the university network; prepare screenshots as a last resort |
| Indoor location is inaccurate | A real student looks far away | A wide radius, the QR code, and weak signals instead of automatic rejection |
| A student shares a PIN or the first person to enter an ID sets the PIN | A cheat is not detected | Other signals (same coordinates, same phone profile); lecturer can reset a PIN; the limits are documented |
| Not enough time for all documents | Incomplete submission | The schedule above puts the attendance documents first |

## 11. Approval

To be signed (name and date) by both authors.
