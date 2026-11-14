from Backend.LLM import PERSONA, now_info, friendly_error
from Backend.Chatbot import run_chat


def WebSearch(query):
    """Top web results as text for the LLM.

    The old googlesearch scraper now returns nothing (Google blocks it), so real-time questions
    silently got no data. ddgs with the Brave backend answers in ~1.5 s; 'auto' (all engines,
    slower) is the fallback.
    """
    from ddgs import DDGS
    results, last = [], None
    for backend in ("brave", "auto"):
        try:
            results = DDGS(timeout=6).text(query, max_results=5, backend=backend)
            if results:
                break
        except Exception as e:
            last = e
    if not results:
        print(f"Search error: {last}")
        return "No search results could be fetched."
    out = f"Web search results for '{query}':\n[start]\n"
    for r in results:
        out += f"Title: {r.get('title', '')}\nDescription: {r.get('body', '')}\n\n"
    return out + "[end]"


def RealTimeSearchEngine(prompt, speaker=None):
    try:
        system = [
            {"role": "system", "content": PERSONA},
            {"role": "system", "content": "Answer the question using the web results below, in your own warm words. Do not read them out verbatim."},
            {"role": "system", "content": WebSearch(prompt)},
            {"role": "system", "content": now_info()},
        ]
        # history is capped and the (large) search dump is never saved to it
        return run_chat(system, prompt, speaker, temperature=0.7)

    except Exception as e:
        return friendly_error(e)


if __name__ == "__main__":
    while True:
        print(RealTimeSearchEngine(input("Enter : ")))

