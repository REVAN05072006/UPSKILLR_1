from flask import Flask, render_template, request, redirect, url_for
import os
import re
import requests
from dotenv import load_dotenv
from typing import Optional, Tuple
from datetime import datetime

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-default-secret-key")

# Constants
MAX_TOKENS = 4000
DEFAULT_MODEL = "openai/gpt-4o"
SERVICE_STATUS_FILE = "service_status.txt"

def check_service_status() -> bool:
    try:
        if not os.path.exists(SERVICE_STATUS_FILE):
            return False
        with open(SERVICE_STATUS_FILE, 'r') as f:
            last_success = datetime.fromisoformat(f.read())
            return (datetime.now() - last_success).total_seconds() < 3600
    except Exception:
        return False

def update_service_status():
    with open(SERVICE_STATUS_FILE, 'w') as f:
        f.write(datetime.now().isoformat())

def get_ai_client() -> Optional[object]:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        app.logger.error("GitHub token missing from environment")
        return None
    try:
        response = requests.get("https://models.github.ai", timeout=5)
        if response.status_code >= 500:
            return None
    except requests.RequestException:
        return None
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url="https://models.github.ai/inference",
            api_key=token,
            timeout=10
        )
        client.models.list()
        update_service_status()
        return client
    except Exception as e:
        app.logger.error(f"AI client failed: {str(e)}")
        return None

def generate_content(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    client = get_ai_client()
    if client:
        try:
            response = client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": "You are an expert educator creating micro-courses. Provide only the course content, no introductory text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=MAX_TOKENS,
                timeout=20
            )
            content = response.choices[0].message.content
            if content.startswith("#"):
                content = "\n".join([line for line in content.split("\n") if not line.strip().startswith("# ")][1:])
            return content, None
        except Exception as e:
            app.logger.error(f"Generation failed: {str(e)}")
    topic = prompt.lower().split("about")[-1].strip().rstrip('.')
    fallback_content = f"""# {topic.capitalize()}

### Lesson 1: Introduction to {topic}
- Key concept 1
- Key concept 2
- Key concept 3

**Summary:**
Basic introduction to the field and its importance.

### Lesson 2: Core Techniques
- Technique 1
- Technique 2
- Technique 3

**Summary:**
Overview of fundamental methods used in this field."""
    return fallback_content, None

def format_lesson_content(topic: str, content: str) -> str:
    if not content:
        return ""
    content = "\n".join([line for line in content.split("\n") if not line.strip().lower().startswith(f"# {topic.lower()}")])
    return f"# {topic}\n\n{content.strip()}"

def estimate_learning_time(content: str) -> str:
    word_count = len(content.split())
    minutes = max(1, word_count // 200)
    return f"{minutes} minute{'s' if minutes > 1 else ''}"

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
                               '
::contentReference[oaicite:60]{index=60}
 
