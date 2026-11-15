# Lency

A voice-and-text desktop assistant for Windows. Talk or type: Lency answers like a friend, controls your PC, and asks before doing anything that can't be undone.

- Windows 10/11, Python 3.10+
- Chat and web answers by [Groq](https://console.groq.com) (free key); image generation by Hugging Face (optional)
- Speech output uses the voices already on your PC (no download); speech input uses Windows voice typing

## Quick start

```bash
git clone <this repo> && cd Lency
python -m venv venv
venv\Scripts\pip install -r Requirements.txt
copy .env.example .env      # then put your keys and name in .env
run.bat                     # or: venv\Scripts\python main.py
```

`.env` (never commit it):

```
Username=YourName
Assistantname=Lency
GroqAPIkey=...
HuggingFaceAPI=...      # only for "generate an image of ..."
```

## What she can do

| Area | Examples |
|---|---|
| Chat | Natural, spoken-style answers with a short memory; follow-ups like "open that song" are understood |
| Web | "search for python decorators", "open the third result", "open github.com", "what's the news" |
| YouTube | "play Shape of You" picks the video that best matches the name (official upload first) |
| Apps | "open / close Spotify", volume, mute, media keys, "write a cover letter" (opens in Notepad) |
| Files and folders | "open D drive then projects then report", "open downloads", find a file by name |
| Reminders | "remind me to call mom at 6", "set a pasta timer for 12 minutes", recurring, snooze; they fire even when the window is closed |
| Info | weather, maths, unit and currency conversion, battery / CPU / RAM / disk / Wi-Fi status |
| PC control | brightness, screenshots (full, window, snip), minimise / maximise / snap windows, "switch to Chrome", browser tabs |
| Clipboard | read it, summarise / translate / fix it, "copy that" copies her last answer |
| Type for you | "type hello there" types into the app you were using; "new line", "select all", "press control c" |
| Notes and memory | "take a note: ...", "read my notes", "remember that I'm allergic to peanuts", "forget ..." (plain files you can edit) |
| Messages | WhatsApp Web and Gmail drafts in your browser; **sent only after you say yes** |

## Safety: she asks first

Anything risky is prepared, shown, and then she asks. A Yes / No strip appears above the text box; you can also say or type yes / no / cancel.

- Messages and email: drafted and read back, sent only on "yes". She re-checks that the same chat or draft is still on screen and refuses if not. "No", asking something else, or 90 seconds of silence discards the draft.
- Clearing notes or memory asks first, and keeps a backup.
- Her stop words ("stop", "cancel", Esc, the Stop button) cut her off instantly.

## Keys and window

- **Ctrl+Alt+M** anywhere toggles the microphone (beep up = on, down = off). While she is talking it interrupts her. **Ctrl+Space** does the same inside her window, **Esc** stops her talking.
- A small always-on-top window; drag the bar, resize from the corner. Click her name (top left) for voice, keep-on-top, clear chat, quit.
- The X hides her to the tray when started by `run.bat` (reminders keep working) and quits when started from a terminal. Override with `close_to_tray` in `Data/settings.json`.

## Voice input

Lency uses **Windows voice typing (Win+H)**: turn the mic on and speak. Windows draws its own small panel, which apps cannot hide. If you'd rather try the popup-free recogniser (it works on some PCs only), set `"mic_engine": "direct"` in `Data/settings.json` and enable *Settings > Privacy > Speech > Online speech recognition*.

## Messages and email

WhatsApp Web and Gmail must be signed in, in your default browser (Chrome, Edge, Brave, Firefox and Opera work). She uses Windows accessibility to type into the page, so there is no password or API key anywhere.

- "message Mom saying I'll be late" types your exact words; "message Raj asking if he's free" lets her word it.
- "email Raj about the meeting" opens a filled-in Gmail draft.
- Optional nicknames: `Data/contacts.json`, or say "save Mom's email as mom at gmail dot com".

## Your data

Everything personal stays in the git-ignored `Data/` folder and `.env`: chat log, settings, notes, memory, reminders, contacts, places. Chat and web questions are sent to Groq; voice input goes to Microsoft (Windows voice typing); nothing else leaves your PC.

Custom folder shortcuts: `Data/places.json`, for example `{"projects": "D:\\Work\\Projects"}`.

## Project layout

```
main.py                  worker loop: routes each request to the right module
Backend/Router.py        instant rule-based router (LLM router in Model.py is the fallback)
Backend/Control.py       brightness, screenshots, windows, status, clipboard, notes, memory, typing
Backend/Web.py           browser, search results, YouTube picker
Backend/Messaging.py     WhatsApp Web + Gmail drafts
Backend/Paths.py         spoken paths -> real folders / files
Backend/Confirm.py       the permission gate (yes / no)
Backend/Reminders.py     reminders, timers, alarms
Backend/TextToSpeech.py  streaming speech with Windows voices
Frontend/                PyQt5 window, tray, voice typing
tools/make_icons.py      regenerates the icon PNGs
```

## Limits

- Windows only. Brightness control works for laptop screens.
- WhatsApp / Gmail automation depends on those sites' current layout; an update could break it.
- Needs an internet connection for chat, search, weather and speech input; local features (apps, volume, reminders, notes, status, windows) work offline.
