import os
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

def test_groq_connection():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("Please set a valid GROQ_API_KEY in your .env file.")

    # Initialize the Groq client
    client = Groq(api_key=api_key)

    # Test prompt
    prompt = "Briefly explain what a race condition in a booking os.system is in 2 sentences."

    # Send chat completion request
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model="qwen/qwen3.6-27b",
    )

    print("\n--- LLM Response ---")
    print(chat_completion.choices[0].message.content)
    print("--------------------\n")

if __name__ == "__main__":
    test_groq_connection()
