# Software Components

Status: draft v1

## 1. Overview

The system is a web application with two browser clients (student and lecturer), one server, a data store, and three external AI services. Everything the user sees runs in the browser, so nothing has to be installed.

```mermaid
flowchart LR
    subgraph Browsers
        S[Student web client]
        L[Lecturer web client]
    end

    subgraph Server["Web server"]
        API[API layer]
        SES[Session service]
        ATT[Attendance service]
        POL[Poll and comment service]
        MED[Media service]
        HW[Homework service]
        REP[Report exporter]
        JOB[Background job runner]
    end

    DB[(Data store)]
    FS[(Temporary file storage)]

    subgraph External["External AI services"]
        ASR[Speech-to-text]
        LLM[LLM]
        CNT[People counter]
    end

    S --> API
    L --> API
    API --> SES
    API --> ATT
    API --> POL
    API --> MED
    API --> HW
    API --> REP
    ATT --> SES
    ATT --> CNT
    MED --> JOB
    HW --> JOB
    JOB --> ASR
    JOB --> LLM
    POL --> LLM
    SES --> DB
    ATT --> DB
    POL --> DB
    MED --> DB
    HW --> DB
    REP --> DB
    MED --> FS
    HW --> FS
    ATT --> FS
```

## 2. Components and responsibilities

### 2.1 Clients (browser)

| Component | Responsibility | Requirements |
|---|---|---|
| **Student web client** | Check-in page opened from the QR code; asks for student ID the first time; reads the phone location; polls and comments; homework upload and review | FR-8 to FR-11, FR-29 to FR-33, FR-40 |
| **Lecturer web client** | Opens and closes a session; shows the rotating QR code; live attendance sheet; photo upload; polls, comments, recordings and homework | FR-1 to FR-7, FR-20 to FR-28, FR-34 to FR-43 |

### 2.2 Server components

| Component | Responsibility | Requirements |
|---|---|---|
| **API layer** | Routes requests, checks that lecturer functions are called only by an authenticated lecturer, limits request rate, returns JSON and pages | NFR-3, NFR-6 |
| **Session service** | Creates and closes sessions; holds the session secret, classroom location, radius and trusted network; loads the class roster | FR-1 to FR-4 |
| **Attendance service** | Generates and verifies rotating tokens; creates check-in tickets; runs the attendance checks and the evaluator; keeps the device binding; computes the head-count gap | FR-5 to FR-24 |
| **Report exporter** | Builds the attendance sheet and exports it to Excel and CSV | FR-25 to FR-28 |
| **Poll and comment service** | Polls, answers and comments (named or anonymous); asks the LLM for a poll question from a slide | FR-29 to FR-33 |
| **Media service** | Accepts recordings and slides; extracts audio from video; starts a transcription job; stores the transcript and the summary | FR-34 to FR-39 |
| **Homework service** | Accepts homework; starts a review job; compares submissions of one assignment (lecturer only) | FR-40 to FR-43 |
| **Background job runner** | Runs long tasks (transcription, review, comparison) outside the request so the site stays responsive; supports retry | NFR-14, NFR-20 |

### 2.3 Data and storage

| Component | Responsibility |
|---|---|
| **Data store** | Sessions, roster, check-ins with reasons, device bindings, polls and answers, comments, transcripts, summaries, reviews |
| **Temporary file storage** | Uploaded photos, recordings and homework files. A class photo is deleted right after counting. Other files are deleted after processing unless the lecturer keeps them. |

### 2.4 External services

| Service | Used for | Called by |
|---|---|---|
| **Speech-to-text** | Raw transcript of a lecture | Background job runner |
| **LLM** | Transcript correction with slides as glossary, summary, homework review and comparison, poll question suggestion | Background job runner, Poll service |
| **People counter** | Number of people in a class photo | Attendance service |

Each external service is accessed through an **adapter** (an interface owned by us), so a provider can be replaced without changing the rest of the system. The tools report selects the actual providers.

## 3. The attendance service in more detail

This is the core of the system, so it is split into smaller parts. These parts become the classes in the class diagram (document 06).

| Part | Responsibility |
|---|---|
| **Token service** | Creates a signed token for a time slot and verifies a token within the allowed window |
| **Ticket store** | Creates single-use check-in tickets and expires them |
| **Attendance checks** | One independent check per signal: token freshness, device binding, classroom location, location plausibility, campus network. All implement one interface. |
| **Evaluator** | Combines the results of the checks into present or suspect |
| **Device registry** | Binds a phone to one student |
| **Head-count comparer** | Compares the number of check-ins with the counted people and finds the most suspect check-ins when the gap exceeds the tolerance |

## 4. Main interfaces between components

| Between | Interface (summary) |
|---|---|
| Student client and API | `GET /c/{session}/{slot}/{signature}` opens the check-in page; `POST /api/checkin` sends the ticket, student ID and location |
| Lecturer client and API | Open and close a session; get the current QR; get the attendance report; upload a photo; export; polls, comments, recordings, homework |
| Attendance service and people counter | `count(image) -> number of people` |
| Background job runner and ASR | `transcribe(audio, language) -> transcript` |
| Background job runner and LLM | `complete(instructions, content) -> text` |

## 5. Deployment

- A single server process serves both clients and runs the background jobs. This is enough for one class and for the demo.
- The server must be reachable over **HTTPS**, because phones allow location access only on secure pages. For the demo, a secure tunnel to the lecturer's laptop is used.
- Configuration (thresholds, provider keys) is read from the environment and not stored in code.

## 6. Design decisions

| Decision | Reason |
|---|---|
| One server instead of separate services | KISS: one class, one demo, fewer parts that can fail |
| Adapters around every external service | A provider can be replaced and tested with a fake |
| Heavy work in background jobs | A one-hour recording must not block check-ins |
| Each attendance check is a separate component | New signals are added without touching the others (FR-19, NFR-23) |
| Photos deleted after counting | Privacy (NFR-7) |
