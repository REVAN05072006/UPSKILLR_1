from flask import Flask, render_template, request
import requests
import os
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

DEEPINFRA_URL = "https://api.deepinfra.com/v1/openai/chat/completions"
HEADERS = {
    "Authorization": f"Bearer {os.getenv('DEEPINFRA_API_KEY')}",
    "Content-Type": "application/json"
}

def generate_content(topic: str):
    prompt = f"""Create a 3-lesson micro-course about {topic}. For each:
    - Title (format as '### Lesson [number]: [title]')
    - 3 bullet points
    - 2-sentence summary"""
    
    try:
        response = requests.post(
            DEEPINFRA_URL,
            headers=HEADERS,
            json={
                "model": "meta-llama/Meta-Llama-3-8B-Instruct",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 500
            },
            timeout=20
        )
        
        if response.status_code == 401:
            return None, "❗ Invalid API key - check .env"
        if not response.ok:
            return None, f"API Error: {response.text[:100]}..."
            
        return response.json()['choices'][0]['message']['content'], None
    except Exception as e:
        return None, f"🚨 Connection Error: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('index.html', error="Please enter a topic")
        
        content, error = generate_content(topic)
        return render_template('index.html',
                           topic=topic,
                           content=content,
                           error=error,
                           show_content=content is not None)
    
    return render_template('index.html')

if __name__ == '__main__':
    app.run(port=5000, debug=True)
