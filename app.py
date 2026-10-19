
import os
import sqlite3
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename


# --------------------------------------------------
# Configuration
# --------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = BASE_DIR / "speakyourlog.db"
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.getenv(
    "FLASK_SECRET_KEY",
    "change-this-secret-before-deployment"
)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


# --------------------------------------------------
# Database - existing database is preserved
# --------------------------------------------------
def get_db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                user_field TEXT NOT NULL,
                language TEXT DEFAULT 'en',
                goal TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)


def signed_in():
    return bool(session.get("user_id"))


def get_current_user():
    if not signed_in():
        return None

    with get_db() as db:
        return db.execute(
            "SELECT * FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()


# --------------------------------------------------
# Gemini AI
# --------------------------------------------------
def call_gemini(prompt, user):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model_name = os.getenv("GEMINI_MODEL", "").strip()

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from .env")

    if not model_name:
        raise RuntimeError("GEMINI_MODEL is missing from .env")

    from google import genai

    client = genai.Client(api_key=api_key)

    response = client.models.generate_content(
        model=model_name,
        contents=prompt
    )

    answer = getattr(response, "text", None)

    if not answer or not answer.strip():
        raise RuntimeError("Gemini returned an empty response.")

    return answer.strip()


def ask_gemini(message, user, document_text=""):
    language = (user["language"] or "en").lower()

    if language.startswith("ta"):
        language_instruction = (
            "Reply in simple, natural, beginner-friendly Tamil."
        )
    else:
        language_instruction = (
            "Reply in clear, simple English for a student."
        )

    prompt = f"""
You are Speak Your Log, a friendly student problem-solving assistant.

Student name: {user['name']}
Student field: {user['user_field']}
Student goal: {user['goal']}

{language_instruction}

Help the student understand and solve their problem.
Ask one relevant follow-up question if essential information is missing.
Give practical, beginner-friendly steps.
Suggest one small next target.
Do not claim a daily log was saved unless the app confirms it.

Relevant document or notes:
{document_text[:12000]}

Student message:
{message}
"""

    try:
        return call_gemini(prompt, user)
    except Exception:
        app.logger.exception("Gemini request failed")
        return (
            "AI response failed. Please check the VS Code Terminal "
            "for the error details."
        )


# --------------------------------------------------
# Home
# --------------------------------------------------
@app.route("/")
def home():
    return redirect(
        url_for("dashboard" if signed_in() else "login")
    )


# --------------------------------------------------
# Register
# --------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user_field = request.form.get("user_field", "").strip()
        language = request.form.get("language", "en").strip()
        goal = request.form.get("goal", "").strip()

        if not all([name, email, password, user_field, goal]):
            flash("Please complete every field.", "error")
            return redirect(url_for("register"))

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return redirect(url_for("register"))

        try:
            with get_db() as db:
                cursor = db.execute("""
                    INSERT INTO users
                    (name, email, password_hash, user_field, language, goal)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    name,
                    email,
                    generate_password_hash(password),
                    user_field,
                    language,
                    goal
                ))

                session.clear()
                session["user_id"] = cursor.lastrowid

            flash("Account created successfully!", "success")
            return redirect(url_for("dashboard"))

        except sqlite3.IntegrityError:
            flash(
                "This email is already registered. Please log in.",
                "error"
            )

    return render_template("register.html")


# --------------------------------------------------
# Login
# --------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with get_db() as db:
            user = db.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()

        if user and check_password_hash(
            user["password_hash"], password
        ):
            session.clear()
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))

        flash("Incorrect email or password.", "error")

    return render_template("login.html")


# --------------------------------------------------
# Dashboard
# --------------------------------------------------
@app.route("/dashboard")
def dashboard():
    if not signed_in():
        return redirect(url_for("login"))

    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE id = ?",
            (session["user_id"],)
        ).fetchone()

        if not user:
            session.clear()
            return redirect(url_for("login"))

        logs = db.execute("""
            SELECT * FROM logs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 20
        """, (session["user_id"],)).fetchall()

        total_logs = db.execute(
            "SELECT COUNT(*) FROM logs WHERE user_id = ?",
            (session["user_id"],)
        ).fetchone()[0]

    return render_template(
        "dashboard.html",
        user=user,
        logs=logs,
        total_logs=total_logs
    )


# --------------------------------------------------
# AI chat - includes uploaded PDF text
# --------------------------------------------------
@app.route("/ask-ai", methods=["POST"])
def ask_ai():
    if not signed_in():
        return jsonify({"error": "Please log in again."}), 401

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip()

    if not message:
        return jsonify({
            "error": "Please enter or speak a message."
        }), 400

    user = get_current_user()

    if not user:
        session.clear()
        return jsonify({"error": "Please log in again."}), 401

    document_text = session.get("document_text", "")
    answer = ask_gemini(message, user, document_text)

    return jsonify({"reply": answer})


# --------------------------------------------------
# PDF upload
# --------------------------------------------------
@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    if not signed_in():
        return redirect(url_for("login"))

    uploaded_file = request.files.get("pdf_file")

    if not uploaded_file or not uploaded_file.filename:
        flash("Please choose your PDF file first.", "error")
        return redirect(url_for("dashboard"))

    original_name = uploaded_file.filename.strip()
    safe_name = secure_filename(original_name)
    file_bytes = uploaded_file.read()

    if not file_bytes:
        flash("The selected file is empty.", "error")
        return redirect(url_for("dashboard"))

    if b"%PDF-" not in file_bytes[:1024]:
        flash("This file is not recognized as a valid PDF.", "error")
        return redirect(url_for("dashboard"))

    saved_path = UPLOAD_DIR / (
        f"{session['user_id']}_{uuid4().hex}.pdf"
    )

    try:
        from pypdf import PdfReader

        with open(saved_path, "wb") as output_file:
            output_file.write(file_bytes)

        reader = PdfReader(str(saved_path))

        if reader.is_encrypted:
            saved_path.unlink(missing_ok=True)
            flash("Please upload an unlocked PDF.", "error")
            return redirect(url_for("dashboard"))

        text = "\n".join(
            page.extract_text() or ""
            for page in reader.pages[:30]
        ).strip()

        if not text:
            saved_path.unlink(missing_ok=True)
            flash(
                "No selectable text found. Scanned PDFs need OCR.",
                "error"
            )
            return redirect(url_for("dashboard"))

        session["document_text"] = text[:12000]
        session["document_name"] = safe_name or "uploaded.pdf"

        flash(
            "PDF uploaded successfully! You can now ask the AI questions about its contents.",
            "success"
        )

    except ImportError:
        saved_path.unlink(missing_ok=True)
        flash(
            "Install PDF support with: python -m pip install pypdf",
            "error"
        )

    except Exception:
        saved_path.unlink(missing_ok=True)
        app.logger.exception("PDF processing failed")
        flash("Could not read this PDF. Please try another.", "error")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Weekly AI Progress Report
# --------------------------------------------------
@app.route("/weekly-report", methods=["GET", "POST"])
def weekly_report():
    if not signed_in():
        return redirect(url_for("login"))

    user = get_current_user()

    if not user:
        session.clear()
        return redirect(url_for("login"))

    report = None
    log_count = 0
    error_message = None

    with get_db() as db:
        # Only this user's logs from the last 7 days are included.
        logs = db.execute("""
            SELECT content, created_at
            FROM logs
            WHERE user_id = ?
              AND datetime(created_at) >= datetime('now', '-7 days')
            ORDER BY created_at ASC
        """, (session["user_id"],)).fetchall()

    log_count = len(logs)

    if request.method == "POST":
        if not logs:
            error_message = (
                "No saved daily logs were found for the last 7 days. "
                "Save a few daily reflections and try again."
            )
        else:
            log_text = "\n\n".join(
                f"Date: {row['created_at']}\n"
                f"Student's original log: {row['content']}"
                for row in logs
            )

            language = (user["language"] or "en").lower()

            if language.startswith("ta"):
                output_language = "simple, natural Tamil"
            else:
                output_language = "simple, clear English"

            prompt = f"""
You are Speak Your Log's weekly student progress coach.

Create a weekly progress report for this student using ONLY the logs
provided below. Respond in {output_language}.

Student name: {user['name']}
Student field: {user['user_field']}
Student goal: {user['goal']}

Logs from the last seven days:
{log_text[:18000]}

Use these headings:
1. Weekly Overview
2. What Went Well
3. Challenges or Repeated Problems
4. Progress Evidence from the Logs
5. Suggestions for Improvement
6. Three Realistic Goals for Next Week

Rules:
- Base every observation on the supplied logs.
- Do not invent achievements, activity, scores, or dates.
- If there is not enough evidence to assess something, say so.
- Be supportive, specific, and practical.
- Keep the report readable and concise.
- Do not claim the student improved unless the logs provide evidence.
"""

            try:
                report = call_gemini(prompt, user)
                
            except Exception:
                app.logger.exception("Weekly report generation failed")
                error_message = (
                    "Could not generate the report. Check the VS Code "
                    "Terminal for the error, then try again."
                )

    

    return render_template(
        "weekly_report.html",
        user=user,
        report=report,
        log_count=log_count,
        error_message=error_message
    )


# --------------------------------------------------
# Save daily log - explicit confirmation required
# --------------------------------------------------
@app.route("/save-log", methods=["POST"])
def save_log():
    if not signed_in():
        return redirect(url_for("login"))

    content = request.form.get("log_text", "").strip()
    confirmed = request.form.get("confirm_save") == "yes"

    if not content:
        flash("Please write your daily log first.", "error")
    elif not confirmed:
        flash("Please confirm before saving your log.", "error")
    else:
        with get_db() as db:
            db.execute(
                "INSERT INTO logs (user_id, content) VALUES (?, ?)",
                (session["user_id"], content)
            )
        flash("Your log has been saved!", "success")

    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Logout
# --------------------------------------------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.errorhandler(413)
def file_too_large(_error):
    flash("File is too large. Maximum size is 10 MB.", "error")
    return redirect(url_for("dashboard"))


# --------------------------------------------------
# Start application
# --------------------------------------------------
init_db()

if __name__ == "__main__":
    app.run(debug=True)
