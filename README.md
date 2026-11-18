# smart-classroom-toolkit

Smart classroom toolkit: reliable attendance verification and AI-assisted tools for lecturers and students.

Course: Intro to Software Engineering (I2SE) - Exercise 2

## The problem

Teaching tools in class are often slow, easy to fake, or require installing yet another app. The clearest example is attendance. Today students fill it in themselves, in one of two ways:

- **A QR code or link** shown in class. A student can photograph it and send it to a friend who is not in the room.
- **A location-based app** that only shows the student is "in the area", so someone near the building, but not in the lecture, can still mark attendance.

Either way the lecturer receives a list but cannot tell how many students were actually in the room. Beyond attendance, lecturers and students also lack lightweight ways to collect feedback, to get a record of what was said in a lecture, and to get useful feedback on homework.

## Users

| User | What they need |
|---|---|
| **Lecturer / teacher** | Open a lecture, get a trustworthy attendance sheet, collect quick feedback, get a transcript and summary of the lecture |
| **Student** | Take part in seconds from their own phone, with nothing to install, and get feedback on homework |

## The solution

A web app (works on iPhone and Android, no installation) made of five tools.

### 1. Reliable attendance (core)

1. **The lecturer opens a lecture.** The system shows a QR code on the classroom screen. The code changes every few seconds, so a photo of it quickly becomes useless.
2. **The student scans the code** with the phone camera and enters a personal PIN (chosen the first time). The system verifies the attendance using the student's **location**, which must be inside the classroom area and is mandatory: without it, attendance cannot be marked.
3. **Head-count gap.** The lecturer enters the number of people in the room and the system shows the **gap** between that number and the number of check-ins. Counting people automatically from a class photo is part of the design, but was dropped from the demo because we could not get a stable result from a free service.
4. The lecturer receives a sheet (online and Excel/CSV) of students marked present, suspect (with the reasons) or absent.

### 2. Student comments and suggestions

Students send short comments during or after the lecture, anonymously or with their name.

### 3. Quick polls

The lecturer creates a question in seconds and students answer from their phone. An LLM can suggest a question from the current slide.

### 4. Lecture transcript and summary (AI)

The lecturer uploads the lecture recording (for example from Zoom or Meet). The system produces a transcript with a speech-to-text model, corrects technical terms with an LLM using the lecture slides as a glossary, and returns a summary.

### 5. Homework review (AI)

A student or teacher uploads homework and receives a detailed LLM review, including a comparison with other students' work where this is allowed (see the limitations below).

## Scope

### Depth of planning

| Level | Tools | What we deliver |
|---|---|---|
| **1: demo + full design** | Reliable attendance | Full design documents and a working demo |
| **2: full design** | Quick polls, student comments | Full design documents |
| **3: design + a small experiment** | Transcript and summary, homework review | Use cases, components, chosen tools, and one small experiment that shows the tool is feasible |

### Out of scope (and why)

| Item | Reason |
|---|---|
| Face recognition | Privacy; counting people is enough for the goal |
| Moodle / Zoom integration | Not required by the exercise; recordings are uploaded by the lecturer |
| Bluetooth / NFC | Not available in the iPhone browser |
| Native mobile apps | The brief asks for a simple web-based app |

## Known limitations

- The head count tells the lecturer **how many** are missing, not **who**. For who, the system ranks students by the other signals (location, device, PIN, scan timing).
- Indoor location is only accurate to tens of meters, so it proves "in the building", not "in this room". The rotating QR code and the check of the location against the class group cover that gap.
- If a photo is used, students in the back rows may be hard to count, so the gap has a tolerance (10% of the check-ins).
- A student can give the personal PIN to a friend, and the first person to enter a student's ID chooses the PIN (the lecturer can reset it). The system flags some of these cases but does not claim to stop all of them.
- Speech-to-text accuracy on Hebrew lectures with English technical terms must be measured, not assumed.
- LLM output can be wrong. Summaries and reviews are presented as suggestions for a human to check.
- Recordings contain students' voices, and homework comparison involves other students' work. Both need consent and privacy rules, described in the SRS.

## Documentation

Documents, in order (in `docs/`):

1. Tools report (`01-tools-report.md`)
2. Statement of Work (`02-sow.md`)
3. Software Requirements Specification (`03-srs.md`)
4. Use cases and user stories (`04-use-cases.md`)
5. Software components (`05-components.md`)
6. Class and sequence diagrams (`06-class-and-sequence-diagrams.md`, images in `docs/diagrams/`)
7. Testing strategy (`07-testing-strategy.md`)
8. Implementation approach and demo notes (`08-demo-notes.md`)
9. Summary (`09-summary.md`)

## Authors

- Maayan Cohen
- Talya Elmaliah
