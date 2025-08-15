from flask import Flask, request, redirect, render_template
from flask_socketio import SocketIO, emit, join_room
import random, string, html
from urllib.parse import quote
from collections import defaultdict
from google import genai
import os
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise ValueError("API_KEY environment variable is not set.")
client = genai.Client(api_key=API_KEY)
votes = defaultdict(dict)
app = Flask(__name__)
socketio = SocketIO(app)

def generate_judge_response(session_name):
    side1_case = votes[session_name]["side1"]
    side2_case = votes[session_name]["side2"]
    prompt = f"You are an AI Judge in a courtroom. You're inside an app where both sides must present fair and factual information. Your task is to analyze and reply with the most logical and factual, non-biased response. You will also provide a reason for your decision. The prosecution's case: : {side1_case}, and the defense's case: {side2_case}. Do not use any special formatting characters"
    prompt = clean(prompt.replace("*", ""))
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=prompt
    )
    del votes[session_name]
    return response.text

def clean(text):
    return html.escape(text, quote=True)

def random_string(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/create_session", methods=["POST"])
def create_session():
    session_name = request.form.get("session_name") or random_string()
    username = request.form.get("username") or "Guest"
    username = username.strip() or "Guest"
    username = quote(username) or "Guest"
    sidechoice = request.form.get("side") or "side2"
    if sidechoice == "side1":
        username = f"{username} [PROSECUTION]"
    elif sidechoice == "side2":
        username = f"{username} [DEFENSE]"
    return redirect(f"/{session_name}?username={username}&side={sidechoice}")

@app.route("/<session_name>")
def session_page(session_name):
    username = request.args.get("username", "Guest")
    return render_template("session.html", session_name=session_name, username=username)

@socketio.on("join")
def handle_join(data):
    session_name = data["session"] or random_string()
    username = clean(data["username"]) or "Guest"
    join_room(session_name)
    emit("message", {"side": "system", "message": f"{username} joined session {session_name}"}, room=session_name)

@socketio.on("message")
def handle_message(data):
    session_name = data["session"]
    username = clean(data["username"]) or "Guest"
    message_text = clean(data["message"])

    # Extract side from username
    side = "side1" if "[PROSECUTION]" in username else "side2"

    if message_text.startswith("/vote"):
        final_case = message_text[6:].strip()  # text after "/vote "
        votes[session_name][side] = final_case

        emit("message", {
            "side": "system",
            "message": f"{username} submitted their final case. {message_text}"
        }, room=session_name)

        # If both sides have voted, trigger AI analysis
        if "side1" in votes[session_name] and "side2" in votes[session_name]:
            emit("message", {
                "side": "system",
                "message": "Both sides have submitted their cases. The AI Judge is analyzing the cases... Please shut the fuck up and wait. DO NOT /VOTE."
            }, room=session_name)
            emit("message", {
                 "side": "system",
                 "message": generate_judge_response(session_name=session_name), }, 
            room=session_name)

    else:
        emit("message", {
            "side": side,
            "message": f"{username}: {message_text}"
        }, room=session_name)

if __name__ == "__main__":
    socketio.run(app, debug=True)
