# Summary

Status: draft v1 (to be completed after the remaining design work, see section 5)

## 1. What we built

A web-based attendance tool that works from the phone browser with nothing to install, hosted for the demo and tested on a real iPhone:

- a **rotating QR code** (new every 5 seconds, signed, single-use ticket);
- **mandatory location**: without permission the student cannot check in, and a location far from the class group is flagged;
- a **personal PIN** per student, so a phone, a private window or another browser does not make it possible to mark someone else;
- checks that explain themselves: every suspect check-in shows its reasons to the lecturer, and the student never sees the status;
- a live lecturer page with the attendance sheet, a typed head count with the gap, and Excel/CSV export;
- 49 automated tests, one simulated phone per scenario.

The other tools (polls, comments, transcript and summary, homework review) are covered by design documents.

## 2. What worked

- **Designing before coding.** The use cases and the strong/weak check rule were written first, and the code followed them. Adding new signals later meant adding a class, not changing the old ones.
- **Testing on a real phone early.** It found problems that no automated test would have found: a phone resting on a desk repeats the same coordinates (a false "suspect"), the free server forgets everything when it sleeps, and a private window changes the device identifier.
- **Showing reasons instead of silently rejecting.** The lecturer decides; the system only points out what looks wrong.

## 3. What did not work

- **Counting people from a photo.** We designed it and built an adapter for a vision service, but the free service did not give a stable result (a retired model name, then timeouts). We dropped it from the demo and kept the manual head count. We did not measure any accuracy and make no claim about it.
- **Public tunnels from the laptop** hung on our network. Hosting on Render solved it.
- **A cookie alone** cannot tie a phone to a person, because a private window removes it. We added the personal PIN and the phone profile checks.

## 4. Known limits

- Indoor location is accurate to tens of meters; it cannot tell two neighbouring rooms apart.
- A student can give the PIN to a friend, and the first person to enter a student's ID chooses that student's PIN (the lecturer can reset it).
- Two phones of the same model look alike, so the phone profile is only a weak signal.
- Data is kept in memory; the free server sleeps and forgets it. The sheet must be exported before closing.
- General rate limiting (NFR-6) and a load test for 200 students (NFR-12) are not done.

## 5. Still to complete

- Designs and one small experiment each for the transcript and homework tools (planned in the SoW).
- A full rehearsal of the 10-minute demo on the university network.
- This section is to be removed when the items above are done.

## 6. What we learned

1. A security feature is only as good as its weakest bypass; we found the bypass (the private window) by trying to cheat ourselves, and we state what remains.
2. Free services and free hosting have limits that decide the design: we had to choose an approach that survives a sleeping server and a failed AI service.
3. Honest documentation is part of the design: the limits are written next to the features, and every claim in the documents was either tested or says that it was not.
