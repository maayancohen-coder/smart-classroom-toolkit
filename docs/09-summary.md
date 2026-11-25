# Summary

Status: v2 (updated for what was built)

## 1. What we built

A web-based attendance tool that works from the phone browser with nothing to install, hosted for the demo and tested on a real iPhone:

- a **rotating QR code** (new every 5 seconds, signed, single-use ticket);
- **mandatory location**: without permission the student cannot check in, and a location far from the class group is flagged;
- a **personal PIN** per student, so a phone, a private window or another browser does not make it possible to mark someone else;
- checks that explain themselves: every suspect check-in shows its reasons to the lecturer, and the student never sees the status;
- a live lecturer page with the attendance sheet, a typed head count with the gap, and Excel/CSV export;
- lecturer approval of a suspect check-in (the checks flag, the lecturer decides), with the reasons kept and the approval reversible;
- 133 automated tests, one simulated phone per scenario.

On the same site (Course Hub, English interface) we also built:

- a **course portal**: sign-in for students (student number and personal PIN) and lecturers (key and personal password), a list of courses for each user, live notes during a lecture, messages to the lecturer, and published lecture summaries, transcripts and recordings;
- a **lecture transcript**: live in the browser or from an uploaded recording (the sound is extracted in the browser and sent in parts to an AI service), correction of English terms using the lecture slides, repair and a summary by AI, edited and published by the lecturer;
- a **homework tool**: assignments per course, submissions (typed, PDF, photo or handwriting), a report with similarity and a course-content check, an AI review in Hebrew for the lecturer and for the student (with an anonymous comparison with the class), the mistakes that repeat across the class, bulk import, and opening the submitted file again.

Polls and comments are covered by design documents only.

## 2. What worked

- **Designing before coding.** The use cases and the strong/weak check rule were written first, and the code followed them. Adding new signals later meant adding a class, not changing the old ones.
- **Testing on a real phone early.** It found problems that no automated test would have found: a phone resting on a desk repeats the same coordinates (a false "suspect"), the free server forgets everything when it sleeps, and a private window changes the device identifier.
- **Showing reasons instead of silently rejecting.** The lecturer decides; the system only points out what looks wrong.

## 3. What did not work

- **Counting people from a photo.** We designed it and built an adapter for a vision service, but the free service did not give a stable result (a retired model name, then timeouts). We dropped it from the demo and kept the manual head count. We did not measure any accuracy and make no claim about it.
- **Public tunnels from the laptop** hung on our network. Hosting on Render solved it.
- **The free AI service was the least reliable part.** In one day we met a retired model name (404), "high demand" errors (503), timeouts, and a spent quota (429) on the newest model, while an older small model answered in under two seconds. A first version hid the cause behind a long wait; we then made a spent quota fail at once with its reason and added a live test of the AI service and a list of the models the key can use. A small model also showed its own working in the answer ("wait, let me re-calculate"), so we changed the instructions to ask for conclusions only.
- **A cookie alone** cannot tie a phone to a person, because a private window removes it. We added the personal PIN and the phone profile checks.

## 4. Known limits

- Indoor location is accurate to tens of meters; it cannot tell two neighbouring rooms apart.
- A student can give the PIN to a friend, and the first person to enter a student's ID chooses that student's PIN (the lecturer can reset it).
- Two phones of the same model look alike, so the phone profile is only a weak signal.
- Data is kept in memory; the free server sleeps and forgets it. The sheet must be exported before closing.
- Adding a student manually after the lecture is closed (FR-28) is designed but not implemented in the demo.
- General rate limiting (NFR-6) and a load test for 200 students (NFR-12) are not done; only the AI calls of a student are limited.
- Uploaded recordings and homework are sent to an external AI service. Names and ID numbers are removed from homework first, but a lecture recording contains voices; the free tier may use submitted data. Real student data needs a paid tier or an agreement.
- Summaries are extractive unless the lecturer has the AI write one; correction of terms is by sound similarity with the slides' terms and is not checked by a model.
- We did not measure the accuracy of the transcript, of handwriting reading or of the AI reviews. They are suggestions for a person to check, never grades.
- Chosen PINs and lecturer passwords can be shown to the lecturer for testing; this must be switched off for real use. Passwords, assignments and submissions are forgotten when the free server restarts or is deployed again; a database behind the existing storage classes is designed and not built.
- The recording is processed by the lecturer's browser (Chrome, up to about 500 MB), there is no background job, and a failed part means starting again.

## 5. Still to complete

- A full rehearsal of the 10-minute demo on the university network, including the AI test button and a short recording.
- Polls and comments have designs only; they are not built.

## 6. What we learned

1. A security feature is only as good as its weakest bypass; we found the bypass (the private window) by trying to cheat ourselves, and we state what remains.
2. Free services and free hosting have limits that decide the design: we had to choose an approach that survives a sleeping server and a failed AI service.
3. A feature that depends on an outside service needs a way to see why it fails: the live test and the exact error saved us more time than any retry.
4. Honest documentation is part of the design: the limits are written next to the features, and every claim in the documents was either tested or says that it was not.
