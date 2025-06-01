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

# Constants
MAX_TOKENS = 4000
DEFAULT_MODEL = "openai/gpt-4o"
SERVICE_STATUS_FILE = "service_status.txt"
FALLBACK_CONTENT = {
    "python": """# Python Programming Basics

### Lesson 1: Introduction to Python
- Python is an interpreted, high-level language
- Known for its simple syntax and readability
- Widely used in web development, data science, and automation

### Lesson 2: Variables and Data Types
- Variables store data values
- Basic types: integers, floats, strings, booleans
- Dynamic typing allows flexible variable usage""",
    "machine learning": """# Machine Learning Fundamentals

### Lesson 1: What is Machine Learning?
- Field of AI that enables systems to learn from data
- Three main types: supervised, unsupervised, reinforcement
- Applications in recommendation systems, image recognition

### Lesson 2: Basic Algorithms
- Linear regression for continuous values
- Decision trees for classification
- Neural networks for complex patterns""",
    "default": """# Welcome to UpSkillr

Our AI service is currently unavailable. Here are some options:
1. Check your internet connection
2. Try a different topic
3. Try again later

Suggested topics to explore:
- Web development basics
- Data analysis techniques
- Cloud computing fundamentals"""
}

def check_service_status() -> bool:
    """Check if service was recently available."""
    try:
        if not os.path.exists(SERVICE_STATUS_FILE):
            return False
            
        with open(SERVICE_STATUS_FILE, 'r') as f:
            last_success = datetime.fromisoformat(f.read())
            return (datetime.now() - last_success).total_seconds() < 3600  # 1 hour cache
    except Exception:
        return False

def update_service_status():
    """Record successful service access."""
    with open(SERVICE_STATUS_FILE, 'w') as f:
        f.write(datetime.now().isoformat())

def get_ai_client() -> Optional[OpenAI]:
    """Initialize AI client with comprehensive checks."""
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        app.logger.error("GitHub token missing from environment")
        return None

    try:
        # Check if API endpoint is reachable
        response = requests.get("https://models.github.ai", timeout=5)
        if response.status_code >= 500:
            return None
    except requests.RequestException:
        return None

    try:
        client = OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=token,
            timeout=10
        )
        # Verify connection
        client.models.list()
        update_service_status()
        return client
    except Exception as e:
        app.logger.error(f"AI client failed: {str(e)}")
        return None

def generate_content(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Generate content with multiple fallback layers."""
    # Try real AI service first
    client = get_ai_client()
    if client:
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert educator creating micro-courses."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=MAX_TOKENS,
                timeout=20
            )
            return response.choices[0].message.content, None
        except Exception as e:
            app.logger.error(f"Generation failed: {str(e)}")

    # Fallback to cached content for common topics
    topic = prompt.lower().split("about")[-1].strip()
    for keyword, content in FALLBACK_CONTENT.items():
        if keyword in topic and keyword != "default":
            return content, None

    # Final fallback
    return FALLBACK_CONTENT["default"], None

def estimate_learning_time(text: str) -> str:
    """Estimate learning time based on word count."""
    if not text:
        return "Time estimate unavailable"
    word_count = len(text.split())
    minutes = max(1, round(word_count/100))
    return f"{minutes} minute{'s' if minutes > 1 else ''}"

def format_lesson_content(topic: str, content: str) -> str:
    """Format lesson content consistently."""
    if not content:
        return content
    if not content.startswith(f"# {topic}"):
        content = f"# {topic}\n\n{content}"
    return content

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('index.html', error="Please enter a topic to learn about")

        prompt = f"""Create a comprehensive micro-course about {topic} with 3-5 lessons.
        For each lesson, provide:
        1. A clear title (format as "### Lesson [number]: [title]")
        2. 3-5 key learning points (format as bullet points)
        3. A brief summary (2-3 sentences)
        
        Use Markdown formatting for headings and lists.
        Ensure the content is well-structured and easy to follow."""

        content, error = generate_content(prompt)
        
        if error:
            service_status = " (Service unavailable)" if not check_service_status() else ""
            return render_template('index.html',
                               error=f"Unable to generate content{service_status}. Please try again.",
                               topic=topic)

        formatted_content = format_lesson_content(topic, content)
        return render_template('index.html',
                           topic=topic,
                           content=formatted_content,
                           estimated_time=estimate_learning_time(content),
                           show_content=True)

    return render_template('index.html')

@app.route('/quiz', methods=['GET'])
def generate_quiz():
    topic = request.args.get('topic')
    content = request.args.get('content')

    if not topic or not content:
        return redirect('/')

    prompt = f"""Create 5 multiple choice quiz questions about {topic} based on this content:
    {content}

    Format each question exactly like this example:
    Q1. What is the capital of France?
    A) London
    B) Paris
    C) Berlin
    D) Madrid
    Answer: B
    
    Include exactly 4 options (A-D) for each question and clearly mark the correct answer.
    Ensure questions cover different aspects of the content."""

    quiz_content, error = generate_content(prompt)

    if error:
        return render_template('index.html',
                           topic=topic,
                           content=content,
                           error="Couldn't generate quiz. Try again later.",
                           show_content=True)

    questions = []
    question_blocks = [block.strip() for block in quiz_content.split('\n\n') if block.strip()]
    
    for block in question_blocks[:5]:
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        if len(lines) >= 6 and lines[0].startswith('Q'):
            answer_line = lines[-1]
            correct_answer = re.search(r'Answer:\s*([A-D])', answer_line, re.IGNORECASE)
            if not correct_answer:
                continue
                
            correct_letter = correct_answer.group(1).upper()
            questions.append({
                'number': len(questions) + 1,
                'text': lines[0][lines[0].find('.')+1:].strip(),
                'options': [opt for opt in lines[1:5] if opt],
                'correct': correct_letter,
                'correct_full': lines[ord(correct_letter) - ord('A') + 1]
            })

    return render_template('index.html',
                       topic=topic,
                       content=content,
                       show_content=True,
                       quiz_data={'questions': questions})

@app.route('/submit-quiz', methods=['POST'])
def submit_quiz():
    topic = request.form.get('topic')
    if not topic:
        return redirect('/')
    
    score = 0
    results = []
    total_questions = 0
    
    for key in request.form:
        if key.startswith('question_'):
            total_questions += 1
    
    for i in range(1, total_questions + 1):
        user_answer = request.form.get(f'q_{i}', '').strip()
        correct_answer = request.form.get(f'correct_full_{i}', '').strip()
        question_text = request.form.get(f'question_{i}', '')
        
        is_correct = user_answer.lower() == correct_answer.lower()
        if is_correct:
            score += 1
            
        results.append({
            'number': i,
            'question': question_text,
            'user_answer': user_answer,
            'correct_answer': correct_answer,
            'is_correct': is_correct
        })

    percentage = int((score / total_questions) * 100) if total_questions > 0 else 0
    
    if percentage >= 80:
        feedback = "Excellent! You've mastered this topic."
    elif percentage >= 60:
        feedback = "Good job! You have a solid understanding."
    else:
        feedback = "Keep practicing! Review the lessons and try again."

    return render_template('index.html',
                       topic=topic,
                       quiz_result={
                           'score': score,
                           'total': total_questions,
                           'percentage': percentage,
                           'feedback': feedback,
                           'results': results
                       })

if __name__ == '__main__':
    app.run(port=5000, debug=True)
