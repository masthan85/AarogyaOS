"""One Sarvam chat completion. Reads SARVAM_API_KEY from the environment (or ../../.env)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sarvamai import SarvamAI

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
key = os.environ.get("SARVAM_API_KEY", "")
if not key:
    sys.exit("SARVAM_API_KEY is not set. Put your key in .env at the repository root.")

client = SarvamAI(api_subscription_key=key)
response = client.chat.completions(
    model="sarvam-105b-conversations",
    messages=[{"role": "user", "content": "Say hello in one short sentence."}],
)
print(response.choices[0].message.content)
