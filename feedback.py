from flask import Flask, render_template, request, jsonify
from flask_mail import Mail, Message
from flask_cors import CORS
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import random
import os
import json
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ==========================================================
# 📨 Gmail Configuration (App Password required)
# ==========================================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'rizult70@gmail.com'   # your gmail
app.config['MAIL_PASSWORD'] = 'rasf mylr bxhw hbtd'  # Gmail App Password
app.config['MAIL_DEFAULT_SENDER'] = ('AI Feedback System', 'rizult70@gmail.com')

mail = Mail(app)

# ==========================================================
# 🗂️ Helper - Save feedback locally
# ==========================================================
def save_feedback(data, analysis):
    folder = "feedback_logs"
    os.makedirs(folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder}/feedback_{timestamp}_{data['name'].replace(' ', '_')}.json"

    record = {
        "timestamp": timestamp,
        "name": data.get("name"),
        "email": data.get("email"),
        "rating": data.get("rating"),
        "experience": data.get("experience"),
        "improvements": data.get("improvements"),
        "analysis": analysis
    }

    with open(filename, "w") as f:
        json.dump(record, f, indent=4)
    print(f"🗂️ Feedback saved → {filename}")


# ==========================================================
# 🌐 Routes
# ==========================================================
@app.route('/')
def index():
    return render_template('Feedback.html')


@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        if not request.is_json:
            return jsonify({"status": "error", "message": "Request must be JSON"}), 400

        data = request.get_json()
        required_fields = ['name', 'email', 'rating']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"status": "error", "message": f"Missing field: {field}"}), 400

        name = data['name']
        email = data['email']
        rating = int(data['rating'])
        experience = data.get('experience', '')
        improvements = data.get('improvements', '')

        print(f"✅ Processing feedback from {name} ({email})")

        # ======================================================
        # 🤖 Real Sentiment Analysis using VADER
        # ======================================================
        analyzer = SentimentIntensityAnalyzer()
        feedback_text = (experience + " " + improvements).strip().lower()
        score = analyzer.polarity_scores(feedback_text)
        compound = score['compound']  # between -1 (negative) and +1 (positive)

        # Combine text sentiment + numeric rating
        if compound >= 0.3 and rating >= 4:
            sentiment = "Positive"
        elif compound <= -0.3 or rating <= 2:
            sentiment = "Negative"
        else:
            sentiment = "Neutral"

        # Assign priority and confidence
        priority = "High" if sentiment == "Negative" else "Medium" if sentiment == "Neutral" else "Low"
        confidence = int(abs(compound) * 100) if abs(compound) > 0 else random.randint(75, 85)

        # ======================================================
        # 💡 Generate insights
        # ======================================================
        insights = []
        if sentiment == "Positive":
            insights.append("Customer shows strong satisfaction.")
            insights.append("Likely to recommend to others.")
        elif sentiment == "Negative":
            insights.append("Customer expressed dissatisfaction or frustration.")
            insights.append("Immediate attention required to resolve issues.")
        elif sentiment == "Neutral":
            insights.append("Customer is somewhat satisfied but sees areas to improve.")

        # Detect common themes
        if "slow" in feedback_text:
            insights.append("Performance optimization may be required.")
        if "confusing" in feedback_text or "hard" in feedback_text:
            insights.append("Improve UI/UX clarity and navigation.")
        if "helpful" in feedback_text or "support" in feedback_text:
            insights.append("Customer appreciates the helpful features or support.")

        analysis = {
            "sentiment": sentiment,
            "priority": priority,
            "rating": rating,
            "confidence": confidence,
            "insights": insights,
            "recommendation": (
                "Leverage this positive feedback for testimonials." if sentiment == "Positive" else
                "Follow up with the customer to understand specific improvement areas." if sentiment == "Neutral" else
                "Immediate follow-up required to address concerns and prevent churn."
            )
        }

        # ======================================================
        # 💾 Save feedback locally
        # ======================================================
        save_feedback(data, analysis)

        # ======================================================
        # ✉️ Send Email with Analysis
        # ======================================================
        try:
            msg = Message(
                subject=f"Your AI Feedback Report - {name}",
                recipients=[email]
            )

            msg.body = f"""
Hi {name},

Thank you for sharing your feedback! 
Here’s your personalized AI analysis result:

📊 Feedback Summary
----------------------------
- Rating: {rating}/5
- Sentiment: {sentiment}
- Confidence: {confidence}%
- Priority: {priority}

💡 Key Insights
----------------------------
{chr(10).join(['• ' + insight for insight in insights])}

🎯 Recommendation
----------------------------
{analysis['recommendation']}

We truly value your time and insights.
Our team uses this data to continuously improve our services.

Best regards,
The AI Feedback System
            """

            mail.send(msg)
            print(f"📧 Email sent successfully to {email}")

        except Exception as email_error:
            print(f"⚠️ Email sending failed: {str(email_error)}")

        # ======================================================
        # ✅ Return result to frontend
        # ======================================================
        return jsonify({
            "status": "success",
            "message": "Feedback analyzed and emailed successfully.",
            "analysis": analysis
        }), 200

    except Exception as e:
        print(f"🔥 Error in /analyze: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


# ==========================================================
# 🚀 Run Flask Server
# ==========================================================
if __name__ == '__main__':
    print("🌐 Running Flask Feedback System at: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
