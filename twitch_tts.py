```python
"""
Twitch TTS Chat
---------------
Features:
- Connects to Twitch IRC with built-in OAuth login flow.
- Reads chat messages aloud with pyttsx3.
- Allows users to switch their TTS voice with chat commands.
- Provides a GUI Voice Manager to assign voices per user.
- Includes dependency auto-check/install at startup.

ToDo:
- [ ] Add user input field in Voice Manager for custom sample text previews.
- [ ] Expand available voices with cloud TTS APIs (optional future enhancement).
"""

import sys
import subprocess
import socket
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pyttsx3
import json
import os
import webbrowser
from requests_oauthlib import OAuth2Session

# ---------------- Dependency Check ----------------
REQUIRED_PACKAGES = [
    "pyttsx3",
    "requests",
    "requests_oauthlib",
    "tk"
]

def check_dependencies():
    missing = []
    for package in REQUIRED_PACKAGES:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing.append(package)

    if missing:
        print("\n⚠️ Missing dependencies detected:", ", ".join(missing))
        print("Attempting to install them with pip...\n")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("\n✅ Installation complete. Please restart the program.\n")
            sys.exit(0)
        except Exception as e:
            print("\n❌ Automatic installation failed.")
            print("Please run this command manually:")
            print(f"    pip install {' '.join(missing)}")
            sys.exit(1)

check_dependencies()

# -------- CONFIG --------
HOST = "irc.chat.twitch.tv"
PORT = 6667
NICK = ""      # Twitch username (fetched after OAuth)
TOKEN = ""     # OAuth token
CONFIG_FILE = "config.json"
CLIENT_ID = "your_twitch_client_id"
REDIRECT_URI = "http://localhost:17563"
SCOPES = ["chat:read", "chat:edit"]
# -------------------------

message_queue = queue.Queue()
played_messages = []
current_index = -1

engine = pyttsx3.init()
engine.setProperty('rate', 180)

blacklist = set()
autoplay = True
CHANNEL = "#defaultchannel"
user_voices = {}  # username -> voice.id
default_voice = None

# --- Load/Save Config ---
def load_config():
    global CHANNEL, blacklist, default_voice, user_voices, NICK, TOKEN
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            CHANNEL = data.get("channel", CHANNEL)
            blacklist = set(data.get("blacklist", []))
            default_voice = data.get("default_voice", default_voice)
            user_voices.update(data.get("user_voices", {}))
            NICK = data.get("nick", NICK)
            TOKEN = data.get("token", TOKEN)

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump({
            "channel": CHANNEL,
            "blacklist": list(blacklist),
            "default_voice": default_voice,
            "user_voices": user_voices,
            "nick": NICK,
            "token": TOKEN
        }, f)

# --- Twitch OAuth Flow ---
def twitch_login():
    global TOKEN, NICK
    oauth = OAuth2Session(CLIENT_ID, redirect_uri=REDIRECT_URI, scope=SCOPES)
    auth_url, state = oauth.authorization_url("https://id.twitch.tv/oauth2/authorize")

    messagebox.showinfo("Twitch Login", "You will be redirected to Twitch to authorize the app.")
    webbrowser.open(auth_url)

    print(f"⚠️ After authorizing, paste the full redirect URL here (starting with {REDIRECT_URI})")
    redirect_response = input("Paste redirect URL: ").strip()

    token = oauth.fetch_token(
        "https://id.twitch.tv/oauth2/token",
        authorization_response=redirect_response,
        client_secret="your_twitch_client_secret"
    )

    TOKEN = "oauth:" + token["access_token"]
    # NOTE: In a real implementation, call Twitch API to fetch username
    NICK = "your_twitch_username"  # Placeholder
    save_config()

# --- Twitch IRC Connection ---
def connect_to_twitch():
    global sock
    sock = socket.socket()
    sock.connect((HOST, PORT))
    sock.send(f"PASS {TOKEN}\r\n".encode("utf-8"))
    sock.send(f"NICK {NICK}\r\n".encode("utf-8"))
    sock.send(f"JOIN {CHANNEL}\r\n".encode("utf-8"))

    while True:
        resp = sock.recv(2048).decode("utf-8")
        if resp.startswith("PING"):
            sock.send("PONG :tmi.twitch.tv\r\n".encode("utf-8"))
        elif len(resp) > 0:
            parts = resp.split(" :", 2)
            if len(parts) >= 3:
                username = parts[1].split("!")[0]
                message = parts[2].strip()
                if username not in blacklist:
                    formatted_display = f"{username}: {message}"
                    formatted_tts = f"{username} said: {message}"
                    message_queue.put((formatted_display, tts_with_voice(username, formatted_tts)))

# --- TTS Playback ---
def tts_with_voice(username, text):
    voice_id = user_voices.get(username, default_voice)
    if voice_id:
        engine.setProperty("voice", voice_id)
    return text

def play_message(index):
    global current_index
    if 0 <= index < len(played_messages):
        current_index = index
        text = played_messages[index][1]
        engine.say(text)
        engine.runAndWait()

def play_next():
    global current_index
    if current_index + 1 < len(played_messages):
        play_message(current_index + 1)

def play_previous():
    global current_index
    if current_index - 1 >= 0:
        play_message(current_index - 1)

# --- GUI Update Loop ---
def poll_messages():
    global autoplay
    while not message_queue.empty():
        display_msg, tts_msg = message_queue.get()
        played_messages.append((display_msg, tts_msg))
        listbox.insert(tk.END, display_msg)
        if autoplay:
            play_message(len(played_messages) - 1)
    root.after(500, poll_messages)

# --- Voice Manager ---
def open_voice_manager():
    vm = tk.Toplevel(root)
    vm.title("Voice Manager")

    voices = engine.getProperty("voices")

    def preview_voice(voice_id):
        engine.setProperty("voice", voice_id)
        sample_text = "This is a sample chat message."  # ToDo: let user provide custom sample
        engine.say(sample_text)
        engine.runAndWait()

    # Default voice selector
    ttk.Label(vm, text="Default Voice:").pack(pady=5)
    default_combo = ttk.Combobox(vm, values=[v.name for v in voices], state="readonly")
    if default_voice:
        for v in voices:
            if v.id == default_voice:
                default_combo.set(v.name)
    default_combo.pack(pady=5)

    def set_default():
        global default_voice
        for v in voices:
            if v.name == default_combo.get():
                default_voice = v.id
                save_config()
                status_label.config(text=f"Default voice set to {v.name}")

    ttk.Button(vm, text="Set Default", command=set_default).pack(pady=5)

    # User voice assignments
    ttk.Label(vm, text="User Voice Assignments:").pack(pady=5)
    for user in set([u for u, _ in played_messages]):
        frame = ttk.Frame(vm)
        frame.pack(fill="x", pady=2)

        ttk.Label(frame, text=user, width=15).pack(side="left")

        combo = ttk.Combobox(frame, values=[v.name for v in voices], state="readonly")
        assigned_id = user_voices.get(user)
        if assigned_id:
            for v in voices:
                if v.id == assigned_id:
                    combo.set(v.name)
        combo.pack(side="left", padx=5)

        def assign(u=user, c=combo):
            for v in voices:
                if v.name == c.get():
                    user_voices[u] = v.id
                    save_config()
                    status_label.config(text=f"{u}'s voice set to {v.name}")

        ttk.Button(frame, text="Assign", command=assign).pack(side="left", padx=5)
        ttk.Button(frame, text="Preview", command=lambda c=combo: preview_voice(next(v.id for v in voices if v.name == c.get()))).pack(side="left", padx=5)

# --- Blacklist & Other UI functions omitted for brevity (same as before) ---
# (reuse your existing blacklist, import/export, autoplay toggle, channel switch, help/about)

# --- GUI ---
root = tk.Tk()
root.title("Twitch TTS Chat")

# Menu
menubar = tk.Menu(root)
help_menu = tk.Menu(menubar, tearoff=0)
help_menu.add_command(label="Help / About", command=lambda: messagebox.showinfo("Help", "Help text here"))
menubar.add_cascade(label="Help", menu=help_menu)
root.config(menu=menubar)

frame = ttk.Frame(root, padding=10)
frame.pack(fill="both", expand=True)

# Channel input
channel_frame = ttk.Frame(frame)
channel_frame.pack(pady=5)
ttk.Label(channel_frame, text="Channel:").pack(side=tk.LEFT)
channel_entry = ttk.Entry(channel_frame, width=30)
channel_entry.pack(side=tk.LEFT, padx=5)
channel_btn = ttk.Button(channel_frame, text="Update Channel", command=lambda: None)
channel_btn.pack(side=tk.LEFT, padx=5)

listbox = tk.Listbox(frame, height=15, width=80)
listbox.pack(pady=10)

controls = ttk.Frame(frame)
controls.pack()

btn_play = ttk.Button(controls, text="Play Selected", command=lambda: play_message(listbox.curselection()[0]))
btn_play.grid(row=0, column=0, padx=5)
btn_prev = ttk.Button(controls, text="Previous", command=play_previous)
btn_prev.grid(row=0, column=1, padx=5)
btn_next = ttk.Button(controls, text="Next", command=play_next)
btn_next.grid(row=0, column=2, padx=5)

ttk.Button(controls, text="Voice Manager", command=open_voice_manager).grid(row=0, column=3, padx=5)

status_label = ttk.Label(frame, text="")
status_label.pack(pady=5)

# Load config before connecting
load_config()

# Start Twitch thread
if not TOKEN or not NICK:
    twitch_login()

twitch_thread = threading.Thread(target=connect_to_twitch, daemon=True)
twitch_thread.start()

# Start polling
root.after(500, poll_messages)
root.mainloop()

