from googlesearch import search
from groq import Groq
from json import load, dump
import datetime
from dotenv import dotenv_values

env_vars = dotenv_values(".env")

Username = env_vars.get("Username")
Assistantname = env_vars.get("Assistantname")
GroqAPIkey = env_vars.get("GroqAPIkey")

client = Groq(api_key=GroqAPIkey)

System = f"""Hello, I am {Username}, You are a very accurate and advanced AI chatbot named {Assistantname} which has real-time up-to-date information from the internet.
*** Provide Answers In a Professional Way, make sure to add full stops, commas, question marks, and use proper grammar.***
*** Just answer the question from the provided data in a professional way. ***"""

try:
    with open(r"Data/ChatLog.json", "r") as f:
        messages = load(f)
except FileNotFoundError:
    with open(r"Data/ChatLog.json", "w") as f:
        dump([],f)

def GoogleSearch(query):
    results = list(search(query, advanced=True, num_results=5))
    Answer = f"The search results for {query} are: \n[start]\n"

    for i in results:
        Answer += f"Title: {i.title}\nDescription: {i.description}\n\n"

    Answer+="[end]"
    return Answer

def AnswerModifier(Answer):
    Answer = Answer.replace("*", "")
    lines = Answer.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    modified_answer = '\n'.join(non_empty_lines)
    return modified_answer

SystemChatBot = [
    {"role": "system", "content": System},
    {"role": "user", "content": "Hi"},
    {"role": "assistant", "content": "Hello, how can I help you?"}
]

def Information():
    currentdatetime = datetime.datetime.now()
    day = currentdatetime.strftime("%A")
    date = currentdatetime.strftime("%d")
    month = currentdatetime.strftime("%B")
    year = currentdatetime.strftime("%Y")
    hour = currentdatetime.strftime("%H")
    minutes = currentdatetime.strftime("%M")
    seconds = currentdatetime.strftime("%S")

    data = f"please use this real-time information if needed,\n"
    data += f"Day: {day}, Date: {date}, Month: {month}, Year: {year},\n"
    data += f"Time: {hour} hours, {minutes} minutes, {seconds} seconds\n"
    return data

def RealTimeSearchEngine(prompt):
    global SystemChatBot, messages

    try:
        with open(r"Data/ChatLog.json", "r") as f:
                messages = load(f)        
        messages.append({"role": "user", "content": f"{prompt}"})

        SystemChatBot.append({"role": "system", "content": GoogleSearch(prompt)})

        completion = client.chat.completions.create(
                model="llama3-70b-8192",
                messages=SystemChatBot + [{"role": "system", "content": Information()}] + messages,
                max_tokens=1024,
                temperature=0.7,
                top_p=1,
                stream=True,
                stop=None
            )
        Answer = ""

        for chunk in completion:
            if chunk.choices[0].delta.content:
                Answer += chunk.choices[0].delta.content

        Answer = Answer.replace("</s>", "")

        messages.append({"role": "assistant", "content": Answer})
        with open(r"Data/ChatLog.json", 'w') as f:
            dump(messages, f, indent=4)

        SystemChatBot.pop()
        return AnswerModifier(Answer=Answer)

    except Exception as e:
            print(f"Error: {e}")
            return "An error occured while processing your request."

if __name__ == "__main__":
    while True:
        prompt = input("Enter : ")
        print(RealTimeSearchEngine(prompt))