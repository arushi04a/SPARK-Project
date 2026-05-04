# SPARK — Career Mentor Platform

SPARK is a comprehensive career mentorship platform built using **Flask (Python)**.
It provides resume analysis, AI-powered quizzes, domain roadmaps, and personalized career insights.
The platform also includes **Sparky**, an AI chatbot powered by **Groq API** for real-time guidance.

---

##🌟 Overview

SPARK integrates multiple AI-driven modules to deliver a complete career support system:

*📄 Resume Analysis (ATS + AI Suggestions)
*🧠 AI-Based Domain Quiz (24 domains)
*🛣️ 26 Structured Career Roadmaps
*🤖 Sparky — Real-time AI Chatbot
*🔐 User Authentication System
*🎨 Modern Frontend (HTML/CSS/JS)

---

## ✨ Features

### 🧾 Resume Analysis

**ATS Score (Groq API)**

* Model: **LLaMA 3.1B-Instant**
* Evaluates keyword match, resume structure, job-role alignment, and skills  

**AI-Powered Suggestions (Gemini API)**

* Provides personalized recommendations to improve resume quality  

**Course Suggestions (Gemini API)**

* Recommends relevant courses based on resume analysis  

**Project Recommendations**

* Suggests projects aligned with user skills and target job roles  

**Job Openings**

* Displays currently active job opportunities across platforms  

---
## 🧠 AI Domain Quiz (24 Domains)

### Powered by Gemini API

Automatically generates domain-specific quizzes.

### Difficulty Levels

* **Easy** → MCQ + MSQ
* **Medium** → MCQ + MSQ + Numeric
* **Hard** → MSQ + Coding Questions

### Question Types

* MCQ
* MSQ
* Numerics
* Coding Problems (Hard level)

### Domain Output

* Quiz Result
* Every Question description is provided

---

## 🛣️ 26 Career Roadmaps

Each roadmap includes:

* Step-by-step learning path
* Tools & technologies to master
* Recommended courses & resources
* Portfolio project ideas
* Certifications

---

## 🤖 Sparky — AI Chatbot (Groq API)

Sparky helps users with:

* Career questions
* Roadmap guidance
* Technology updates

Powered by **Groq API** for fast and accurate responses.

---

## 📦 Project Structure

```plaintext
Carrier_Catalyst/
│
├── backend/
│   ├── webpage.py            # Main Flask application
│   ├── ats.py                # Groq ATS using LLaMA 3.1B-Instant
│   ├── quiz.py               # Gemini-powered domain quiz
│   ├── roadmap.py            # 26-domain roadmap generator
│   ├── auth.py               # Login/auth system
│   ├── feedback.py           # Gemini-powered resume advice
│
├── templates/
│   ├── webpage.html
│   ├── login.html
│   ├── quiz.html
│   ├── jobs.html
│   ├── feedback.html
│   ├── roadmaps/
│       ├──Data_scientist.html
│       ├── many more ....
│
├── static/
│   └── images/
|
├──Roadmps/
│   ├── Data_scientist.py
│   ├── many more...

```

---

## ⚡ Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/arushi04a/SPARK-Project.git
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### Activate Environment

Windows:

```bash
venv\Scripts\activate
```

macOS/Linux:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the Application

### Option A — Flask CLI

Windows:

```bash
set FLASK_APP=backend.webpage
flask run
```

macOS/Linux:

```bash
export FLASK_APP=backend.webpage
flask run
```

### Option B — Direct run

```bash
python backend/webpage.py
```

### Option C — Using run.py

```bash
python run.py
```

---

## 🔧 Dependencies

* Flask
* python-dotenv
* requests
* Groq API (LLaMA 3.1B-Instant)
* Gemini API
* pdfminer / python-docx

---



## 👤 Author
arushi 


