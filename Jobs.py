from flask import Flask, render_template
import importlib

app = Flask(__name__)

# List of jobs (make sure filenames match these names)
JOB_ROLES = [
    "AI Engineer",
    "Blockchain Engineer",
    "Business Intelligence Engineer",
    "Business Analyst",
    "Cloud Computing Engineer",
    "Cybersecurity Engineer",
    "DevOps Engineer",
    "Deep Learning Engineer",
    "Data Scientist",
    "Data Analyst",
    "Data Engineer",
    "Ethical AI Engineer",
    "Edge AI Developer",
    "Full Stack Engineer",
    "Gen AI Engineer",
    "IoT Engineer",
    "LLM Engineer",
    "ML Engineer",
    "MLOps Engineer",
    "Robotics Engineer",
    "Back-End Developer",
    "Front-End Developer",
    "App Developer",
    "Web Developer"
]

@app.route("/")
def index():
    return render_template("jobs.html", jobs=JOB_ROLES)

@app.route("/<job_name>")
def job_page(job_name):
    """
    Dynamically import each job's Python file and return its page.
    Each job file must have a function `render_page()`
    that returns render_template("job_name.html").
    """
    module_name = f"roadmaps.{job_name.lower().replace(' ', '_')}"
    try:
        mod = importlib.import_module(module_name)
        return mod.render_page()
    except Exception as e:
        return f"<h1>Error loading {job_name}</h1><p>{e}</p>"

if __name__ == "__main__":
    app.run(debug=True)
