from json import load, dump
from Backend import State, LLM
from Backend.LLM import stream, PERSONA, now_info, clean, friendly_error

LOG = r"Data/ChatLog.json"
MAX_HISTORY = 12     # fewer old messages per request = fewer tokens against the free per-minute cap


def _read_log():
    try:
        with open(LOG, "r", encoding="utf-8") as f:
            data = load(f)
            return data if isinstance(data, list) else []
    except (FileNotFoundError, ValueError):
        return []


def _write_log(messages):
    with open(LOG, "w", encoding="utf-8") as f:
        dump(messages[-MAX_HISTORY:], f, indent=4, ensure_ascii=False)


def run_chat(system_messages, user_text, speaker=None, temperature=0.9):
    """Stream an answer. If a LiveSpeaker is given, speech starts with the first sentence."""
    messages = _read_log()
    messages.append({"role": "user", "content": str(user_text)})
    messages = messages[-MAX_HISTORY:]

    answer = ""
    for delta in stream(system_messages + messages, max_tokens=450, temperature=temperature):
        if State.cancelled():
            break
        answer += delta
        if speaker:
            speaker.feed(delta)

    if LLM.last_finish == "length":                 # hit the token cap: end on a whole sentence
        cut = max(answer.rfind(". "), answer.rfind("! "), answer.rfind("? "), answer.rfind("."))
        if cut > 40:
            answer = answer[:cut + 1]
    answer = clean(answer)
    if answer:
        messages.append({"role": "assistant", "content": answer})   # stored clean: no markdown after a restart
        _write_log(messages)
    return answer


def ChatBot(Query, speaker=None):
    try:
        return run_chat(
            [{"role": "system", "content": PERSONA}, {"role": "system", "content": now_info()}],
            Query, speaker)
    except Exception as e:
        return friendly_error(e)


if __name__ == "__main__":
    while True:
        print(ChatBot(input("Enter : ")))
