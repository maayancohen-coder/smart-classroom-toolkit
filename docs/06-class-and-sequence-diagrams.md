# Class and Sequence Diagrams

Status: draft v1

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
        +checkIn(nonce, deviceId, studentId, location) CheckIn
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
    class NetworkCheck

    AttendanceCheck <|-- TokenFreshnessCheck
    AttendanceCheck <|-- DeviceBindingCheck
    AttendanceCheck <|-- GeofenceCheck
    AttendanceCheck <|-- LocationSpoofCheck
    AttendanceCheck <|-- NetworkCheck

    DeviceBindingCheck --> DeviceRegistry
    AttendanceEvaluator o-- "1..*" AttendanceCheck
    AttendanceEvaluator ..> CheckContext
    AttendanceCheck ..> CheckContext

    AttendanceService --> TokenService
    AttendanceService --> TicketStore
    AttendanceService --> AttendanceEvaluator
    AttendanceService --> DeviceRegistry
    AttendanceService --> Roster
    TicketStore "1" o-- "*" CheckInTicket
```

How the evaluator decides: it runs every check. If at least one **strong** check failed, or at least two **weak** checks failed, the status is `SUSPECT`. Otherwise it is `PRESENT`. Strong checks: device binding, geofence, location spoofing. Weak checks: token freshness, campus network.

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
    Student->>SC: Enter student ID (first time) and allow location
    SC->>API: POST /api/checkin (ticket, student ID, location)
    API->>AS: checkIn(ticket, deviceId, studentId, location)
    AS->>TK: consume(ticket)
    TK-->>AS: ticket (single use)
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

## 3. Design patterns and principles

| Where | Pattern or principle | Why |
|---|---|---|
| `AttendanceCheck` and its five subclasses | **Strategy** | Each signal is a separate algorithm behind one interface. A new check is a new class and nothing else changes (FR-19, NFR-23). |
| `PeopleCounter`, `SpeechToText`, `LLMClient`, `ReportExporter` | **Adapter / dependency inversion** | The system depends on our interface. A provider is replaced, or faked in a test, without changing the rest. |
| `AttendanceService`, `MediaService`, `HomeworkService` | **Facade** | The API layer calls one simple entry point per tool. |
| `DeviceRegistry`, `TicketStore`, `Roster` | **Repository** | Storage is hidden. In the demo it is in memory, and it can become a database later. |
| `AttendanceEvaluator` | **Single responsibility** | It only combines results. It does not know how any check works. |
| `Fake...` classes | **Testability** | Every external service has a fake, used by the tests in document 07. |

## 4. From requirements to classes

| Requirement | Class |
|---|---|
| FR-5 to FR-7 (rotating QR) | `TokenService` |
| FR-8 to FR-11 (check-in) | `AttendanceService`, `TicketStore`, `Roster` |
| FR-12, FR-13 (checks and decision) | `AttendanceCheck` subclasses, `AttendanceEvaluator` |
| FR-17, FR-18 (device binding) | `DeviceRegistry`, `DeviceBindingCheck` |
| FR-20 to FR-24 (head count) | `PeopleCounter`, `HeadCountComparer`, `GapReport` |
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
