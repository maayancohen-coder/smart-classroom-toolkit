# smart-classroom-toolkit

Smart classroom toolkit: reliable attendance verification and interactive tools for lecturers and students.

Course: Intro to Software Engineering (I2SE) - Exercise 2

## The problem

Teaching tools in class are often slow, easy to fake, or require installing yet another app. The clearest example is attendance. Today students fill it in themselves, in one of two ways:

- **A QR code or link** shown in class. A student can photograph it and send it to a friend who is not in the room.
- **A location-based app** that only shows the student is "in the area", so someone near the building, but not in the lecture, can still mark attendance.

Either way the lecturer receives a list but cannot tell how many students were actually in the room. Beyond attendance, lecturers also lack a lightweight way to hear from students during a lecture.

## Users

| User | What they need |
|---|---|
| **Lecturer / teacher** | Open a lecture, get a trustworthy attendance sheet, and collect quick feedback from the class |
| **Student** | Take part in seconds from their own phone, with nothing to install |

## The solution

A web app (works on iPhone and Android, no installation) with one core tool and two light ones.

### Core: reliable attendance

1. **The lecturer opens a lecture.** The system shows a QR code on the classroom screen. The code changes every few seconds, so a photo of it quickly becomes useless.
2. **The student scans the code** with the phone camera. The system verifies the attendance using the student's **location**, which must be inside the classroom area.
3. **The lecturer uploads a photo of the class.** The system **counts the people in the photo** and sends the lecturer the **gap** between the number of students who marked attendance and the number of people actually in the room.

### Light tools

- **Quick polls:** the lecturer creates a question in seconds and students answer from their phone.
- **Student comments and suggestions:** students send short comments during or after the lecture.

## Scope

### In scope

- Rotating QR code for each lecture
- Location check against the classroom
- Binding each phone to one student, so one phone cannot mark attendance for several students
- Counting people in a class photo and reporting the gap
- Attendance sheet for the lecturer (online view and Excel/CSV export)
- Quick polls and student comments (planned at a lighter level than attendance)
- Web app only

### Out of scope (and why)

| Item | Reason |
|---|---|
| Face recognition | Privacy; counting people is enough for the goal |
| Moodle / Zoom integration | Not required by the exercise |
| ML summary of lecture recordings | Needs transcription and a model; planned as future work |
| LLM review of homework, with comparison to other students | Raises privacy questions; planned as future work |
| Bluetooth / NFC | Not available in the iPhone browser |

## Known limitations

- The photo count tells the lecturer **how many** are missing, not **who**. For who, the system ranks students by the other signals (location, device, scan timing).
- Indoor location is only accurate to tens of meters, so it proves "in the building", not "in this room". The QR code and the photo count cover that gap.
- Students in the back rows may be hard to count, so the gap has a tolerance.

## Documentation

Planned documents, in order (see `docs/`):

1. Tools report
2. Statement of Work (SoW)
3. Software Requirements Specification (SRS)
4. Use cases and user stories
5. Software components
6. Class and sequence diagrams
7. Testing strategy
8. Implementation approach and demo notes
9. Summary

## Authors

- Maayan Cohen
- Talya Elmaliah
