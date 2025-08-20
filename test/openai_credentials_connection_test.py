import os
import openai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

if api_key:
    try:
        client = openai.OpenAI(api_key=api_key)
        client.models.list()
        print("OpenAI API key is valid.")
    except Exception as exc:
        print(f"OpenAI API test failed: {exc}")
else:
    print("OPENAI_API_KEY is not set.")
