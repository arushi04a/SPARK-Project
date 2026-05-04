import os
import json
import logging
import tempfile
import requests
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import fitz
from flask import Flask, render_template, request, jsonify
import os
import tempfile
import docx2txt
import PyPDF2
import json
import requests
import hashlib
from google import generativeai as genai

# ----------------------------
# ⚙ FLASK + GEMINI CONFIG
# ----------------------------
app = Flask(_name_)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.secret_key = "resume-analyzer"

# ✅ Gemini 2.0 Flash setup
GEMINI_API_KEY = "AIzaSyB7JdIy17Dza_KTDrCfZv8ltxC1yoTsT9U"  # <-- replace with your key
genai.configure(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-2.0-flash"

# ----------------------------
# 🧠 Caching System
# ----------------------------
CACHE_FILE = "cache.json"

DOMAIN_KNOWLEDGE = {
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
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)

cache = load_cache()

# ----------------------------
# 📄 File Text Extraction
# ----------------------------
def extract_text(file_path):
    text = ""
    ext = os.path.splitext(file_path)[-1].lower()

    if ext == ".pdf":
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                text += page.extract_text() or ""
    elif ext == ".docx":
        text = docx2txt.process(file_path)
    elif ext == ".txt":
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        raise ValueError("Unsupported file type")

    return text.strip()

# ----------------------------
# 🔍 Gemini Analysis Prompt
# ----------------------------
def analyze_with_gemini(resume_text, job_desc):
    prompt = f"""
    You are an ATS (Applicant Tracking System) and career mentor AI.
    Analyze this resume for the role described below.

    --- JOB DESCRIPTION ---
    {job_desc}

    --- RESUME ---
    {resume_text}

    Provide a JSON response with these keys:
    - ats_score (0–100)
    - matched_skills (list)
    - missing_skills (list)
    - extra_skills (list)
    - courses (list of recommended learning resources)
    - projects (list of project ideas)
    """

    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    text = response.text

    try:
        # Extract JSON safely from response
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        json_str = text[json_start:json_end]
        data = json.loads(json_str)
    except Exception:
        data = {"ats_score": 50, "matched_skills": [], "missing_skills": [], 
                "extra_skills": [], "courses": [], "projects": []}

    return data

# ----------------------------
# 💼 Job Search (Dummy or API)
# ----------------------------
def fetch_jobs(job_title):
    # Example: Adzuna, Indeed, or local dummy data
    # You can replace this later with a real API call
    dummy_jobs = [
        {"title": f"{job_title.title()} Intern", "company": "TechNova", "link": "https://example.com/job1"},
        {"title": f"Junior {job_title.title()}", "company": "DataMinds", "link": "https://example.com/job2"},
        {"title": f"Senior {job_title.title()} Engineer", "company": "AIWorks", "link": "https://example.com/job3"},
    ]
    return dummy_jobs

# ----------------------------
# 🧮 Flask Routes
# ----------------------------
@app.route("/")
def index():
    return render_template("ats.html")

@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        resume_file = request.files.get("resume")
        job_desc = request.form.get("description", "")

        if not resume_file or not job_desc:
            return jsonify({"error": "Missing resume or description"}), 400

        # Save uploaded file
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], resume_file.filename)
        resume_file.save(file_path)

        # Create cache key
        key = hashlib.md5((resume_file.filename + job_desc).encode()).hexdigest()
        if key in cache:
            print("✅ Using cached response")
            return jsonify(cache[key])

        # Extract resume text
        resume_text = extract_text(file_path)
        if not resume_text:
            return jsonify({"error": "Could not extract text"}), 400

        # Gemini analysis
        print("🤖 Analyzing with Gemini...")
        data = analyze_with_gemini(resume_text, job_desc)

        # Add jobs
        data["jobs"] = fetch_jobs(job_desc)

        # Cache result
        cache[key] = data
        save_cache(cache)

        return jsonify(data)

    except Exception as e:
        print("❌ Error:", e)
        return jsonify({"error": str(e)}), 500

import pytesseract
from pdf2image import convert_from_path
import docx2txt
from google import generativeai as genai


# ---------- CONFIG ----------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}
MAX_CONTENT_LENGTH = 10 * 1024 * 1024

# Gemini Setup
GEMINI_API_KEY = "AIzaSyB7JdIy17Dza_KTDrCfZv8ltxC1yoTsT9U"

# Configure the Gemini client
genai.configure(api_key=GEMINI_API_KEY)

# Choose your model
MODEL_NAME = "gemini-2.0-flash"

# Flask setup
app = Flask(_name_)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ats_app")

# ---------- HELPERS ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_pdf(filepath):
    """Extract text from PDF (fallback to OCR)."""
    text = ""
    try:
        with fitz.open(filepath) as doc:
            for page in doc:
                text += page.get_text("text")
        if text.strip():
            return text
    except Exception as e:
        logger.warning(f"PDF text extraction failed, trying OCR: {e}")
    try:
        images = convert_from_path(filepath)
        for img in images:
            text += pytesseract.image_to_string(img)
        return text
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        return ""

def extract_text_docx(filepath):
    try:
        return docx2txt.process(filepath)
    except Exception as e:
        logger.error(f"DOCX extraction failed: {e}")
        return ""

def extract_text_txt(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        logger.error(f"TXT extraction failed: {e}")
        return ""

def extract_text(filepath, filename):
    ext = filename.rsplit(".", 1)[1].lower()
    if ext == "pdf":
        return extract_text_pdf(filepath)
    elif ext == "docx":
        return extract_text_docx(filepath)
    elif ext == "txt":
        return extract_text_txt(filepath)
    return ""

# ---------- GEMINI LOGIC ----------
def analyze_with_gemini(resume_text, job_description):
    """Use Gemini to analyze ATS match and give recommendations."""
    prompt = f"""
You are an expert ATS evaluator and AI career coach.

Analyze the following resume and job description.

1. Calculate ATS match score (0–100)
2. List matched, missing, and extra skills.
3. Provide key feedback on resume.
4. Suggest 3–4 relevant online courses or notes links.
5. Suggest 2–3 practical projects to build for this job.
6. Suggest a short summary of the candidate fit.

Return your answer strictly in JSON format like this:
{{
  "ats_score": 85,
  "matched_skills": [...],
  "missing_skills": [...],
  "extra_skills": [...],
  "recommendations": [...],
  "projects": [...],
  "summary": "..."
}}

Resume:
{resume_text}

Job Description:
{job_description}
"""
    client = genai.GenerativeModel(MODEL_NAME)
    response = client.generate_content(prompt)
    try:
        data = json.loads(response.text)
        return data
    except Exception:
        return {"error": "Invalid response from Gemini", "raw": response.text}

# ---------- JOB API ----------
def fetch_live_jobs(query, location="India"):
    """Fetch job openings using JSearch (public endpoint)."""
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "x-rapidapi-key": "2b3efb1df0msh7b253cbdadfakeapi12345"  # Free demo key, replace if needed
    }
    params = {"query": query, "num_pages": 1, "country": "in"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        jobs = r.json().get("data", [])
        return [
            {
                "title": j.get("job_title"),
                "company": j.get("employer_name"),
                "location": j.get("job_city"),
                "url": j.get("job_apply_link")
            }
            for j in jobs[:5]
        ]
    except Exception as e:
        logger.error(f"Job API error: {e}")
        return []

# ---------- ROUTES ----------
@app.route("/")
def home():
    return render_template("ats.html")

@app.route("/api/analyze", methods=["POST"])
def analyze():
    file = request.files.get("file")
    job_description = request.form.get("job_description", "").strip()

    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Please upload a valid resume (PDF/DOCX/TXT)"}), 400
    if not job_description:
        return jsonify({"error": "Please enter a job description"}), 400

    filename = secure_filename(file.filename)
    with tempfile.NamedTemporaryFile(delete=False, dir=UPLOAD_FOLDER, suffix=os.path.splitext(filename)[1]) as tmp:
        file.save(tmp.name)
        filepath = tmp.name

    resume_text = extract_text(filepath, filename)
    os.unlink(filepath)

    if not resume_text.strip():
        return jsonify({"error": "Failed to extract text from resume"}), 400

    gemini_data = analyze_with_gemini(resume_text, job_description)
    jobs = fetch_live_jobs(job_description)

    return jsonify({"analysis": gemini_data, "jobs": jobs})

if _name_ == "_main_":
    app.run(debug=True)