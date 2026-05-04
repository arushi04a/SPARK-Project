from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import google.generativeai as genai
import os
import json
from datetime import datetime
import logging

app = Flask(__name__)
app.secret_key = 'quiz-generator-secret-key-2024'
app.config['SESSION_TYPE'] = 'filesystem'
CORS(app, resources={r"/*": {"origins": "*"}})

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Configure Gemini AI - Direct API Key
GEMINI_API_KEY = "AIzaSyBbZIwwLYXvHKozDL1KEL65CikfUCoKM0o"
genai.configure(api_key=GEMINI_API_KEY)
logger.info("Gemini API Key configured successfully.")

# ---------------- Quiz Generator ----------------
class QuizGenerator:
    def __init__(self):
        self.domains = {
            "AI Engineer": "Machine learning algorithms, neural networks, deep learning frameworks, model optimization",
            "Blockchain Engineer": "Blockchain technology, smart contracts, cryptography, DeFi, Web3",
            "Cloud Computing Engineer": "AWS, Azure, GCP, cloud architecture, microservices, containerization",
            "Cybersecurity Engineer": "Network security, encryption, ethical hacking, vulnerability assessment",
            "Data Scientist": "Statistics, machine learning, data analysis, Python, R, data visualization",
            "DevOps Engineer": "CI/CD, containerization, infrastructure as code, monitoring, automation",
            "Full Stack Engineer": "Frontend frameworks, backend development, databases, APIs, web development",
            "Business Intelligence Engineer": "Data warehousing, ETL, reporting, business analytics",
            "Business Analyst": "Requirements gathering, process analysis, stakeholder management",
            "Deep Learning Engineer": "Neural networks, TensorFlow, PyTorch, computer vision, NLP",
            "Data Analyst": "SQL, data visualization, statistical analysis, Excel, reporting",
            "Data Engineer": "Data pipelines, ETL, Apache Spark, data warehousing, big data",
            "Ethical AI Engineer": "AI ethics, bias detection, fairness in ML, responsible AI",
            "Edge AI Developer": "Edge computing, IoT, embedded AI, model optimization for devices",
            "Gen AI Engineer": "Large language models, prompt engineering, GPT, generative AI",
            "IoT Engineer": "Internet of Things, sensors, embedded systems, connectivity protocols",
            "LLM Engineer": "Language models, fine-tuning, prompt engineering, NLP applications",
            "ML Engineer": "Machine learning pipelines, model deployment, MLOps, feature engineering",
            "MLOps Engineer": "ML model deployment, monitoring, versioning, automation",
            "Robotics Engineer": "Robot programming, control systems, sensors, automation",
            "Back-End Developer": "Server-side programming, APIs, databases, system architecture",
            "Front-End Developer": "HTML, CSS, JavaScript, React, Vue, user interfaces",
            "App Developer": "Mobile development, iOS, Android, cross-platform frameworks",
            "Web Developer": "Full-stack web development, frameworks, responsive design"
        }

    def generate_quiz_prompt(self, domain, difficulty, num_questions):
        domain_description = self.domains.get(domain, "General technology concepts")
        return f"""
        Create a {difficulty.lower()} level technical quiz for {domain} with exactly {num_questions} questions.
        Focus on: {domain_description}

        Question Types to use:
        - MCQ: Multiple Choice (single correct answer)
        - MSQ: Multiple Select (multiple correct answers)
        - CODING: Code analysis or prediction questions
        - NUMERIC: Numerical calculation questions

        Return ONLY a valid JSON array with this exact format:
        [
            {{
                "question": "Clear, specific question text",
                "type": "MCQ",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correct": ["Option B"],
                "explanation": "Detailed explanation of why this is correct"
            }},
            {{
                "question": "Another question",
                "type": "MSQ",
                "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
                "correct": ["Option 1", "Option 3"],
                "explanation": "Explanation for multiple correct answers"
            }}
        ]

        Requirements:
        - Generate exactly {num_questions} questions
        - Mix different question types appropriately
        - Ensure all questions are relevant to {domain}
        - Make difficulty appropriate for {difficulty.lower()} level
        - Provide clear, detailed explanations
        - For NUMERIC questions, use empty options array
        - For CODING questions, include code snippets in the question
        """

    def parse_quiz_response(self, response_text):
        try:
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            elif text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            questions = json.loads(text)
            if not isinstance(questions, list):
                return self.get_fallback_quiz()

            validated = []
            for i, q in enumerate(questions):
                try:
                    if not all(k in q for k in ['question', 'type', 'correct']):
                        continue
                    validated_q = {
                        'question': str(q['question']),
                        'type': str(q['type']).upper(),
                        'options': q.get('options', []),
                        'correct': [str(c) for c in (q['correct'] if isinstance(q['correct'], list) else [q['correct']])],
                        'explanation': q.get('explanation', 'No explanation provided.')
                    }
                    if validated_q['type'] not in ['MCQ', 'MSQ', 'CODING', 'NUMERIC']:
                        validated_q['type'] = 'MCQ'
                    validated.append(validated_q)
                except:
                    continue
            return validated if validated else self.get_fallback_quiz()
        except:
            return self.get_fallback_quiz()

    def get_fallback_quiz(self):
        return [
            {
                "question": "What does CPU stand for?",
                "type": "MCQ",
                "options": ["Central Processing Unit", "Computer Processing Unit", "Core Processing Unit", "Central Program Unit"],
                "correct": ["Central Processing Unit"],
                "explanation": "CPU stands for Central Processing Unit, the main component that executes instructions."
            },
            {
                "question": "Which of the following are programming languages?",
                "type": "MSQ",
                "options": ["Python", "HTML", "JavaScript", "CSS"],
                "correct": ["Python", "JavaScript"],
                "explanation": "Python and JavaScript are programming languages, while HTML and CSS are markup/styling languages."
            },
            {
                "question": "What is the result of 2^3?",
                "type": "NUMERIC",
                "options": [],
                "correct": ["8"],
                "explanation": "2 raised to the power of 3 equals 2 × 2 × 2 = 8."
            }
        ]

# ---------------- Routes ----------------
@app.route('/')
def index():
    return render_template('Quiz.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "AI Quiz Generator",
        "api_key_status": "configured",
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/generate-quiz', methods=['POST'])
def generate_quiz():
    try:
        data = request.get_json()
        domain = data.get('domain', 'Cloud Computing Engineer')
        difficulty = data.get('difficulty', 'Medium')
        num_questions = int(data.get('num_questions', 5))

        generator = QuizGenerator()
        prompt = generator.generate_quiz_prompt(domain, difficulty, num_questions)

        # Retry logic across multiple models
        model_names = [
            'models/gemini-1.5-flash',
            'models/gemini-1.5-flash-8b',
            'models/gemini-2.0-flash',
            'models/gemini-flash-latest'
        ]

        questions = generator.get_fallback_quiz()
        for model_name in model_names:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                if response and response.text:
                    questions = generator.parse_quiz_response(response.text)
                    break
            except Exception as e:
                if "429" in str(e) or "quota" in str(e).lower():
                    continue
                else:
                    continue

        while len(questions) < num_questions:
            questions.extend(generator.get_fallback_quiz())
        questions = questions[:num_questions]

        session['current_quiz'] = {
            'questions': questions,
            'domain': domain,
            'difficulty': difficulty,
            'generated_at': datetime.now().isoformat()
        }

        return jsonify({"success": True, "questions": questions})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/submit-answer', methods=['POST'])
def submit_answer():
    try:
        data = request.get_json()
        question_index = data.get('question_index')
        user_answer = data.get('answer', [])

        quiz_data = session.get('current_quiz', {}).get('questions', [])

        if question_index is None or question_index >= len(quiz_data):
            return jsonify({"success": False, "error": "Invalid question index"}), 400

        question = quiz_data[question_index]
        correct_answer = question.get('correct', [])

        user_normalized = sorted([str(x).lower().strip() for x in (user_answer if isinstance(user_answer, list) else [user_answer])])
        correct_normalized = sorted([str(x).lower().strip() for x in correct_answer])

        is_correct = user_normalized == correct_normalized
        score = 1 if is_correct else 0

        return jsonify({
            "success": True,
            "is_correct": is_correct,
            "correct_answer": correct_answer,
            "explanation": question.get('explanation', ''),
            "score": score
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------- Error Handlers ----------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({"success": False, "error": "Internal server error"}), 500


# ---------------- Run Server ----------------
if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='127.0.0.1', port=5000)
