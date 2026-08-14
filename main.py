import os
from xmlrpc import client
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file
load_dotenv()

def test_gemini_connection():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY":
        raise ValueError("Please set a valid GEMINI_API_KEY in your .env file.")

    # Initialize the Google GenAI client
    client = genai.Client(api_key=api_key)

    # Send a lightweight test prompt
    prompt = "You are Backend Guardian, an AI debugging assistant. State your status in one sentence."
    
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )

    print("\n--- LLM Response ---")
    print(response.text)
    print("--------------------\n")

if __name__ == "__main__":
    
    test_gemini_connection()