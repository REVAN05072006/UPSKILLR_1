from flask import Flask, render_template, request, redirect, send_from_directory
from openai import OpenAI
import os
import re
from dotenv import load_dotenv
from typing import Optional, Tuple

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "your-default-secret-key")

# Constants
MAX_TOKENS = 4000
DEFAULT_MODEL = "gpt-4"

def get_ai_client() -> Optional[OpenAI]:
    """Initialize and return the OpenAI client configured for GitHub AI."""
    try:
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise ValueError("GitHub token is missing from environment variables")
        
        return OpenAI(
            base_url="https://api.githubcopilot.com/v1",
            api_key=token,
            default_headers={
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2023-07-07"
            }
        )
    except Exception as e:
        app.logger.error(f"Error initializing AI client: {e}")
        return None

def estimate_learning_time(text: str) -> str:
    """Estimate learning time based on word count."""
    if not text:
        return "Time estimate unavailable"
    
    word_count = len(text.split())
    minutes = max(1, round(word_count/100))
    return f"{minutes} minute{'s' if minutes > 1 else ''}"

def generate_content(prompt: str) -> Tuple[Optional[str], Optional[str]]:
    """Generate content using the AI model."""
    client = get_ai_client()
    if not client:
        return None, "AI service not available. Please check your token and try again."
    
    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert educator creating micro-courses."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=MAX_TOKENS
        )
        return response.choices[0].message.content, None
    except Exception as e:
        app.logger.error(f"AI generation error: {str(e)}")
        return None, f"AI service error: {str(e)}"

def format_lesson_content(topic: str, content: str) -> str:
    """Format the lesson content with consistent structure."""
    if not content:
        return content
    
    # Add topic header if not present
    if not content.startswith(f"# {topic}"):
        content = f"# {topic}\n\n{content}"
    
    return content

@app.route('/static/<path:filename>')
def static_files(filename):
    """Serve static files."""
    return send_from_directory('static', filename)

@app.route('/', methods=['GET', 'POST'])
def index():
    """Main route for generating micro-courses."""
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        if not topic:
            return render_template('index.html', error="Topic is required")

        prompt = f"""Create a comprehensive micro-course about {topic} with 3-5 lessons.
        For each lesson, provide:
        1. A clear title (format as "### Lesson [number]: [title]")
        2. 3-5 key learning points (format as bullet points)
        3. A brief summary (2-3 sentences)
        
        Use Markdown formatting for headings and lists.
        Ensure the content is well-structured and easy to follow."""

        content, error = generate_content(prompt)
        
        if error:
            return render_template('index.html', error=error)

        formatted_content = format_lesson_content(topic, content)
        
        return render_template('index.html', 
                           topic=topic,
                           content=formatted_content,
                           estimated_time=estimate_learning_time(content),
                           show_content=True)

    return render_template('index.html')

@app.route('/quiz', methods=['GET'])
def generate_quiz():
    """Generate quiz questions based on the course content."""
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
                           error=f"Quiz error: {error}",
                           show_content=True)

    questions = []
    question_blocks = [block.strip() for block in quiz_content.split('\n\n') if block.strip()]
    
    for block in question_blocks[:5]:  # Take max 5 questions
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
    """Process quiz submissions and provide results."""
    topic = request.form.get('topic')
    if not topic:
        return redirect('/')
    
    score = 0
    results = []
    total_questions = 0
    
    # Count total questions
    for key in request.form:
        if key.startswith('question_'):
            total_questions += 1
    
    # Evaluate each question
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
    
    # Generate feedback based on score
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
