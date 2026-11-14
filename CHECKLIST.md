# Lency fix checklist (from the pessimistic-customer review + support triage)

Legend: [x] done and tested, [~] done, not testable without a microphone/GUI, [ ] still open

| # | Complaint | Verdict | Status | What was done |
|---|-----------|---------|--------|---------------|
| 1 | Any question containing "generate" launched the image generator | REAL / high | [x] | Only `generate image ...` starts it; "how do I generate random numbers" now goes to chat |
| 2 | Reminders silently ignored | REAL / high | [x] honest decline | She says she can't set reminders yet. **Real reminders still open (large).** |
| 3 | "Done!" even when a command failed | REAL / medium | [x] | Tasks return success/failure counts; she says done / partly / failed. Image script exits non-zero on failure. `close msedge` works |
| 4 | "good morning, open spotify" swallowed; "close it" closed a random app | REAL / medium | [x] | Greetings are skipped before commands; "it/this/that/all" rejected for open and close |
| 5 | One vague apology for every error | REAL / medium | [x] | Separate spoken messages for offline, rate limit, bad key, missing key; 20 s timeout |
| 6 | Mic only worked while window in front; 1.6 s cutoff | PARTLY | [~] | No focus gate in direct mode (still on for Win+H fallback); pause is 2.0 s. Wake word not built |
| 7 | Win+H fallback, dead settings, missing deps | PARTLY | [x] | Speech packages added to requirements, fallback shown in chat, tooltip mentions Microsoft |
| 8 | No way to stop her | REAL / medium | [x] | Stop button, Esc, or say "stop"; cuts audio and abandons the answer in under a second |
| 9 | Long answers chopped | PARTLY | [x] | Cut-off answers end on a whole sentence; Home hint "(more in Chat)" |
| 10 | `*` / `#` stripped (C#, 5*3) | PARTLY | [x] | Only markdown is removed; speech says "C sharp", "5 times 3"; history stored clean; your capitals are kept |
| 11 | Volume weak, mute toggled | REAL / med-low | [x] | Real Windows volume API: "set volume to 40", "volume up 20", idempotent mute/unmute (media-key fallback) |
| 12 | Opens invented websites | PARTLY | [x] | https + host must match the app name, otherwise a Google search. Fuzzy app matching left as is |
| 13 | Privacy | PARTLY | [x] | Clear chat button, `.gitignore`, `.env.example`, honest-about-AI persona line. **Delete the unused CohereAPIkey in .env and rotate it** (not touched by me) |
| 14 | Heavy window | PARTLY | [x] greeting | Greeting refreshes through the day. Tray icon / compact mode not built |
| 15 | Setup hassle | REAL / medium | [x] | Pinned complete `Requirements.txt`, README, `run.bat`, rebuilt `venv`, friendly missing-key message |

## Still open
- Real reminders (date parsing, saved list, timer)
- Wake word / always-on hands-free mode
- Tray icon, compact mode, packaged `.exe`
- Dictation with a real microphone has not been tested by me
