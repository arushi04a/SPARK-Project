from flask import Flask, render_template, request, redirect, url_for, session, flash
import smtplib
from email.mime.text import MIMEText
import pandas as pd
import os
import hashlib
import random

app = Flask(__name__)
app.secret_key = open("D:\\village\\codeProgram\\Carrier_Catalyst\\secret.key").read().strip()

# =======================
# CONFIGURATION
# =======================
SENDER_EMAIL = "careersparky@gmail.com"
APP_PASSWORD = "zmrz wonu nzga edqg"  # 🔹 Replace with your Gmail App Password
USERS_CSV = "D:\\village\\codeProgram\\Carrier_Catalyst\\user.csv"

# =======================
# UTILITIES
# =======================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(input_password, stored_hash):
    return hash_password(input_password) == stored_hash

def send_otp(receiver_email):
    otp = str(random.randint(100000, 999999))
    msg = MIMEText(f"Your CareerMentor OTP is: {otp}")
    msg["Subject"] = "CareerMentor Email Verification"
    msg["From"] = SENDER_EMAIL
    msg["To"] = receiver_email

    try:
        print(f"📨 Connecting to Gmail SMTP...")
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
        print(f"✅ OTP sent to {receiver_email}: {otp}")
        return otp
    except Exception as e:
        print("❌ Email sending failed:", e)
        raise e

# =======================
# USER STORAGE
# =======================
if os.path.exists(USERS_CSV):
    users_df = pd.read_csv(USERS_CSV)
else:
    users_df = pd.DataFrame(columns=["email", "password"])
    users_df.to_csv(USERS_CSV, index=False)

# =======================
# ROUTES
# =======================
@app.route("/")
def home():
    if "email" in session:
        return f"""
        <h2>✅ Welcome, {session['email']}</h2>
        <a href='/logout'>Logout</a>
        """
    return redirect(url_for("login"))


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    users_df = pd.read_csv(USERS_CSV)
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        match = users_df[users_df["email"] == email]
        if not match.empty and verify_password(password, match.iloc[0]["password"]):
            session["email"] = email
            flash("✅ Login successful!", "success")
            return redirect(url_for("home"))
        else:
            flash("❌ Invalid email or password", "error")

    return render_template("auth.html", step="login")


# ---------- SIGNUP STEP 1: EMAIL ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    users_df = pd.read_csv(USERS_CSV)
    if request.method == "POST":
        email = request.form["email"]
        if email in users_df["email"].values:
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


# ---------- SIGNUP STEP 2: OTP ----------
@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if "otp" not in session:
        flash("⚠️ Please start signup again.", "warning")
        return redirect(url_for("signup"))

    if request.method == "POST":
        otp_input = request.form["otp"]
        if otp_input.strip() == session.get("otp", ""):
            flash("🎉 OTP verified! Now create your password.", "success")
            return redirect(url_for("create_password"))
        else:
            flash("❌ Incorrect OTP. Try again.", "error")

    return render_template("auth.html", step="otp")


# ---------- SIGNUP STEP 3: PASSWORD ----------
@app.route("/create_password", methods=["GET", "POST"])
def create_password():
    if "pending_email" not in session:
        flash("⚠️ Session expired. Please start signup again.", "warning")
        return redirect(url_for("signup"))

    users_df = pd.read_csv(USERS_CSV)
    if request.method == "POST":
        password = request.form["password"]
        email = session["pending_email"]

        hashed = hash_password(password)
        new_user = pd.DataFrame({"email": [email], "password": [hashed]})
        users_df = pd.concat([users_df, new_user], ignore_index=True)
        users_df.to_csv(USERS_CSV, index=False)

        session.pop("otp", None)
        session.pop("pending_email", None)
        session["email"] = email

        flash("✅ Account created successfully!", "success")
        return redirect(url_for("home"))

    return render_template("auth.html", step="password")


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


# ---------- TEST EMAIL ----------
@app.route("/test_email")
def test_email():
    try:
        test_otp = send_otp("youremail@gmail.com")  # change to your email for testing
        return f"✅ Test OTP sent! ({test_otp})"
    except Exception as e:
        return f"❌ Failed: {e}"


if __name__ == "__main__":
    app.run(debug=True)
