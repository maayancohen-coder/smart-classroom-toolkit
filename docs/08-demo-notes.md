# Implementation Approach and Demo Notes

Status: v2

## 1. Implementation approach (KISS)

The live demo shows the attendance tool; the portal, the transcript and the homework tool with AI review are shown briefly (section 7). Everything is kept as small as the design allows.

| Decision | Choice | Why |
|---|---|---|
| Structure | Flask routes only in `app.py`; all logic in the `attendance` package | The web layer can change without touching the rules |
| Rules | One `AttendanceCheck` class per rule (Strategy); an evaluator combines them | A new rule is a new class; each rule has its own test |
| Decision | One strong failure, or two weak failures, makes a check-in suspect | Avoids accusing a student because of one noisy signal |
| Storage | In memory behind repository classes | No database to set up; replaceable later |
| Hosting | Render free plan, branch `demo-deploy` | Works from a phone on any network, with HTTPS |
| Student feedback | The student sees only "recorded", never the status | A cheater learns nothing about which signal tripped |

Vibe coding: we described the behaviour and the rules to an AI assistant, ran the code on real devices, and corrected it from what we saw (for example, "frozen location" first made real students suspect and became a weak signal). The design documents came first and the code follows them.

## 2. Before the demo

Do all of this in the 15 minutes before the presentation, in the classroom.

1. Open the site address on the laptop, **5 minutes early**. The free server sleeps and needs about 50 seconds to wake up.
2. Open the lecturer link with your own key. Do not show the key on the projector.
3. Open a **new** session. Allow location on the laptop so the classroom point is filled in. Set the radius to 500 m.
4. Put the lecturer page on the projector. The QR code changes every 5 seconds.
5. Phones: location services on for the browser, mobile data or the university Wi-Fi, a private tab ready.
6. Have two students' IDs ready (for example `100000001` and `100000002`) and agree on the PINs you will use.
7. Record a 60-second screen video of the whole flow the day before, as a backup.
8. Change `LECTURER_KEY` in Render to a new value that has not been shown anywhere, and sign in once as the lecturer to choose your personal password (it is forgotten on every deployment). Do not deploy again after this step.
9. In the homework page press **Test the AI service**: it must answer OK in a few seconds. If it does not, change `GEMINI_MODEL` (use **List available models**).
10. Create the sample assignment again (data is erased by a deployment) and import the sample submissions.

## 3. The 10-minute plan

| Time | Part | What to say or show |
|---|---|---|
| 0:00-1:30 | The problem | A shared QR code can be photographed and sent; a location app shows only "near the building". The lecturer gets a list but cannot trust it. |
| 1:30-3:30 | The design | Rotating QR + location + personal PIN + device checks. Show the component diagram and the strong/weak rule. Mention Strategy (checks), Adapter (people counter), Facade (service). |
| 3:30-8:00 | Live demo | See section 4. |
| 8:00-9:30 | Limits and next steps | Indoor GPS is accurate to tens of meters; a PIN can be shared; passkeys as a future upgrade; the photo count we tried and dropped. |
| 9:30-10:00 | Summary | One sentence on what was built and one on what was learned. |

## 4. The live demo, step by step

| # | Action | Expected result |
|---|---|---|
| 1 | Show the lecturer page: the QR code, the progress bar, and the list of students, all "absent". | The code changes every 5 seconds. |
| 2 | Phone A scans the code and the browser asks for location; choose **Don't allow**, and press the check-in button. | The page asks to allow location. No attendance is recorded. |
| 3 | Allow location, enter ID `100000001`, choose a PIN, press the button. | "Attendance recorded". The lecturer page shows the student as present. |
| 4 | **Old QR:** scan a screenshot of the code taken more than 15 seconds earlier. | The page says the code expired. |
| 5 | **Private window:** on the same phone, open a private tab, scan again, enter another student's ID (for example `100000002`) with any new PIN. | The student appears as **suspect**; the notes show the reasons (same phone profile, same coordinates). |
| 6 | **Wrong PIN:** in a private tab, enter student `100000001` with a wrong PIN. | "Wrong personal code". Nothing is recorded. |
| 7 | On the lecturer page, show the reasons and press the Excel button. | The sheet opens with status and reasons per student. |

Steps 2 to 6 were confirmed by hand on a real phone during development and are also covered by automated tests. Step 7 (the Excel export) is covered by automated tests; open the file once by hand before the demo. Rehearse everything once more on the classroom network.

## 5. If something goes wrong

| Problem | Do this |
|---|---|
| The page does not open | The server is waking up. Wait 50 seconds and refresh. |
| "403 Forbidden" on the lecturer page | The key is wrong. Check the `LECTURER_KEY` variable in Render (name and value in the right fields). |
| Everything is empty after a pause | The server restarted and forgot the data. Open a new session. |
| No network at all | Play the recorded video and show the screenshots; explain the same steps. |
| A student is wrongly "suspect" | Explain it as the design working: the lecturer sees the reasons and decides. |

## 6. Questions we may get

| Question | Short answer |
|---|---|
| What if a student gives a friend the PIN? | Then it is a deliberate act we cannot prevent; other signals (same coordinates, same phone profile) can still flag it. |
| Why no fingerprint or face? | Privacy. A PIN is simple and stores nothing about the body. |
| Why can GPS not tell the exact room? | Indoor accuracy is tens of meters. The rotating QR and the group of students cover the room level. |
| What data is stored? | Student ID, time, coordinates, a hash of the PIN, and the reasons. It is kept in memory in the demo. |
| Why was the photo count dropped? | The free vision service gave no stable result in our tests; the design remains and the manual count works. |
| Does it scale to 200 students? | The checks are cheap; for real use the in-memory storage would be replaced by a database and several servers. |

## 7. Short extra demo (about 2 minutes, only if time allows)

| # | Action | Expected result |
|---|---|---|
| 1 | Open the site, sign in as a student, open a course | The course page lists the homework, a live lecture and published summaries |
| 2 | Submit a typed or scanned solution, open **View my submission** | The status shows Submitted and the file opens |
| 3 | Sign in as the lecturer, open the assignment report, press **AI review** on one student | A Hebrew review with strengths, mistakes and suggestions |
| 4 | Press **Common mistakes (AI)** | The mistakes that repeat across the class and what to re-teach |
| 5 | Open the transcript page of a lecture, show the result of a short recording and the summary | A transcript with corrected terms and a summary that can be published |

If the AI service is slow or fails, show the live test button, read the reason, and continue with the recorded video.

Questions we may get about the AI part: *Is student data sent outside?* Yes, after names and ID numbers are removed; the screens say so; real data would need a paid tier. *Is the AI review a grade?* No, it is a suggestion for a person. *How accurate is it?* We did not measure it; the first runs are in the tools report.
