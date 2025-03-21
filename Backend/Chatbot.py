from groq import Groq
from json import load, dump
import datetime
from dotenv import dotenv_values

env_vars = dotenv_values(".env")

Username = env_vars.get("Username")
Assistantname = env_vars.get("Assistantname")
GroqAPIkey = env_vars.get("GroqAPIkey")

client = Groq(api_key=GroqAPIkey)

messages = []

System = f"""Hello, I am {Username}, You are a very accurate and advanced AI Assistant named {Assistantname} which also has real-time up-to-date information from the internet.
*** Do not tell time until I ask, do not talk too much, just answer the question.***
*** Reply in only English, even if the question is in Hindi or Telugu, reply in English.***
*** Do not provide notes in the output, just answer the question and never mention your training data. ***
*** Answer in paragraphs ***
*** Do not use asterisks in between of your message ***
"""

SystemChatBot = [
    {"role": "system", "content": System}
]

try:
    with open(r"Data/ChatLog.json", "r") as f:
        messages = load(f)
except FileNotFoundError:
    with open(r"Data/ChatLog.json", "w") as f:
        dump([],f)

def RealtimeInformation():
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

def AnswerModifier(Answer):
    Answer = Answer.replace("*", "")
    lines = Answer.split("\n")
    non_empty_lines = [line for line in lines if line.strip()]
    modified_answer = '\n'.join(non_empty_lines)
    return modified_answer

def ChatBot(Query):
    try:
        with open(r"Data/ChatLog.json", "r") as f:
            messages = load(f)           
        messages.append({"role": "user", "content": f"{Query}"})
        messages = messages[-20:]

        completion = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=SystemChatBot + [{"role": "system", "content": RealtimeInformation()}] + messages,
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

        return AnswerModifier(Answer=Answer)
    
    except Exception as e:
        print(f"Error: {e}")
        return "An error occured while processing your request."

if __name__ == "__main__":
    while True:
        user_input = input("Enter : ")
        print(ChatBot(user_input))