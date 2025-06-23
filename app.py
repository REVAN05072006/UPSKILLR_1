import os
import requests
import re
from flask import Flask, render_template, request
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Configuration - Use environment variable in production
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
MODEL_NAME = "deepseek/deepseek-chat-v3-0324:free"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://upskillr.onrender.com",  # Update for production
    "X-Title": "UpSkillr",
    "Content-Type": "application/json"
}

def format_content_to_html(content):
    """Convert plain text content to properly formatted HTML"""
    if not content:
        return ""
    
    # Split content into lines
    lines = content.strip().split('\n')
    formatted_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Check for lesson headers (containing "Lesson" and numbers)
        if re.match(r'^(Lesson\s*\d+|Chapter\s*\d+|\d+\.)', line, re.IGNORECASE):
            formatted_lines.append(f'<h2 class="lesson-title" data-aos="fade-up">{line}</h2>')
        # Check for section headers (lines ending with colon or starting with ##)
        elif line.endswith(':') or line.startswith('##'):
            clean_line = line.replace('##', '').strip().rstrip(':')
            formatted_lines.append(f'<h3 class="section-title" data-aos="fade-left">{clean_line}</h3>')
        # Check for bullet points or numbered lists
        elif re.match(r'^[\-\*\+]\s+', line) or re.match(r'^\d+\.\s+', line):
            # Start a list if we're not already in one
            if not formatted_lines or not formatted_lines[-1].startswith('<ul>'):
                formatted_lines.append('<ul class="content-list" data-aos="fade-up">')
            clean_line = re.sub(r'^[\-\*\+]\s+', '', line)
            clean_line = re.sub(r'^\d+\.\s+', '', clean_line)
            formatted_lines.append(f'<li>{clean_line}</li>')
        else:
            # Close any open list
            if formatted_lines and formatted_lines[-1].startswith('<li>'):
                formatted_lines.append('</ul>')
            # Regular paragraph
            if line:
                formatted_lines.append(f'<p class="content-paragraph" data-aos="fade-right">{line}</p>')
    
    # Close any remaining open list
    if formatted_lines and formatted_lines[-1].startswith('<li>'):
        formatted_lines.append('</ul>')
    
    return '\n'.join(formatted_lines)

def generate_content(topic):
    """Generate educational content with strict error handling"""
    if not OPENROUTER_API_KEY.startswith("sk-or-v1-"):
        return None, "Invalid API key format - must start with 'sk-or-v1-'"
        
    prompt = f"""Create a comprehensive 3-lesson course about {topic}. Format it clearly with:

Lesson 1: Foundation & Basics
- Core concepts and terminology
- Fundamental principles
- Basic examples

Lesson 2: Practical Application
- Real-world examples
- Hands-on exercises
- Common use cases

Lesson 3: Advanced Concepts & Best Practices
- Advanced techniques
- Best practices
- Common pitfalls to avoid

Make each lesson detailed with clear explanations and practical examples. Use clear headings and organize the content in a structured way."""
        
    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=HEADERS,
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 1500
            },
            timeout=30
        )
                
        # Debug print (remove in production)
        print(f"API Response: {response.status_code}")
        print(f"Response Body: {response.text[:200]}...")
                
        if response.status_code == 401:
            return None, "OpenRouter rejected the API key"
                
        response.raise_for_status()
        raw_content = response.json()['choices'][0]['message']['content']
        formatted_content = format_content_to_html(raw_content)
        return formatted_content, None
            
    except Exception as e:
        return None, f"Connection Error: {str(e)}"

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('index.html', error="Please enter a topic")
                
        content, error = generate_content(topic)
        return render_template(
            'index.html',
            topic=topic,
            content=content,
            error=error,
            show_content=content is not None
        )
    return render_template('index.html')

if __name__ == '__main__':
    # Get port from environment variable for Render deployment
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
