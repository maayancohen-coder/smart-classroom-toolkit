# Class and Sequence Diagrams

Status: v2 (sections 1.6, 2.6 and 2.7 show the transcript, recording and homework tools as they were built)

This document turns the components (document 05) into classes and shows how objects talk to each other in the main scenarios. The attendance tool is designed in full detail. The other tools are shown at the level needed to see how they fit.

Diagrams are written in Mermaid, so GitHub shows them directly. Rendered SVG copies, for slides and printing, are in `docs/diagrams/` (list in section 5).

## 1. Class diagrams

### 1.1 Attendance: domain model

The data that the system keeps about a lecture and its attendance.

```mermaid
classDiagram
    class LectureSession {
        +String sessionId
        +String course
        +float centerLat
        +float centerLng
        +float radiusMeters
        +List~String~ trustedNetworks
        +bool closed
        +hasGeofence() bool
    }
    class Student {
        +String studentId
        +String name
    }
    class Roster {
        +get(studentId) Student
        +all() List~Student~
    }
    class CheckIn {
        +datetime at
        +String deviceId
        +String fingerprint
        +float tokenAgeSeconds
        +float distanceMeters
        +bool addedManually
        +failedReasons() List~String~
    }
    class AttendanceStatus {
        <<enumeration>>
        PRESENT
        SUSPECT
        ABSENT
    }
    class CheckResult {
        +String checkName
        +bool passed
        +bool strong
        +String reason
    }
    class LocationReport {
        +bool denied
        +best() LocationSample
    }
    class LocationSample {
        +float lat
        +float lng
        +float accuracy
        +float timestamp
    }

    Roster "1" o-- "*" Student
    LectureSession "1" *-- "0..*" CheckIn
    CheckIn "*" --> "1" Student
    CheckIn "1" *-- "1..*" CheckResult
    CheckIn --> AttendanceStatus
    CheckIn --> LocationSample
    LocationReport "1" *-- "0..*" LocationSample
```

### 1.2 Attendance: check-in logic

The classes that decide whether a check-in is present or suspect. This is the core of the design.

```mermaid
classDiagram
    class AttendanceService {
        +openSession(course, lat, lng, radius) LectureSession
        +closeSession(session)
        +currentQr(session) QrCode
        +scan(sessionId, slot, signature) CheckInTicket
        +checkIn(nonce, deviceId, studentId, location, pin, fingerprint) CheckIn
        +addManually(session, studentId) CheckIn
        +report(session) List~ReportRow~
    }
    class TokenService {
        -int periodSeconds
        -int gracePeriods
        +current(secret, sessionId) Token
        +verify(secret, sessionId, slot, signature) TokenVerdict
    }
    class TicketStore {
        +newTicket(sessionId, tokenAge) CheckInTicket
        +consume(nonce, ttl) CheckInTicket
    }
    class CheckInTicket {
        +String nonce
        +String sessionId
        +float tokenAgeSeconds
        +bool used
    }
    class DeviceRegistry {
        +studentForDevice(deviceId) String
        +deviceForStudent(studentId) String
        +bindIfFree(studentId, deviceId) bool
        +reset(studentId)
    }
    class PinStore {
        +checkOrSet(studentId, pin) Verdict
        +reset(studentId)
    }
    class ClassCluster {
        +float centerLat
        +float centerLng
        +float radiusMeters
        +isOutside(lat, lng, accuracy) bool
    }
    class AttendanceEvaluator {
        +evaluate(context) Evaluation
    }
    class CheckContext {
        +LectureSession session
        +Student student
        +String deviceId
        +CheckInTicket ticket
        +LocationReport location
        +String ip
        +String fingerprint
        +bool pinVerified
    }
    class AttendanceCheck {
        <<abstract>>
        +String name
        +bool strong
        +run(context) CheckResult
    }
    class TokenFreshnessCheck
    class DeviceBindingCheck
    class GeofenceCheck
    class LocationSpoofCheck
    class FrozenLocationCheck
    class DuplicateCoordinatesCheck
    class StaleLocationCheck
    class SharedFingerprintCheck
    class RapidRepeatCheck
    class NetworkCheck

    AttendanceCheck <|-- TokenFreshnessCheck
    AttendanceCheck <|-- DeviceBindingCheck
    AttendanceCheck <|-- GeofenceCheck
    AttendanceCheck <|-- LocationSpoofCheck
    AttendanceCheck <|-- FrozenLocationCheck
    AttendanceCheck <|-- DuplicateCoordinatesCheck
    AttendanceCheck <|-- StaleLocationCheck
    AttendanceCheck <|-- SharedFingerprintCheck
    AttendanceCheck <|-- RapidRepeatCheck
    AttendanceCheck <|-- NetworkCheck

    DeviceBindingCheck --> DeviceRegistry
    AttendanceEvaluator o-- "1..*" AttendanceCheck
    AttendanceEvaluator ..> CheckContext
    AttendanceCheck ..> CheckContext

    AttendanceService --> TokenService
    AttendanceService --> TicketStore
    AttendanceService --> AttendanceEvaluator
    AttendanceService --> DeviceRegistry
    AttendanceService --> PinStore
    AttendanceService ..> ClassCluster
    AttendanceService --> Roster
    TicketStore "1" o-- "*" CheckInTicket
```

How the evaluator decides: it runs every check. If at least one **strong** check failed, or at least two **weak** checks failed, the status is `SUSPECT`. Otherwise it is `PRESENT`. Strong checks: device binding, geofence, location plausibility, same coordinates as another student. Weak checks: token freshness, frozen location, stale location reading, same phone profile, repeated check-in from the same phone profile and network, campus network.

Two things happen outside the evaluator. Before it runs, `AttendanceService` refuses a check-in that has no location (when the class has a location) and refuses a wrong PIN, using `PinStore`; a correct PIN also tells `DeviceBindingCheck` that a new phone is not a cheat signal. When the report is built, `ClassCluster` (the centre and spread of the check-ins of the class) marks a check-in suspect if its location is clearly outside the group, even inside the lecturer's radius.

### 1.3 Attendance: head-count gap and export

```mermaid
classDiagram
    class HeadCountComparer {
        -float tolerance
        +compare(session, countedPeople) GapReport
    }
    class GapReport {
        +int checkIns
        +int counted
        +int gap
        +bool toleranceExceeded
        +List~CheckIn~ mostSuspect
    }
    class PeopleCounter {
        <<interface>>
        +count(image) int
    }
    class ModelPeopleCounter
    class FakePeopleCounter
    class ReportExporter {
        <<interface>>
        +export(rows) bytes
    }
    class CsvExporter
    class XlsxExporter
    class AttendanceService

    PeopleCounter <|.. ModelPeopleCounter
    PeopleCounter <|.. FakePeopleCounter
    ReportExporter <|.. CsvExporter
    ReportExporter <|.. XlsxExporter
    AttendanceService --> PeopleCounter
    AttendanceService --> HeadCountComparer
    AttendanceService --> ReportExporter
    HeadCountComparer ..> GapReport
```

`FakePeopleCounter` returns a number chosen by the test, so the gap logic can be tested without any image.

### 1.4 Polls and comments

```mermaid
classDiagram
    class Poll {
        +String pollId
        +String question
        +bool open
        +List~PollOption~ options
    }
    class PollOption {
        +String text
        +int votes
    }
    class PollAnswer {
        +String studentId
        +String optionId
    }
    class Comment {
        +String text
        +bool anonymous
        +String authorId
        +datetime at
    }
    class PollService {
        +create(session, question, options) Poll
        +answer(poll, studentId, optionId)
        +close(poll)
        +results(poll) List~PollOption~
    }
    class CommentService {
        +submit(session, text, studentId, anonymous) Comment
        +list(session) List~Comment~
    }
    class QuestionSuggester {
        +suggest(slideText) String
    }
    class LLMClient {
        <<interface>>
        +complete(instructions, content) String
    }

    Poll "1" *-- "2..*" PollOption
    Poll "1" o-- "*" PollAnswer
    PollService --> Poll
    CommentService --> Comment
    PollService --> QuestionSuggester
    QuestionSuggester --> LLMClient
```

For an anonymous comment `authorId` is left empty, so the system cannot show who wrote it (FR-33). A student can answer a poll once: `PollService.answer` rejects a second answer from the same `studentId`.

### 1.5 AI services: transcript, summary and homework

```mermaid
classDiagram
    class MediaService {
        +submit(session, file, slides) Job
        +transcript(session) Transcript
    }
    class AudioExtractor {
        +extract(videoFile) AudioFile
    }
    class TranscriptCorrector {
        +correct(rawText, glossary) String
    }
    class Summarizer {
        +summarize(text) String
    }
    class Transcript {
        +String rawText
        +String correctedText
        +String summary
        +String language
    }
    class JobRunner {
        +start(job)
        +status(jobId) JobStatus
        +retry(jobId)
    }
    class Job {
        +String jobId
        +JobStatus status
        +String error
    }
    class SpeechToText {
        <<interface>>
        +transcribe(audio, language) String
    }
    class LLMClient {
        <<interface>>
        +complete(instructions, content) String
    }
    class RemoteSpeechToText
    class FakeSpeechToText
    class RemoteLLMClient
    class FakeLLMClient
    class HomeworkService {
        +review(submission, assignment) Review
        +compare(assignment) ComparisonReport
    }
    class Submission {
        +String submissionId
        +String studentId
        +String assignmentId
    }
    class Review {
        +List~String~ strengths
        +List~String~ mistakes
        +List~String~ suggestions
    }

    MediaService --> AudioExtractor
    MediaService --> JobRunner
    MediaService --> TranscriptCorrector
    MediaService --> Summarizer
    MediaService --> SpeechToText
    MediaService ..> Transcript
    JobRunner "1" o-- "*" Job
    TranscriptCorrector --> LLMClient
    Summarizer --> LLMClient
    HomeworkService --> LLMClient
    HomeworkService --> JobRunner
    HomeworkService ..> Review
    Submission "*" --> "1" HomeworkService
    SpeechToText <|.. RemoteSpeechToText
    SpeechToText <|.. FakeSpeechToText
    LLMClient <|.. RemoteLLMClient
    LLMClient <|.. FakeLLMClient
```

### 1.6 Portal, transcript and homework as built

Sections 1.4 and 1.5 are the first design. In the demo the AI tools were built differently, to fit a free server: there is no background job runner, because the browser sends the recording in parts and the server answers each part directly; and one `Transcriber` adapter (Gemini, with a Claude variant) reads scans, transcribes audio and completes text. This diagram shows what exists in the code.

```mermaid
classDiagram
    class Catalog {
        +get(courseId) Course
        +forStudent(studentId) List~Course~
        +forLecturer(lecturerId) List~Course~
    }
    class Course {
        +String courseId
        +String name
        +hasStudent(studentId) bool
    }
    class LectureSession {
        +String courseId
        +bool closed
        +String transcriptRaw
        +String transcriptCorrected
        +String summaryAi
        +bool summaryPublished
        +bytes recording
    }
    class Transcriber {
        <<interface>>
        +transcribe(data, mime) String
        +transcribeAudio(data, mime) String
        +complete(prompt) String
    }
    class GeminiTranscriber
    class HomeworkStore {
        +create(course, title) Assignment
        +submit(assignment, studentId, name, filename, text)
    }
    class Assignment {
        +String title
        +String questionsText
        +String solutionText
        +Map submissions
    }
    class Submission {
        +String text
        +bytes original
        +String mime
    }
    class TranscriptCorrector {
        +parseGlossary(text) List~String~
        +correctTranscript(raw, terms) Correction
    }
    class PinStore {
        +checkOrSet(key, pin) Verdict
    }

    Catalog "1" o-- "*" Course
    Course "1" <-- "*" LectureSession
    Course "1" <-- "*" Assignment
    HomeworkStore "1" o-- "*" Assignment
    Assignment "1" *-- "*" Submission
    GeminiTranscriber ..|> Transcriber
    LectureSession ..> TranscriptCorrector
    LectureSession ..> Transcriber
    Assignment ..> Transcriber
    PinStore ..> Course
```

The data is kept in memory and saved to Firestore after every change, so it survives a restart.

## 2. Sequence diagrams

### 2.1 Open a lecture and show the rotating QR code (UC1, UC2)

```mermaid
sequenceDiagram
    actor Lecturer
    participant LC as Lecturer client
    participant API
    participant AS as AttendanceService
    participant TS as TokenService

    Lecturer->>LC: Open lecture (course, location)
    LC->>API: POST /api/session
    API->>AS: openSession(course, lat, lng, radius)
    AS-->>API: LectureSession
    API-->>LC: session id
    loop every few seconds
        LC->>API: GET qr
        API->>AS: currentQr(session)
        AS->>TS: current(secret, sessionId)
        TS-->>AS: token (slot, signature)
        AS-->>API: QR address
        API-->>LC: QR address
        LC-->>Lecturer: show QR code
    end
```

### 2.2 Student marks attendance (UC3)

```mermaid
sequenceDiagram
    actor Student
    participant SC as Student client
    participant API
    participant AS as AttendanceService
    participant TS as TokenService
    participant TK as TicketStore
    participant EV as AttendanceEvaluator
    participant CH as AttendanceCheck
    participant DR as DeviceRegistry
    participant PS as PinStore

    Student->>SC: Scan QR code
    SC->>API: GET /c/session/slot/signature
    API->>AS: scan(sessionId, slot, signature)
    AS->>TS: verify(secret, sessionId, slot, signature)
    alt token invalid or expired
        TS-->>AS: invalid
        AS-->>API: error
        API-->>SC: please scan again
    else token valid
        TS-->>AS: valid, token age
        AS->>TK: newTicket(sessionId, tokenAge)
        TK-->>AS: ticket
        AS-->>API: ticket
        API-->>SC: check-in page
    end
    Student->>SC: Enter student ID and personal PIN, allow location
    SC->>API: POST /api/checkin (ticket, student ID, PIN, location, phone profile)
    API->>AS: checkIn(ticket, deviceId, studentId, location, pin, fingerprint)
    AS->>TK: consume(ticket)
    TK-->>AS: ticket (single use)
    alt no location although the class has one
        AS-->>API: refused, ticket stays valid
        API-->>SC: please allow location
    else location given
        AS->>PS: checkOrSet(studentId, pin)
        alt wrong PIN or locked
            PS-->>AS: wrong / locked
            AS-->>API: refused, ticket stays valid
            API-->>SC: wrong code
        else first PIN or correct PIN
            PS-->>AS: set / ok
        end
    end
    AS->>EV: evaluate(context)
    loop each check
        EV->>CH: run(context)
        CH-->>EV: CheckResult
    end
    EV-->>AS: status and results
    AS->>DR: bindIfFree(studentId, deviceId)
    AS-->>API: CheckIn stored
    API-->>SC: attendance recorded
    SC-->>Student: Done (status is not shown)
```

### 2.3 Head-count gap from a class photo (UC4)

```mermaid
sequenceDiagram
    actor Lecturer
    participant LC as Lecturer client
    participant API
    participant AS as AttendanceService
    participant PC as PeopleCounter
    participant HC as HeadCountComparer

    Lecturer->>LC: Upload class photo
    LC->>API: POST photo
    API->>AS: headCount(session, photo)
    AS->>PC: count(photo)
    PC-->>AS: number of people
    AS->>AS: delete photo, keep only the number
    AS->>HC: compare(session, counted)
    HC-->>AS: GapReport
    AS-->>API: GapReport
    API-->>LC: gap and most suspect check-ins
    LC-->>Lecturer: show gap
```

### 2.4 Transcript and summary of a recording (UC13)

```mermaid
sequenceDiagram
    actor Lecturer
    participant LC as Lecturer client
    participant API
    participant MS as MediaService
    participant JR as JobRunner
    participant AE as AudioExtractor
    participant ST as SpeechToText
    participant TC as TranscriptCorrector
    participant SU as Summarizer

    Lecturer->>LC: Upload recording and slides
    LC->>API: POST recording
    API->>MS: submit(session, file, slides)
    MS->>JR: start(job)
    MS-->>API: job id
    API-->>LC: processing started
    JR->>AE: extract(video)
    AE-->>JR: audio
    JR->>ST: transcribe(audio, language)
    ST-->>JR: raw transcript
    JR->>TC: correct(raw transcript, slide terms)
    TC-->>JR: corrected transcript
    JR->>SU: summarize(corrected transcript)
    SU-->>JR: summary
    JR->>MS: store transcript and summary
    LC->>API: GET job status
    API-->>LC: done
    LC-->>Lecturer: show transcript and summary
```

### 2.5 Homework review (UC14)

```mermaid
sequenceDiagram
    actor User as Student or lecturer
    participant C as Web client
    participant API
    participant HS as HomeworkService
    participant JR as JobRunner
    participant LLM as LLMClient

    User->>C: Upload homework
    C->>API: POST homework
    API->>HS: review(submission, assignment)
    HS->>JR: start(job)
    HS-->>API: job id
    JR->>LLM: complete(review instructions, homework text)
    LLM-->>JR: review text
    JR->>HS: store review
    C->>API: GET review
    API-->>C: Review visible only to the uploader
    C-->>User: show review
```

### 2.6 Recording upload, transcript, summary and publishing, as built (UC13)

The lecture can be a live one or one that already took place: the lecturer can add a past lecture to a course by its date, and then upload its recording.

```mermaid
sequenceDiagram
    actor Lecturer
    participant B as Lecturer browser
    participant API
    participant AI as Transcriber (Gemini)
    participant S as LectureSession
    actor Student

    Lecturer->>B: Choose a recording (audio or video), optionally keep it for students
    B->>B: Decode the sound, resample to 16 kHz mono, cut into 6-minute WAV parts
    loop each part
        B->>API: POST recording-chunk
        API->>AI: transcribeAudio(part)
        AI-->>API: text
        API-->>B: text
    end
    B->>API: POST transcript (raw text, glossary, excluded terms)
    API->>S: store raw and glossary-corrected text
    API-->>B: corrected text and list of fixes
    opt Lecturer undoes a wrong fix
        Lecturer->>B: Click the fix
        B->>API: POST transcript (excluded term added)
    end
    opt Repair with AI
        loop each part of the text
            B->>API: POST transcript/ai-fix
            API->>AI: complete(fix prompt)
            AI-->>API: repaired text
        end
        B->>API: POST transcript/save
    end
    opt Summary with AI
        B->>API: POST ai-summary
        API->>AI: complete(summary prompt)
        AI-->>B: draft summary
        Lecturer->>B: Edit and save
        B->>API: POST summary/text
    end
    opt Keep the recording
        B->>API: POST recording-file (up to 100 MB)
        API->>S: keep in memory
    end
    Lecturer->>API: Publish to students
    Student->>API: Open the course page
    API-->>Student: summary, full transcript and the recording player
```

### 2.7 Homework with AI review, as built (UC14)

```mermaid
sequenceDiagram
    actor Student
    actor Lecturer
    participant API
    participant HS as HomeworkStore
    participant AI as Transcriber (Gemini)

    Lecturer->>API: Create assignment (questions, teacher solution, course material)
    API->>HS: create(course, title)
    Student->>API: Upload the submission (PDF, image or text)
    alt the file has selectable text
        API->>API: Extract the text
    else a scan or photo
        API->>AI: transcribe(file)
        AI-->>API: text
    end
    API->>HS: submit(assignment, studentId, text, original file)
    API-->>Student: Submitted (the student can view the text and the file)
    Lecturer->>API: Review submission
    API->>API: Remove names and ID numbers from the text
    API->>AI: complete(review prompt)
    AI-->>API: review in Hebrew
    API-->>Lecturer: review, similarity to other submissions, content check
    Lecturer->>API: Common mistakes (AI)
    API->>AI: complete(prompt with all submissions)
    AI-->>Lecturer: mistakes shared by several students
    opt at least 3 other submissions exist
        Student->>API: Request feedback
        API->>AI: complete(review prompt)
        AI-->>Student: feedback for this student only
    end
```

## 3. Design patterns and principles

| Where | Pattern or principle | Why |
|---|---|---|
| `AttendanceCheck` and its five subclasses | **Strategy** | Each signal is a separate algorithm behind one interface. A new check is a new class and nothing else changes (FR-19, NFR-23). |
| `PeopleCounter`, `SpeechToText`, `LLMClient`, `ReportExporter` | **Adapter / dependency inversion** | The system depends on our interface. A provider is replaced, or faked in a test, without changing the rest. |
| `Transcriber` (`GeminiTranscriber`, `ClaudeTranscriber`) | **Adapter** | The demo reads scans, transcribes audio and completes text through one interface. The model is a setting (`GEMINI_MODEL`). |
| `AttendanceService`, `MediaService`, `HomeworkService` | **Facade** | The API layer calls one simple entry point per tool. |
| `DeviceRegistry`, `TicketStore`, `Roster` | **Repository** | Storage is hidden. In the demo it is in memory, and a snapshot of it is saved to Firestore. |
| `AttendanceEvaluator` | **Single responsibility** | It only combines results. It does not know how any check works. |
| `Fake...` classes | **Testability** | Every external service has a fake, used by the tests in document 07. |

## 4. From requirements to classes

| Requirement | Class |
|---|---|
| FR-5 to FR-7 (rotating QR) | `TokenService` |
| FR-8 to FR-11a (check-in, location required) | `AttendanceService`, `TicketStore`, `Roster` |
| FR-9a, FR-9b (personal PIN) | `PinStore`, `AttendanceService` |
| FR-12, FR-13 (checks and decision) | `AttendanceCheck` subclasses, `AttendanceEvaluator` |
| FR-12a (outside the class group) | `ClassCluster`, `AttendanceService.report` |
| FR-17, FR-18 (device binding) | `DeviceRegistry`, `DeviceBindingCheck` |
| FR-20 to FR-24a (head count; photo counting is designed, not in the demo) | `PeopleCounter`, `HeadCountComparer`, `GapReport` |
| FR-25 to FR-28 (sheet) | `ReportExporter`, `AttendanceService.addManually` |
| FR-29 to FR-33 (polls, comments) | `PollService`, `CommentService`, `Comment` |
| FR-34 to FR-39 (transcript) | `MediaService`, `JobRunner`, `SpeechToText`, `LLMClient` |
| FR-40 to FR-43 (homework) | `HomeworkService`, `Review`, `Submission` |

## 5. Rendered diagrams

| Diagram | File |
|---|---|
| 1.1 Attendance domain model | `diagrams/class-attendance-domain.svg` |
| 1.2 Attendance check-in logic | `diagrams/class-attendance-checkin-logic.svg` |
| 1.3 Head-count gap and export | `diagrams/class-attendance-gap-export.svg` |
| 1.4 Polls and comments | `diagrams/class-polls-comments.svg` |
| 1.5 AI services | `diagrams/class-ai-services.svg` |
| 2.1 Open lecture and QR | `diagrams/seq-open-lecture-qr.svg` |
| 2.2 Student check-in | `diagrams/seq-student-checkin.svg` |
| 2.3 Head-count gap | `diagrams/seq-headcount-gap.svg` |
| 2.4 Transcript and summary | `diagrams/seq-transcript-summary.svg` |
| 2.5 Homework review | `diagrams/seq-homework-review.svg` |
| 1.6 Portal, transcript and homework as built | `diagrams/class-built-portal-ai.svg` |
| 2.6 Recording upload and publishing, as built | `diagrams/seq-recording-upload.svg` |
| 2.7 Homework with AI review, as built | `diagrams/seq-homework-ai-review.svg` |
