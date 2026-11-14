# Lency

A voice assistant with a warm personality. Talk to her with the mic or type; she answers out loud,
searches the web for live questions, opens apps, controls the volume and draws images.

## Setup (Windows 10/11)
1. Install Python 3.12.
2. `python -m venv venv` then `venv\Scripts\pip install -r Requirements.txt`
3. Copy `.env.example` to `.env` and add your keys:
   - `GroqAPIkey` from https://console.groq.com (free tier, about 1000 requests a day)
   - `HuggingFaceAPI` only if you want image generation
4. Windows Settings > Privacy & security > Speech > turn on **Online speech recognition**
   (the mic uses Windows' own recogniser; without this setting Lency falls back to the Win+H popup).
5. Start her with `run.bat` (or `python main.py`).

## Using her
- Type in the box or tap the mic and just talk. Say "stop" (or press Esc / the Stop button) to quiet her.
- "Change voice to Heera" or use the picker in the top bar. "Clear chat" erases the saved history.
- Reminders, alarms and timers: "remind me to call mom in 20 minutes", "set a pasta timer for 12 minutes", "wake me at 6:30", "every Monday at 9 remind me to submit the timesheet", "snooze 10 minutes", "what reminders do I have", "cancel all timers". They ring even when the window is closed (Lency lives in the tray; right-click it to quit or to turn on Start with Windows).
- Weather: "what's the weather in Delhi", "will it rain tomorrow", "do I need an umbrella"; say "my city is Pune" once and she remembers it.
- Maths and conversions: "what's 15% of 80", "twelve times seven", "convert 5 miles to km", "100 USD to INR".
- Media: "pause", "resume", "next song", "previous song".
- Examples: "open spotify", "set volume to 40", "what's the weather in Delhi", "generate an image of a fox".

## Privacy
Chat goes to Groq, web questions to Brave/DuckDuckGo, images to Hugging Face and speech to Microsoft's
speech service. Your last 12 messages are saved in plain text in `Data/ChatLog.json` (use "Clear chat").

## Not built yet
Wake word, hotkey, long-term memory, packaged .exe (see FEATURES.md).
