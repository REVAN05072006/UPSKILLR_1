from flask import Flask, render_template, request, redirect, send_from_directory
from openai import OpenAI
import os
import re
import requests
from dotenv import load_dotenv
from typing import Optional, Tuple
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-default-secret-key")

# Constants and configurations
MAX_TOKENS = 4000
DEFAULT_MODEL = "openai/gpt-4o"
SERVICE_TIMEOUT = 30  # Increased timeout

def get_ai_client() -> Optional[OpenAI]:
    """Safely initialize and return the OpenAI client."""
    try:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            app.logger.error("GitHub token is missing")
            return None

        # Test connection first
        try:
            test_response = requests.get("https://models.github.ai", timeout=5)
            if test_response.status_code != 200:
                app.logger.error("AI service endpoint unavailable")
                return None
        except requests.RequestException as e:
            app.logger.error(f"Connection test failed: {str(e)}")
            return None

        return OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=token,
            timeout=SERVICE_TIMEOUT
        )
    except Exception as e:
        app.logger.error(f"Client initialization failed: {str(e)}")
        return None

def generate_safe_content(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Generate content with comprehensive error handling."""
    try:
        client = get_ai_client()
        if not client:
            return None, "Service temporarily unavailable. Please try again later."

        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert educator creating micro-courses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=MAX_TOKENS,
            timeout=SERVICE_TIMEOUT
        )
        return response.choices[0].message.content, None
    except Exception as e:
        app.logger.error(f"Content generation error: {str(e)}")
        return None, "We couldn't generate content. Please try a different topic."

@app.route('/', methods=['GET', 'POST'])
def index():
    try:
        if request.method == 'POST':
            topic = request.form.get('topic', '').strip()
            if not topic:
                return render_template('index.html', error="Please enter a topic")

            prompt = f"""Create a micro-course about {topic} with 3-5 lessons.
            Each lesson should have:
            - Title (format as "### Lesson [number]: [title]")
            - 3-5 key points
            - 2-3 sentence summary"""

            content, error = generate_safe_content(prompt)
            
            if error:
                return render_template('index.html', 
                                   error=error,
                                   topic=topic)

            return render_template('index.html',
                               topic=topic,
                               content=content,
                               show_content=True)

        return render_template('index.html')
    except Exception as e:
        app.logger.error(f"Index route error: {str(e)}")
        return render_template('index.html',
                           error="An unexpected error occurred. We're working on it!")

# Error handler for 500 errors
@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"500 Error: {str(error)}")
    return render_template('index.html',
                       error="Something went wrong. Please try again later."), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
