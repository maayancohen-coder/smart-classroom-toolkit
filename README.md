# smart-classroom-toolkit

Smart classroom toolkit: reliable attendance verification and AI-assisted tools for lecturers and students.

Course: Intro to Software Engineering (I2SE) - Exercise 2

**Live site:** https://attendance-demo-2lrh.onrender.com (free server: the first visit after a quiet period can take about a minute)

**Explainer video (2 min, English, narrated):** [docs/media/course-hub-video.mp4](docs/media/course-hub-video.mp4) - the problem, the product, the process and what failed on the way.

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

A web app named **Course Hub** (works on iPhone and Android, no installation) made of five tools. The demo is hosted on Render and has a portal: students and lecturers log in with a personal password, see their courses, and each course page holds the lectures, notes, messages, summaries and homework.

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

**Built in the demo.** The lecturer dictates live in Chrome, or uploads the recording of a lecture (audio or video), also of a lecture that already took place. The browser cuts the sound into parts and an AI speech model transcribes them. Technical terms are corrected from a glossary (the lecture slides or the lecturer's list), and the lecturer can undo any correction that is wrong, repair the text with the AI, edit it, and write a summary with the AI. When the lecturer publishes the lecture, students see the summary, the full transcript and, if the lecturer chose to keep it, a player for the recording (up to 100 MB).

### 5. Homework review (AI)

**Built in the demo.** The lecturer creates an assignment with the questions and the teacher's solution, and students (or the lecturer, in bulk) upload submissions as PDF, image or text. Names and ID numbers are removed before anything is sent to the AI. The lecturer gets a review in Hebrew, similarity to other submissions and a list of mistakes shared by several students. A student sees their own submission and the file, and gets feedback only when at least three other submissions exist.

## Scope

### Depth of planning

| Level | Tools | What we deliver |
|---|---|---|
| **1: demo + full design** | Reliable attendance | Full design documents and a working demo (138 automated tests) |
| **2: full design** | Quick polls, student comments | Full design documents. Of these, only live notes from students and messages to the lecturer are built; polls are design only |
| **3: design + experiment, then built** | Transcript and summary, homework review | Use cases, components, chosen tools, an experiment, and a working version in the demo that uses an external AI service |

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
- Speech-to-text accuracy on Hebrew lectures with English technical terms was not measured, so we make no claim about it. The glossary correction can be wrong, which is why the lecturer can undo it.
- The data is used in memory and saved to Firebase Cloud Firestore (free plan) a few seconds after every change, so lectures, recordings, assignments and passwords come back after a restart. Changes in the last seconds before a crash can be lost.
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
