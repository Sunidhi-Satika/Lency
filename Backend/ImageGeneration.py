import asyncio
import requests
from random import randint
from PIL import Image
from dotenv import load_dotenv
from time import sleep
import os
import re
import sys

load_dotenv()
HuggingFaceAPI = os.getenv("HuggingFaceAPI")

def open_images(prompt):
    folder_path = r"Data"
    prompt = prompt.replace(" ", "_")

    files = [f"{prompt}{i}.jpg" for i in range(1, IMAGE_COUNT + 1)]

    for jpg_file in files:
        image_path = os.path.join(folder_path, jpg_file)

        try:
            img = Image.open(image_path)
            print(f"Opening image: {image_path}")
            img.show()
            sleep(1)
        except IOError:
            print(f"Unable to open: {image_path}")

# old api-inference.huggingface.co host was retired; the router host replaces it
API_URL = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"
IMAGE_COUNT = 2  # was 3; each image is a separate paid/rate-limited request
headers = {"Authorization": f"Bearer {HuggingFaceAPI}"}

async def query(prompt):
    payload = {
            "inputs": f"{prompt}, quality=4K, sharpness=maximum, Ultra High details, high resolution, seed={randint(0, 1000000)}"
        }
    response = await asyncio.to_thread(requests.post, API_URL, headers=headers, json=payload)
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}, {response.text}")
        return None
    
    return response.content

async def generate_images(prompt: str):

    tasks = [query(prompt) for _ in range(IMAGE_COUNT)]
    image_data_list = await asyncio.gather(*tasks)

    if not any(image_data_list):  # Check if all requests failed
        print("No images were generated.")
        return 0

    for i, image_data in enumerate(image_data_list):
        if image_data:
            file_path = fr"Data/{prompt.replace(' ', '_')}{i+1}.jpg"
            with open(file_path, "wb") as f:
                f.write(image_data)
            print(f"Image saved: {file_path}")
    return sum(1 for d in image_data_list if d)

def GenerateImages(prompt: str):
    prompt = re.sub(r"[^A-Za-z0-9 ]+", "", prompt.replace("generate image", "")).strip() or "art"
    saved = asyncio.run(generate_images(prompt))
    if not saved:
        sys.exit(1)                      # tells main.py it failed so she doesn't claim success
    open_images(prompt)

if __name__ == "__main__":
    # called by main.py with the prompt as an argument (no more polling a data file)
    GenerateImages(" ".join(sys.argv[1:]) or "art")