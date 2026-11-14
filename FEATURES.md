# Lency feature checklist = (client wishlist ∪ market survey) − what she already has

Sources: **C** = demanding client (65 items, written blind to the code), **M** = market survey (87 features; note its web research was thin: 4 searches, the rest from background knowledge, so treat "which products have it" as approximate).
Effort: S = under a day, M = a few days, L = a week+. Priority: MUST / SHOULD / NICE (client's view, adjusted by how common the feature is in the market).

## Already have (subtracted)
Chat with persona; streaming answer with speech starting on the first sentence; Windows speech recognition + typing; live transcript while speaking; voice picker + "change voice"; stop / Esc / "stop"; follow-up listening (re-arms after she answers); listening/thinking/answering states; live web search; open/close apps; open files; volume (exact, mute); YouTube/Google; image generation; write content to Notepad; last-12-message memory; clear history; themes; honest errors; command-first router; secrets in `.env`.

## Tier 1: the daily-use basics (client MUST and market table-stakes)
- [x] **T1 Reminders, alarms and named timers that fire with the window closed** (done: voice/typed, recurring, snooze, list, cancel, missed-while-off; tested) (C13-15, 19, M13-14): MUST, M. Needs persistence, a scheduler thread, spoken + toast alert, snooze, recurring ("every Monday 9am").
- [ ] **T2 Long-term memory + viewer/editor** ("remember that…", "forget that…", see/edit/delete) (C48-49, M56, 58): MUST, M.
- [x] **T3 Tray icon + autostart + minimise to tray** (done: X hides to tray, tray menu, opt-in Start with Windows; registry write tested with a fake registry only) (C58, M84): MUST, S. Prerequisite for T4 and T1 being useful.
- [ ] **T4 Global hotkey push-to-talk / summon, and wake word "Hey Lency"** (C1-2, M1-2, 50): MUST, S (hotkey) / M (wake word via openWakeWord).
- [x] **T5 Media control: pause, next, previous, play/pause current** (done; key presses mocked in tests) (C37, M29): MUST, S (media keys).
- [x] **T6 Weather** (done: Open-Meteo, saved home city, tomorrow, umbrella/rain; news/sports still use web search) (C44, M36): MUST, S (Open-Meteo, no key) and works offline-ish.
- [x] **T7 Deterministic math, unit and currency conversion** (done) (C26, M21): MUST, S (safe eval / `pint`, free currency API).
- [ ] **T8 Confirm risky actions + "undo that"** (close app with unsaved work, shutdown, delete, send) (C54, M64): MUST, S-M. Gate before any destructive tool; also needed before T11/T12.
- [ ] **T9 Onboarding + "what can you do?"** (C59): MUST, S. First run: mic test, voice, name, city, example commands; help command lists features.
- [ ] **T10 Privacy controls**: visible mic mute indicator, settings for what goes to the cloud, "forget everything" by voice (C53, M62): MUST, S.

## Tier 2: strong value
- [ ] **T11 To-do and shopping lists by voice** (C17, M15): SHOULD, S.
- [ ] **T12 Calendar read/create** (Google Calendar; Outlook later) (C16, M16): MUST per client but L-ish (OAuth). M-L.
- [ ] **T13 Morning briefing** (date, weather, calendar, tasks, one headline) (C18, M22): SHOULD, M after T1, T6, T12.
- [ ] **T14 Notes: "take a note", read back, search** (M17): SHOULD, S.
- [ ] **T15 Answer-length control and "shorter / say that again slower"**; per-answer detail on request (C4): SHOULD, S.
- [ ] **T16 Sources for web answers** + "open the first result" (C36, 56, M35): SHOULD, S.
- [ ] **T17 Desktop control: screenshot, lock, sleep, minimise all, shutdown (confirm), brightness, dark mode** (C32, M44-45): SHOULD, S-M.
- [ ] **T18 Smarter file finding** (by recency/content, read the match before opening) (C34, M42): SHOULD, M.
- [ ] **T19 Summarise clipboard / page / PDF; read selected text aloud** (C23-24, M19, 49): SHOULD, M.
- [ ] **T20 Transcript correction + "didn't catch that" re-prompt** (C6, M67): SHOULD, S.
- [ ] **T21 Natural end-of-speech tuning** (VAD-style, adjustable pause) (C5, M10): SHOULD, S (setting) / M (true VAD).
- [ ] **T22 Voice speed/pitch sliders + whisper/quiet mode** (C11-12, M5): SHOULD, S.
- [ ] **T23 Study tools: Pomodoro/focus mode with spoken breaks; quiz me / flashcards** (C21-22, 28): SHOULD, M.
- [ ] **T24 Custom routines / shortcut names** ("study mode" opens apps, plays lo-fi, sets a timer) (C60, M23): SHOULD, M after T1.
- [ ] **T25 Settings page**: default browser/music app, units, city, personality dial, custom instructions (C52, 61, M57, 60, 78): SHOULD, M.
- [ ] **T26 Chat history upgrades**: search, export, copy, pin, markdown/code rendering (C64, M85): SHOULD, S-M.
- [ ] **T27 Offline fallback**: local commands/timers/volume always work; clear "no internet" mode (C55, M61, 66, 71): SHOULD, S for basics, L for local LLM.
- [ ] **T28 Reply in the user's language / Hinglish understanding** (C9-10, M9): SHOULD, M (currently forced English).
- [ ] **T29 Accessibility**: font size, high contrast, full keyboard use (C62, M75): SHOULD, S.
- [ ] **T30 Emotional awareness / supportive mode, opt-in check-ins** (C50-51, M77, 79): SHOULD, S (prompt) / M (proactive).
- [ ] **T31 Health nudges** (water, stretch, 20-20-20 eye breaks) (C42): SHOULD, S after T1.

## Tier 3: nice to have
- [ ] T32 Music by mood/artist, Spotify control (C38) M · T33 Fun: jokes, trivia, bedtime story (C40, M34) S · T34 Hands-free recipes (C46) M
- [ ] T35 Email: read, dictate, send with confirmation (C30, M24) L (Gmail OAuth) · T36 Meeting helper (C31) L
- [ ] T37 Screen vision: "what's on my screen?" (M31) M (vision-capable LLM) · T38 Translate/dictionary spoken (C27, M20) S
- [ ] T39 Clipboard history (C33) S · T40 File tidy by voice with undo (C35) M · T41 Plugin system / tool registry (M81-82) M
- [ ] T42 Model/provider selector + fallback chain (M66, 86) S · T43 Mini always-on-top window (M87) S · T44 Logging/diagnostics + bug report button (C65, M70) S
- [ ] T45 Smart home via Home Assistant (C63, M51-52) M, only if you own devices · T46 Voice lock/PIN (C57) M · T47 Phone companion (C63) L
- [ ] T48 Image gen extras: re-roll, set as wallpaper (C41) S · T49 Study summary at end of day (C28) S · T50 Travel/flight/stocks/sports (C45, 47, M39) S-M
- [ ] T51 Context-triggered reminders (C20) L · T52 Semantic memory search (M59) M · T53 Animated avatar (M80) skipped: you chose the aurora instead

## Deliberately skipped (low value for effort)
Native phone calls/SMS, song identification, full OS voice control (use Windows Voice Access), voice-built smart-home automations, deep-research mode.

## Suggested build order
1. **T3 tray + autostart** → **T1 reminders/timers** (the known gap, needs the tray to survive window close)
2. **T6 weather, T7 math/conversion, T5 media keys** (small, instantly useful, work offline)
3. **T2 memory + editor, T8 confirmations, T9 onboarding/help, T10 privacy**
4. **T4 hotkey, then wake word**
5. Tier 2 in the order that interests you; Tier 3 later.
