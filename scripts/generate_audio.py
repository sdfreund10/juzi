import requests
from dotenv import load_dotenv
import os

load_dotenv()
MODEL = "elevenlabs/eleven-multilingual-v2"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

response = requests.post(
  url="https://openrouter.ai/api/v1/audio/speech",
  headers={
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "Content-Type": "application/json"
  },
  json={
    "model": MODEL,
    "input": "他生病了，今天不去上班。",
    "voice": "sarah",
    "response_format": "mp3"
  }
)
response.raise_for_status()

with open("output.mp3", "wb") as f:
  f.write(response.content)

generation_id = response.headers.get("X-Generation-Id")
print(f"Audio saved. Generation ID: {generation_id}")
