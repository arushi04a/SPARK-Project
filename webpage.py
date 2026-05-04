# (Full patched file — paste this over your existing file)
import os
import re
import json
import time
import random
import logging
import hashlib
import tempfile
import threading
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask_cors import CORS
from werkzeug.utils import secure_filename
import csv, smtplib, pandas as pd, base64
from email.mime.text import MIMEText
from functools import wraps
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from groq import Groq 
# optional libs (import failures are tolerated)
try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

try:
    import docx2txt
except Exception:
    docx2txt = None

try:
    import pytesseract
    from pdf2image import convert_from_path
except Exception:
    pytesseract = None
    convert_from_path = None

# google generative AI (Gemini) SDK — optional
try:
    import google.generativeai as genai
except Exception:
    genai = None

# missing import for external API calls
try:
    import requests
except Exception:
    requests = None

# ---------------- CONFIG ----------------
# Directly hardcoded API keys (you may want to move these to env vars)
GEMINI_API_KEY_QUIZ = "AIzaSyAJS94TuJaQbgenjaVzng_WGATSptmsAk8"
GEMINI_API_KEY_RESUME = "AIzaSyCTtjXlxzC23oSneVNCT3SctsGbIh_N91I"
GROQ_API_KEY = "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"


# Uploads and cache defaults
UPLOAD_DIR = tempfile.gettempdir()
os.makedirs(UPLOAD_DIR, exist_ok=True)


# Resume cache: prefer env var RESUME_CACHE_FILE, else fall back to your original path
RESUME_CACHE_FILE = os.environ.get(
    "RESUME_CACHE_FILE",
    r"D:\village\codeProgram\Carrier_Catalyst\cache.json"
)

# Ensure directory exists for resume cache file
try:
    resume_cache_dir = os.path.dirname(RESUME_CACHE_FILE)
    if resume_cache_dir and not os.path.exists(resume_cache_dir):
        os.makedirs(resume_cache_dir, exist_ok=True)
except Exception:
    pass

ALLOWED_EXT = {"pdf", "docx", "txt"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB

# ---------------- Flask setup ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "quiz-generator-secret-key-2025")
app.config["SESSION_TYPE"] = "filesystem"
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
CORS(app)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("careermentor")

# lock for thread-safe genai.configure calls
gemini_config_lock = threading.Lock()

from functools import wraps

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("⚠️ Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ---------------- JSON file helpers (robust) ----------------
def load_json_file(path: str) -> Dict[str, Any]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    # empty file; treat as empty dict
                    return {}
                return json.loads(content)
    except Exception as e:
        logger.warning("Could not load JSON file %s: %s", path, e)
    return {}

def save_json_file(path: str, data: Dict[str, Any]):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning("Could not save JSON file %s: %s", path, e)

# Load caches (separate quiz & resume caches)
resume_cache = load_json_file(RESUME_CACHE_FILE)

# ---------------- Utility functions ----------------
def safe_text_from_response(resp: Any) -> str:
    """Extract reasonable textual output from various genai shapes or strings."""
    try:
        if resp is None:
            return ""
        if isinstance(resp, str):
            return resp.strip()

        if hasattr(resp, "text") and isinstance(resp.text, str):
            return resp.text.strip()

        if hasattr(resp, "candidates"):
            try:
                cands = list(resp.candidates)
                if cands:
                    c0 = cands[0]
                    content = getattr(c0, "content", None) or (c0 if isinstance(c0, dict) else None)
                    if content and hasattr(content, "parts"):
                        parts = getattr(content, "parts", [])
                        texts = []
                        for p in parts:
                            if hasattr(p, "text"):
                                texts.append(p.text)
                            elif isinstance(p, dict) and "text" in p:
                                texts.append(p["text"])
                        if texts:
                            return "\n".join(texts).strip()
                    return str(c0)
            except Exception:
                pass

        if isinstance(resp, dict):
            for k in ("text", "response", "content", "result"):
                v = resp.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
            if "candidates" in resp and isinstance(resp["candidates"], list) and resp["candidates"]:
                cand = resp["candidates"][0]
                if isinstance(cand, dict):
                    content = cand.get("content", {})
                    parts = content.get("parts", [])
                    if parts and isinstance(parts[0], dict):
                        return parts[0].get("text", "") or ""
        return str(resp).strip()
    except Exception as e:
        logger.debug("safe_text_from_response error: %s", e)
        try:
            return str(resp)
        except Exception:
            return ""

def is_json_like(s: str) -> bool:
    if not s:
        return False
    s = s.strip()
    return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))

def extract_text_from_file(filepath: str, filename: str) -> str:
    """Extract text for pdf/docx/txt with fallbacks."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    text = ""
    try:
        if ext == "pdf":
            if fitz:
                try:
                    with fitz.open(filepath) as doc:
                        for page in doc:
                            text += page.get_text("text") or ""
                except Exception as e:
                    logger.debug("PyMuPDF failed: %s", e)
            if not text:
                try:
                    import PyPDF2
                    with open(filepath, "rb") as f:
                        reader = PyPDF2.PdfReader(f)
                        for page in reader.pages:
                            text += page.extract_text() or ""
                except Exception as e:
                    logger.debug("PyPDF2 fallback failed: %s", e)
            if not text and pytesseract and convert_from_path:
                try:
                    images = convert_from_path(filepath)
                    for img in images:
                        text += pytesseract.image_to_string(img) or ""
                except Exception as e:
                    logger.debug("OCR fallback failed: %s", e)
        elif ext == "docx" and docx2txt:
            try:
                text = docx2txt.process(filepath) or ""
            except Exception as e:
                logger.debug("docx2txt failed: %s", e)
        elif ext == "txt":
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        else:
            logger.debug("Unsupported extension for extraction: %s", ext)
    except Exception as e:
        logger.warning("Text extraction failed: %s", e)
    return (text or "").strip()

def generate_with_gemini(api_key: str, model_name: str, prompt: str, timeout: int = 60, **kwargs) -> str:
    """Thread-safe call to genai. Returns text or empty string on failure."""
    if genai is None:
        logger.info("genai SDK not available on this environment.")
        return ""
    try:
        with gemini_config_lock:
            try:
                genai.configure(api_key=api_key)
            except Exception as e:
                logger.warning("genai.configure failed: %s", e)
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt, request_options={"timeout": timeout}, **kwargs)

            return safe_text_from_response(resp)
    except Exception as e:
        logger.warning("generate_with_gemini failed: %s", e)
        return ""

def safe_gemini_sequence(api_key: str, model_list: List[str], prompt: str, max_chars: Optional[int] = None) -> str:
    """Attempt models in order; return first plausible non-empty text."""
    if not genai:
        logger.info("genai SDK missing; safe_gemini_sequence will not call remote.")
        return ""
    if not api_key:
        logger.warning("No API key provided to safe_gemini_sequence.")
        return ""
    for model in model_list:
        try:
            txt = generate_with_gemini(api_key, model, prompt)
            if not txt:
                logger.debug("Model %s returned empty. Trying next.", model)
                continue
            txt = txt.strip()
            if max_chars:
                txt = txt[:max_chars]
            if txt:
                return txt
        except Exception as e:
            logger.warning("safe_gemini_sequence error for %s: %s", model, e)
            continue
    return ""

# ---------------- Quiz generator ----------------
QUIZ_MODELS = [
    "models/gemini-2.0-flash",
    "models/gemini-1.5-flash",
    "models/gemini-1.5-flash-8b",
    "models/gemini-2.0plus-flash"
]
CODING_DOMAINS = {
    "AI Engineer", "ML Engineer", "Data Scientist", "Data Engineer",
    "Deep Learning Engineer", "LLM Engineer", "Gen AI Engineer",
    "MLOps Engineer", "Full Stack Engineer", "Back-End Developer",
    "Front-End Developer", "App Developer", "Web Developer",
    "DevOps Engineer", "Cloud Computing Engineer", "IoT Engineer",
    "Robotics Engineer", "Blockchain Engineer"
}
NON_CODING_DOMAINS = {
    "Business Analyst", "Business Intelligence Engineer",
    "Ethical AI Engineer", "Edge AI Developer", "Cybersecurity Engineer"
}

class QuizGenerator:
    def __init__(self):
        self.domains  = {
            "AI Engineer": "Artificial intelligence fundamentals, supervised and unsupervised learning, reinforcement learning, neural networks, deep learning frameworks (TensorFlow, PyTorch, Keras), model evaluation, hyperparameter tuning, explainable AI (XAI), model optimization, deployment of AI models using APIs and cloud services.",
            "Blockchain Engineer": "Blockchain architecture, cryptographic hashing, distributed ledger technology, consensus algorithms (Proof of Work, Proof of Stake), smart contracts (Solidity, Ethereum, Hyperledger), decentralized applications (DApps), tokenomics, NFTs, DeFi, Web3 frameworks, blockchain scalability and security.",
            "Cloud Computing Engineer": "Cloud infrastructure design, virtualization, containerization (Docker, Kubernetes), AWS, Azure, GCP services, load balancing, auto-scaling, microservices, cloud security, cost optimization, serverless computing, DevOps integration, Infrastructure as Code (Terraform, CloudFormation).",
            "Cybersecurity Engineer": "Network and information security, firewalls, intrusion detection systems (IDS), encryption algorithms (AES, RSA), ethical hacking, penetration testing, vulnerability scanning, malware analysis, identity and access management (IAM), security operations center (SOC), SIEM tools, incident response, and threat intelligence.",
            "Data Scientist": "Statistics, probability, hypothesis testing, machine learning algorithms, data preprocessing, Python, R, NumPy, pandas, scikit-learn, feature engineering, model evaluation metrics, data visualization (Matplotlib, Seaborn, Plotly), big data (Hadoop, Spark), and predictive analytics.",
            "DevOps Engineer": "Continuous Integration/Continuous Deployment (CI/CD), Jenkins, GitHub Actions, Docker, Kubernetes, cloud automation, Infrastructure as Code (Ansible, Terraform), monitoring (Prometheus, Grafana), configuration management, system reliability engineering (SRE), logging, and performance optimization.",
            "Full Stack Engineer": "Frontend (HTML, CSS, JavaScript, React, Vue, Angular), backend (Node.js, Django, Flask, Express), RESTful APIs, databases (MySQL, PostgreSQL, MongoDB), authentication and authorization, version control (Git), deployment pipelines, scalability, and microservices architecture.",
            "Business Intelligence Engineer": "Data warehousing, ETL pipelines, SQL optimization, business analytics, Power BI, Tableau, Looker, reporting automation, OLAP cubes, data modeling, KPI measurement, dashboard design, predictive analytics, data governance, and decision support systems.",
            "Business Analyst": "Requirement elicitation, stakeholder management, business process modeling (BPMN), SWOT and GAP analysis, Agile methodology, SCRUM documentation, data-driven decision-making, user stories, UML diagrams, and performance metrics analysis.",
            "Deep Learning Engineer": "Artificial neural networks, convolutional neural networks (CNNs), recurrent networks (RNNs, LSTMs), attention mechanisms, transformers, computer vision, natural language processing (NLP), TensorFlow, PyTorch, autoencoders, GANs, transfer learning, and model optimization for GPU/TPU.",
            "Data Analyst": "Data cleaning, SQL queries, data aggregation, Excel, Power BI, Tableau, Python (pandas, NumPy), data visualization, exploratory data analysis (EDA), statistical inference, A/B testing, and storytelling with data for business insights.",
            "Data Engineer": "ETL pipeline development, Apache Spark, Kafka, Hadoop, data lakes, data warehousing (Redshift, Snowflake, BigQuery), Airflow, database optimization, schema design, data quality assurance, and distributed computing frameworks.",
            "Ethical AI Engineer": "AI governance, bias and fairness detection, model transparency, privacy-preserving ML, explainable AI (XAI), responsible AI development, regulatory compliance (GDPR, IEEE ethics), algorithmic accountability, and societal impact of AI systems.",
            "Edge AI Developer": "Edge computing, IoT integration, low-latency AI inference, model compression (quantization, pruning), embedded systems (Raspberry Pi, NVIDIA Jetson), TinyML, mobile AI deployment (TensorFlow Lite, CoreML), and real-time decision-making at the edge.",
            "Gen AI Engineer": "Generative AI models (GPT, Gemini, LLaMA), prompt engineering, multimodal AI (text, image, audio), fine-tuning LLMs, embeddings, retrieval-augmented generation (RAG), text-to-image models (Stable Diffusion, DALL·E), generative video/audio synthesis, and ethical generative AI.",
            "IoT Engineer": "IoT architecture, embedded systems, microcontrollers (Arduino, ESP32), connectivity protocols (MQTT, CoAP), edge computing, IoT cloud platforms (AWS IoT, Azure IoT Hub), sensor networks, real-time data streaming, and IoT security.",
            "LLM Engineer": "Large language model training, fine-tuning, tokenization, embeddings, transformer architectures, text generation, summarization, question answering, retrieval-augmented generation (RAG), model evaluation (BLEU, ROUGE, perplexity), and deployment optimization.",
            "ML Engineer": "Supervised and unsupervised ML, regression, classification, clustering, feature engineering, model evaluation (ROC, F1), ML pipelines, hyperparameter tuning, deployment (FastAPI, Flask), MLOps practices, and monitoring model drift.",
            "MLOps Engineer": "End-to-end ML lifecycle, model deployment automation, CI/CD for ML, data versioning (DVC), MLFlow, Kubeflow, container orchestration, experiment tracking, model serving (TensorFlow Serving), monitoring, retraining automation, and scalability.",
            "Robotics Engineer": "Kinematics, dynamics, control systems, robotics programming (ROS, Python, C++), sensor integration (LIDAR, cameras), path planning, SLAM, robotic vision, motion control, embedded systems, and human-robot interaction.",
            "Back-End Developer": "API development, RESTful and GraphQL APIs, Node.js, Express, Django, Flask, database management (SQL, NoSQL), authentication (OAuth, JWT), caching (Redis, Memcached), performance optimization, microservices, and cloud deployment.",
            "Front-End Developer": "HTML5, CSS3, JavaScript ES6+, frameworks (React, Angular, Vue), responsive design, accessibility (WCAG), cross-browser compatibility, Webpack/Babel, state management (Redux, Vuex), UX/UI design principles, performance optimization, and testing (Jest, Cypress).",
            "App Developer": "Mobile development (Android, iOS), cross-platform frameworks (Flutter, React Native), UI/UX design principles, Android Studio, Xcode, Swift, Kotlin, Firebase integration, RESTful APIs, push notifications, and mobile performance optimization.",
            "Web Developer": "Full-stack web development, HTML5, CSS3, JavaScript, frameworks (React, Vue, Angular), backend integration, responsive design, SEO best practices, APIs, Git, accessibility, security best practices (CORS, HTTPS), and deployment on AWS/Netlify/Vercel."
        }

    def generate_quiz_prompt(self, domain: str, difficulty: str, num_questions: int) -> str:
        domain_description = self.domains.get(domain, domain)
        difficulty = (difficulty or "medium").strip().capitalize()

        # Determine allowed question types by domain
        if domain in NON_CODING_DOMAINS:
            allowed_types = "MCQ | MSQ | NUMERIC"
        else:
            allowed_types = "MCQ | MSQ | NUMERIC | CODING-MCQ | CODING-WRITE"

        # Adjust difficulty rules
        if difficulty.lower() == "easy":
            type_rules = """
Question type rules:
- Only MCQ (single correct answer).
- Keep questions conceptual and straightforward.
"""
        elif difficulty.lower() == "medium":
            type_rules = """
Question type rules:
- Include MCQ, MSQ, and NUMERIC questions.
- Avoid coding tasks unless relevant to the domain.
"""
        elif difficulty.lower() == "hard":
            type_rules = """
Question type rules:
- Include complex conceptual questions.
- If domain involves programming, include some coding-related questions:
  - CODING-MCQ (find output)
  - CODING-WRITE (short code snippet)
- If non-coding domain, focus on scenario or case-based questions instead.
"""
        else:
            type_rules = "Create balanced technical questions suitable for intermediate learners."

        return f"""
You are an expert instructor for {domain_description}.
Generate exactly {num_questions} {difficulty}-level quiz questions for the domain "{domain}".

Return ONLY a valid JSON array of objects like:
[
  {{
    "question": "string",
    "type": "{allowed_types}",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],  // [] if not applicable
    "correct": ["Correct Answer(s) or code snippet"],
    "explanation": "Short explanation or reference solution."
  }}
]

Rules:
- Strictly follow valid JSON format (no markdown or comments).
- Ensure correctness and variety as per difficulty.
- Avoid coding questions if the domain does not require programming.
- Keep all code syntactically valid and readable when present.
- {type_rules}
"""

    def parse_quiz_response(self, response_text: str) -> List[Dict[str, Any]]:
        cleaned = (response_text or "").strip()
        try:
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end != -1 and end > start:
                candidate = cleaned[start:end + 1]
                parsed = json.loads(candidate)
                if isinstance(parsed, list):
                    return parsed
        except Exception:
            pass
        try:
            return json.loads(cleaned)
        except Exception:
            objs = re.findall(r"\{(?:[^{}]|(?R))*\}", cleaned, re.DOTALL)
            parsed = []
            for o in objs:
                try:
                    parsed.append(json.loads(o))
                except Exception:
                    continue
            return parsed
        return []
        
    def get_fallback_quiz(self) -> List[Dict[str, Any]]:
        return [{
            "question": "What does AI stand for?",
            "type": "MCQ",
            "options": ["Artificial Intelligence", "Automated Input", "Algorithmic Interface", "Advanced Integration"],
            "correct": ["Artificial Intelligence"],
            "explanation": "AI stands for Artificial Intelligence."
        }]
# ---------------- Optimized parallel quiz generation ----------------
def safe_gemini_call(api_key: str, model_name: str, prompt: str, max_chars: Optional[int] = None) -> str:
    """Safe single-model Gemini call used for parallel generation."""
    try:
        text = generate_with_gemini(api_key, model_name, prompt)
        if not text:
            return ""
        text = text.strip()
        if max_chars:
            text = text[:max_chars]
        return text
    except Exception as e:
        logger.warning("safe_gemini_call error for %s: %s", model_name, e)
        return ""

def generate_quiz_parallel(domain: str, difficulty: str, num_questions: int, api_key: Optional[str] = None) -> List[Dict[str, Any]]:
    qg = QuizGenerator()
    api = api_key or GEMINI_API_KEY_QUIZ
    if not api or genai is None:
        logger.warning("Gemini unavailable; using fallback quiz.")
        return qg.get_fallback_quiz() * (num_questions or 1)

    prompt = qg.generate_quiz_prompt(domain, difficulty, num_questions)

    # Use ThreadPoolExecutor to call multiple Gemini models simultaneously
    def call_model(model):
        try:
            response = safe_gemini_call(api, model, prompt, max_chars=15000)
            if response and "[" in response:
                return response
        except Exception as e:
            logger.warning("Model %s failed: %s", model, e)
        return None

    with ThreadPoolExecutor(max_workers=min(len(QUIZ_MODELS), 4)) as executor:
        futures = {executor.submit(call_model, model): model for model in QUIZ_MODELS}
        for future in as_completed(futures):
            result = future.result()
            if result:
                try:
                    parsed = qg.parse_quiz_response(result)
                    if parsed:
                        logger.info("✅ Quiz generated successfully using %s", futures[future])
                        return parsed[:num_questions]
                except Exception:
                    continue

    logger.warning("All models failed — returning fallback quiz.")
    return qg.get_fallback_quiz() * (num_questions or 1)

# ---------------- Quiz API ----------------
@app.route("/api/generate_quiz", methods=["POST"])
def api_generate_quiz():
    """Generate quiz using parallel Gemini calls"""
    try:
        data = request.get_json(force=True, silent=True) or {}
        domain = data.get("domain", "AI Engineer")
        difficulty = data.get("difficulty", "Medium")
        num_questions = int(data.get("num_questions", 10))
        api_key = data.get("api_key") or GEMINI_API_KEY_QUIZ

        logger.info("Parallel quiz generation started: %s (%s) x%s", domain, difficulty, num_questions)
        questions = generate_quiz_parallel(domain, difficulty, num_questions, api_key=api_key)

        formatted = [
            {
                "question": q.get("question", ""),
                "options": q.get("options", []),
                "type": q.get("type", "MCQ"),
                "correct": q.get("correct", []),
                "explanation": q.get("explanation", "")
            }
            for q in questions
        ]

        session["current_quiz"] = {
            "questions": formatted,
            "domain": domain,
            "difficulty": difficulty,
            "generated_at": datetime.now().isoformat()
        }
        return jsonify({"success": True, "questions": formatted})
    except Exception as e:
        logger.exception("Quiz generation failed:")
        return jsonify({"success": False, "error": str(e), "questions": []}), 500


@app.route('/api/submit-quiz', methods=['POST'])
def api_submit_quiz():
    """Evaluate submitted answers against the session-stored quiz and return score."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        answers = data.get('answers', []) or []
        current = session.get('current_quiz') or {}
        questions = current.get('questions', []) or []

        total = len(questions)
        correct = 0

        for idx, q in enumerate(questions):
            correct_vals = q.get('correct', [])
            if not isinstance(correct_vals, list):
                correct_vals = [correct_vals]
            correct_norm = [str(c).strip().lower() for c in correct_vals if c is not None]

            if idx >= len(answers):
                continue
            ans = answers[idx]

            if isinstance(ans, list):
                user_norm = [str(a).strip().lower() for a in ans if a is not None]
                try:
                    if set(user_norm) == set(correct_norm):
                        correct += 1
                except Exception:
                    pass
            else:
                try:
                    if str(ans).strip().lower() in correct_norm:
                        correct += 1
                except Exception:
                    pass

        score_percent = round((correct / total) * 100, 2) if total > 0 else 0.0

        return jsonify({
            'success': True,
            'correct': correct,
            'total': total,
            'score_percent': score_percent,
            'ai_explanation': None
        })
    except Exception as e:
        logger.exception('submit-quiz failed')
        return jsonify({'success': False, 'error': str(e)}), 500


# ================================================================
# 🔹 Core Logic — Resume Analysis
# ================================================================
MODEL_MAIN = "models/gemini-2.0-flash"  # 🧠 Gemini model for advice + recommendations

# ================================================================
# 🔹 Helper — Gemini Call
# ================================================================
def call_gemini_model(api_key: str, prompt: str, timeout: int = 60) -> str:
    """Call Gemini safely with timeout and handle both v1beta and new response structures."""
    import concurrent.futures, json

    def run():
        try:
            if genai is None:
                logger.warning("genai SDK not available in environment.")
                return '{"error": "Gemini SDK not installed"}'

            genai.configure(api_key=api_key)
            model_name = MODEL_MAIN.replace("models/", "")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)

            # Extract text safely
            text = ""
            try:
                if hasattr(response, "text") and response.text:
                    text = response.text
                elif hasattr(response, "candidates"):
                    text = response.candidates[0].content.parts[0].text
                elif isinstance(response, dict) and "candidates" in response:
                    text = response["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    text = str(response)
            except Exception as e:
                logger.warning("Text extraction failed: %s", e)
                text = str(response)

            if not text.strip():
                logger.warning("Gemini returned empty text for model %s", model_name)
                return '{"error": "Empty Gemini response"}'
            return text

        except Exception as e:
            logger.warning("Gemini call failed: %s", e)
            return json.dumps({"error": str(e)})

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(run)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.warning("Gemini timed out after %ss", timeout)
            return '{"error": "Timeout"}'


# ================================================================
# 🔹 UPDATED Helper — Groq ATS Score (replaces AssemblyAI)
# ================================================================
def compute_ats_score(resume_text: str, job_desc: str) -> int:
    """Compute ATS score using Groq LLM with strict JSON output."""

    def fallback_score(resume_text, job_desc):
        r_words = set(re.sub(r"[^\w\s]", " ", resume_text.lower()).split())
        j_words = set(re.sub(r"[^\w\s]", " ", job_desc.lower()).split())
        overlap = len(r_words & j_words)
        score = int((overlap / max(1, len(j_words))) * 100)
        return max(0, min(90, score))

    if not GROQ_API_KEY:
        return fallback_score(resume_text, job_desc)

    try:
        client = Groq(api_key=GROQ_API_KEY)

        prompt = f"""
You are an ATS scoring system.
Analyze the resume and job description.

Return ONLY a JSON object EXACTLY like this:
{{
  "ats_score": 78
}}

Rules:
- Only one key: "ats_score"
- Value must be an integer from 0 to 100
- No additional explanation
- No additional text
- No percentage signs

Resume:
{resume_text[:5000]}

Job Description:
{job_desc[:2000]}
"""

        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )

        raw = response.choices[0].message.content.strip()

        # Remove accidental markdown fences
        raw = raw.replace("```json", "").replace("```", "").strip()

        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            data = json.loads(match.group(0))
            score = int(data.get("ats_score", 50))
            return max(0, min(100, score))

        return fallback_score(resume_text, job_desc)

    except Exception as e:
        logger.warning(f"Groq ATS call failed: {e}")
        return fallback_score(resume_text, job_desc)



# ================================================================
# 🔹 Gemini Recommendations (fixed JSON template)
# ================================================================
def get_gemini_recommendations(resume_text: str, job_desc: str, api_key: str) -> dict:
    """Generate advice, courses, projects, and jobs from Gemini using safe JSON extraction."""

    json_template = """
{
  "advice": "4-5 sentence personalized advice.",
  "recommended_courses": [
    {"name": "Course Name", "platform": "Platform", "url": "https://..."}
  ],
  "project_ideas": ["Idea 1", "Idea 2", "Idea 3"],
  "job_openings": [
    {"title": "Job Title", "platform": "Platform", "url": "https://..."}
  ]
}
"""

    prompt = (
        "You are a senior career coach.\n"
        "Return ONLY valid JSON (no text before or after it) using this structure:\n"
        + json_template +
        f"\n\nResume:\n{resume_text[:3500]}\n\n"
        f"Job Description:\n{job_desc[:1500]}\n"
    )

    raw = call_gemini_model(api_key, prompt, timeout=40)

    # --- FIX: Clean markdown fences ---
    raw = raw.strip()
    raw = re.sub(r"```(json)?", "", raw).replace("```", "").strip()

    # --- FIX: Extract JSON safely ---
    try:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"[Gemini JSON Parse Error] {e}")

    return {}


# ================================================================
# 🔹 Core — Resume Analysis Orchestrator
# ================================================================
def agentic_resume_analysis(resume_text: str, job_desc: str = "") -> dict:
    # 1️⃣ ATS Score → Groq
    ats_score = compute_ats_score(resume_text, job_desc)

    # 2️⃣ Recommendations → Gemini
    gemini_data = get_gemini_recommendations(
        resume_text,
        job_desc,
        GEMINI_API_KEY_RESUME
    )

    # 3️⃣ Fallback if Gemini fails
    if not gemini_data:
        gemini_data = {
            "advice": "Improve resume structure, highlight achievements, and tailor for the job role.",
            "recommended_courses": [],
            "project_ideas": [],
            "job_openings": []
        }

    return {
        "ats_score": ats_score,
        "advice": gemini_data.get("advice", ""),
        "recommended_courses": gemini_data.get("recommended_courses", []),
        "project_ideas": gemini_data.get("project_ideas", []),
        "job_openings": gemini_data.get("job_openings", [])
    }

# ================================================================
# 🔹 Flask Route — Resume Analysis
# ================================================================
@app.route("/api/analyze_resume", methods=["POST"])
def api_analyze_resume():
    try:
        # File upload
        if "resume" in request.files:
            file = request.files["resume"]
            job_desc = request.form.get("description", "")
            filename = secure_filename(file.filename)
            filepath = os.path.join(UPLOAD_DIR, filename)
            file.save(filepath)
            resume_text = extract_text_from_file(filepath, filename)

        # Raw text mode
        else:
            data = request.get_json(force=True)
            resume_text = data.get("resume_text", "")
            job_desc = data.get("job_desc", "")

        if not resume_text.strip():
            return jsonify({"success": False, "error": "Empty resume text"}), 400

        key_hash = hashlib.sha256((resume_text + job_desc).encode()).hexdigest()

        if key_hash in resume_cache:
            return jsonify({"success": True, "cached": True, "result": resume_cache[key_hash]})

        result = agentic_resume_analysis(resume_text, job_desc)

        resume_cache[key_hash] = result
        save_json_file(RESUME_CACHE_FILE, resume_cache)

        return jsonify({"success": True, "cached": False, "result": result})

    except Exception as e:
        logger.exception("Resume analysis failed.")
        return jsonify({"success": False, "error": str(e)}), 500


# ---------------- Simple pages ----------------
JOB_ROLES = [
    "AI Engineer", "Blockchain Engineer", "Business Intelligence Engineer", "Business Analyst",
    "Cloud Computing Engineer", "Cybersecurity Engineer", "DevOps Engineer", "Deep Learning Engineer",
    "Data Scientist", "Data Analyst", "Data Engineer", "Ethical AI Engineer", "Edge AI Developer",
    "Full Stack Engineer", "Gen AI Engineer", "IoT Engineer", "LLM Engineer", "ML Engineer", "MLOps Engineer",
    "Robotics Engineer", "Back-End Developer", "Front-End Developer", "App Developer", "Web Developer", "Software Engineer"
    , "Embedded System Engineer", "Big Data Engineer", "AI Research Scientist"]

@app.route("/")
def home():
    return render_template("webpage.html")

@app.route("/resume")
@login_required
def resume_page():
    return render_template("ats.html")


@app.route("/quiz/<domain>")
@login_required
def quiz_page(domain):
    try:
        return render_template("Quiz.html", domain=domain)
    except Exception:
        return jsonify({"domain": domain})

@app.route("/team")
def team_page():
    return render_template("team.html")

@app.route("/privacy-policy")
def privacy_policy():
    return render_template("policies.html")

@app.route("/terms-of-service")
def terms_of_service():
    return render_template("policies.html")

@app.route("/ai-ethics-policy")
def ai_ethics_policy():
    return render_template("policies.html")

@app.route("/quiz")
def quiz_page_root():
    """Render quiz page using quiz stored in session (generated on demand)."""
    try:
        current = session.get("current_quiz")
        return render_template("Quiz.html", quiz=current)
    except Exception:
        return render_template("Quiz.html")

@app.route("/explore_jobs")
def explore_jobs():
    try:
        return render_template("jobs.html", jobs=JOB_ROLES)
    except Exception:
        return jsonify({"jobs": JOB_ROLES})

@app.route("/job/<job_name>")
def job_page(job_name):
    module_name = job_name.lower().strip()
    # sanitize: keep a-z0-9 and underscores only
    module_name = re.sub(r'[^a-z0-9_]+', '_', module_name)
    module_name = module_name.strip('_')
    logger.info("Requested job: %s → Module: %s", job_name, module_name)
    try:
        import importlib
        mod = importlib.import_module(f"roadmaps.{module_name}")
        if hasattr(mod, "render_page"):
            return mod.render_page()
        elif hasattr(mod, "main"):
            return mod.main()
        else:
            raise AttributeError(f"{module_name} missing render_page() or main()")
    except Exception as e:
        logger.warning("Could not import roadmap module: %s", e)
        try:
            return render_template(f"roadmaps/{module_name}.html")
        except Exception:
            return f"<h1>Module '{module_name}' not found</h1><p>{e}</p>", 404
        

# ==========================================================
# 📩 FEEDBACK SYSTEM ROUTES — Integrated into webpage.py
# ==========================================================
from flask_mail import Mail, Message
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from flask_cors import CORS
import random, os, json
from datetime import datetime

# Enable CORS (if not already)
CORS(app)

# ==========================================================
# 📨 Gmail Configuration (App Password required)
# ==========================================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'rizult70@gmail.com'
app.config['MAIL_PASSWORD'] = 'rasf mylr bxhw hbtd'
app.config['MAIL_DEFAULT_SENDER'] = ('AI Feedback System', 'rizult70@gmail.com')

mail = Mail(app)

# ==========================================================
# 🌐 Feedback Routes
# ==========================================================
@app.route("/feedback")
def feedback_form():
    """Serve Feedback HTML form"""
    return render_template("Feedback.html")


@app.route("/feedback/analyze", methods=["POST"])
def feedback_analyze():
    """Handle feedback submission + AI analysis + email"""
    try:
        if not request.is_json:
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400

        data = request.get_json()
        required_fields = ["name", "email", "rating"]
        for field in required_fields:
            if not data.get(field):
                return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400

        name = data["name"]
        email = data["email"]
        rating = int(data["rating"])
        experience = data.get("experience", "")
        improvements = data.get("improvements", "")

        print(f"✅ Processing feedback from {name} ({email})")

        # ======================================================
        # 🤖 Real Sentiment Analysis using VADER
        # ======================================================
        analyzer = SentimentIntensityAnalyzer()
        feedback_text = (experience + " " + improvements).strip().lower()
        score = analyzer.polarity_scores(feedback_text)
        compound = score["compound"]

        # Combine text sentiment + numeric rating
        if compound >= 0.3 and rating >= 4:
            sentiment = "Positive"
        elif compound <= -0.3 or rating <= 2:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"

        priority = "High" if sentiment == "Negative" else "Medium" if sentiment == "Neutral" else "Low"
        confidence = int(abs(compound) * 100) if abs(compound) > 0 else random.randint(75, 85)

        # Minimal AI result
        analysis = {
            "sentiment": sentiment,
            "priority": priority,
            "rating": rating,
            "confidence": confidence,
        }

        # ======================================================
        # ✉️ Send Email
        # ======================================================
        try:
            msg = Message(
                subject=f"Your Feedback Confirmation - {name}",
                recipients=[email],
            )

            msg.body = f"""
Hi {name},

Thank you for submitting your feedback!
We’ve successfully received your response.

Summary:
- Rating: {rating}/5
- Sentiment: {sentiment}
- Confidence: {confidence}%
- Priority: {priority}

Our team will review your feedback carefully to improve your experience.

Best regards,
The AI Feedback System
            """
            mail.send(msg)
            print(f"📧 Email sent successfully to {email}")

        except Exception as email_error:
            print(f"⚠️ Email sending failed: {email_error}")

        return jsonify({
            "status": "success",
            "message": "✅ Feedback submitted successfully! You’ll receive a confirmation email shortly."
        }), 200

    except Exception as e:
        print(f"🔥 Error in /feedback/analyze: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ==============================================================
# 👤 USER AUTHENTICATION + DASHBOARD (Unified)
# ==============================================================

# Paths
USERS_CSV = r"D:\village\codeProgram\Carrier_Catalyst\users.csv"
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Email setup (OTP)
SENDER_EMAIL = "careersparky@gmail.com"
APP_PASSWORD = "zmrz wonu nzga edqg"  # Gmail App Password

# ---------------- HELPERS ----------------
def read_users():
    """Read all user data from CSV"""
    if not os.path.exists(USERS_CSV):
        with open(USERS_CSV, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "email", "password", "name", "phone", "location",
                "linkedin", "github", "title", "memberSince", "photo"
            ])
            writer.writeheader()
        return []
    with open(USERS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_users(users):
    """Write user list to CSV"""
    if not users:
        return
    with open(USERS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=users[0].keys())
        writer.writeheader()
        writer.writerows(users)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(input_password, stored_hash):
    return hash_password(input_password) == stored_hash


def send_otp(receiver_email):
    """Send OTP via Gmail"""
    otp = str(random.randint(100000, 999999))
    msg = MIMEText(f"Your CareerMentor OTP is: {otp}")
    msg["Subject"] = "CareerMentor Email Verification"
    msg["From"] = SENDER_EMAIL
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✅ OTP sent to {receiver_email}: {otp}")
        return otp
    except Exception as e:
        print("❌ Email sending failed:", e)
        raise e


# ---------------- LOGIN REQUIRED DECORATOR ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("⚠️ Please log in first.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# 🔹 AUTH ROUTES
# ============================================================

@app.route("/signup", methods=["GET", "POST"])
def signup():
    users = read_users()
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if any(u["email"] == email for u in users):
            flash("⚠️ Email already registered! Please log in.", "warning")
            return redirect(url_for("login"))
        try:
            otp = send_otp(email)
            session["pending_email"] = email
            session["otp"] = otp
            flash(f"✅ OTP sent to {email}. Check your inbox.", "success")
            return redirect(url_for("verify_otp"))
        except Exception as e:
            flash(f"❌ Failed to send OTP: {e}", "error")
    return render_template("auth.html", step="signup_email")


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    """Verify OTP step"""
    if "otp" not in session:
        flash("⚠️ Please start signup again.", "warning")
        return redirect(url_for("signup"))

    if request.method == "POST":
        otp_input = request.form.get("otp", "").strip()
        if otp_input == session.get("otp"):
            flash("🎉 OTP verified! Now create your password.", "success")
            return redirect(url_for("create_password"))
        else:
            flash("❌ Incorrect OTP. Try again.", "error")
    return render_template("auth.html", step="otp")


@app.route("/create_password", methods=["GET", "POST"])
def create_password():
    """Create password after OTP verification"""
    if "pending_email" not in session:
        flash("⚠️ Session expired. Please start signup again.", "warning")
        return redirect(url_for("signup"))

    users = read_users()
    if request.method == "POST":
        password = request.form["password"].strip()
        email = session["pending_email"]
        hashed = hash_password(password)

        new_user = {
            "email": email,
            "password": hashed,
            "name": "",
            "phone": "",
            "location": "",
            "linkedin": "",
            "github": "",
            "title": "",
            "memberSince": datetime.now().strftime("%Y-%m-%d"),
            "photo": "/static/uploads/default.png"
        }

        users.append(new_user)
        write_users(users)
        session.clear()
        session["user"] = new_user

        flash("✅ Account created successfully!", "success")
        return redirect(url_for("home"))  # ✅ Redirects directly to homepage

    return render_template("auth.html", step="password", email=session["pending_email"])


@app.route("/login", methods=["GET", "POST"])
def login():
    """User login"""
    users = read_users()
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"].strip()

        for user in users:
            if user["email"].lower() == email and verify_password(password, user["password"]):
                session["user"] = user
                flash("✅ Login successful!", "success")
                return redirect(url_for("home"))  # ✅ Homepage after login

        flash("❌ Invalid email or password", "error")
    return render_template("auth.html", step="login")


@app.route("/dashboard")
@login_required
def dashboard():
    """Legacy dashboard (kept for reference)"""
    return render_template("webpage.html", user=session["user"])


@app.route("/update_user", methods=["POST"])
@login_required
def update_user():
    """Update user profile info (supports base64 photo)"""
    data = request.get_json() or {}
    email = session["user"]["email"]
    users = read_users()

    for user in users:
        if user["email"].lower() == email.lower():
            # Text fields
            for field in ["name", "phone", "location", "linkedin", "github", "title"]:
                if data.get(field):
                    user[field] = data[field]

            # ✅ Handle Base64 photo uploads
            if data.get("photo", "").startswith("data:image"):
                header, encoded = data["photo"].split(",", 1)
                image_data = base64.b64decode(encoded)
                filename = email.replace("@", "_") + ".png"
                save_path = os.path.join(UPLOAD_FOLDER, filename)
                with open(save_path, "wb") as f:
                    f.write(image_data)
                user["photo"] = f"/static/uploads/{filename}"

            session["user"] = user
            break

    write_users(users)
    return jsonify({"success": True})


@app.route("/get_user_data")
def get_user_data():
    """Return logged-in user data for sidebar"""
    if "user" not in session:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify(session["user"])


@app.route("/logout")
def logout():
    """Logout the current user"""
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))

client = Groq(api_key=GROQ_API_KEY)

@app.route("/chatbot", methods=["POST"])
def chatbot():
    if "user" not in session:
        return jsonify({"reply": "Please login to talk to Sparky 😊"}), 403

    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"reply": "Please type something for Sparky 😊"})

        # --------------------------
        # SYSTEM PROMPT (Website Brain)
        # --------------------------
        SYSTEM_PROMPT = """
You are Sparky — the friendly AI assistant of CareerMentor.

You MUST know everything about the platform:

CareerMentor Features:
1. Resume Analyzer  
   - Gives ATS Score  
   - Highlights skill gaps  
   - Gives resume improvement tips  
   - Helps with formatting  
   - Gives suggestions for job roles  

2. Domain Quiz  
   - Users take quizzes in domains like AI, Web Dev, Data Science, Cybersecurity  
   - You give supportive feedback  
   -  Focus on strengths-first guidance  

3. Career Roadmap  
   - Users explore career paths  
   - You guide them with skills, tools, certifications and steps  

4. User Dashboard  
   - Users have their profile: name, email, phone, location, LinkedIn, GitHub  
   - You can use this info to personalize answers  

5. Sparky Chatbot  
   - You explain features  
   - Answer questions  
   - Motivate the user  
   - Help with interview prep  
   - Suggest skills  
   - Give clear, simple, helpful advice  

Tone Rules:
- Supportive, friendly, positive  
- Encourage the user  
- No negative or harsh tone  
- Strengths-first approach  
- Use bullet points if helpful  

If user asks:
- “What is this website?”
- “Explain your features”
- “What can you do?”
→ Give a full explanation using the above knowledge.
        """

        # --------------------------
        # SEND TO GROQ MODEL
        # --------------------------
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        )

        bot_reply = response.choices[0].message.content.strip()
        return jsonify({"reply": bot_reply})

    except Exception as e:
        print("Chatbot Error:", e)
        return jsonify({"reply": "Sparky is facing an error. Please try again later 🙏"}), 500


                        
                        
# ---------------- Run server ----------------
if __name__ == "__main__":
    # ensure templates dir exists for simple dev testing
    os.makedirs("templates", exist_ok=True)
    logger.info("Starting CareerMentor on http://127.0.0.1:5000")
    app.run(debug=True, host="127.0.0.1", port=5000)
