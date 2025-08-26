import socket
import threading
import sys
import time
import re
import tkinter as tk
from tkinter import scrolledtext, messagebox, ttk
import queue
import json
import os
import pyttsx3

# --- EDIT THESE VALUES ---
# Use the token you generated from the Twitch Developer console.
OAUTH_TOKEN = "oauth:YourOAuthTOKEN"
# Use the name of your bot account.
BOT_USERNAME = "USERNAMEofYourBotsTwitchAccount"

# --- Do not edit below this line unless you know what you are doing ---

class TwitchGUI:
    """A GUI for the Twitch IRC bot using tkinter."""
    def __init__(self, master):
        self.master = master
        master.title("Twitch IRC Chat")
        master.geometry("1000x800")
        
        # Queues for safe cross-thread communication
        self.message_queue = queue.Queue() # For GUI updates (chat log, status)
        self.tts_queue = queue.Queue() # For messages to be spoken
        
        # IRC and threading variables
        self.irc_thread = None
        self.tts_thread = None
        self.irc_socket = None
        self.running = False
        self.connected_channel = None
        self.viewers = set() # Set to store unique usernames
        
        # New flag to prevent mass greetings on initial join
        self.is_initial_join = True
        
        # TTS engine and settings
        self.tts_engine = None
        self.settings_file = "tts_settings.json"
        self.voice_id = None
        self.rate = 175
        self.volume = 1.0
        self.max_queue_size = 10  # Max messages to buffer for TTS
        self.message_delay = 1.0  # Delay in seconds between TTS messages
        self.max_chat_lines = 25 # New setting for chat log
        self.processing_message = False
        self.last_channel = ""
        
        self.load_settings()
        self.setup_tts_engine()
        self.setup_gui()
        
        # Load the last connected channel into the entry field
        if self.last_channel:
            self.channel_entry.insert(0, self.last_channel)
        
        # Start the GUI update loop
        self.master.after(100, self.check_message_queue)

    def load_settings(self):
        """Loads TTS and last channel settings from a file, or creates one with defaults."""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r") as f:
                    settings = json.load(f)
                    self.voice_id = settings.get("voice_id")
                    self.rate = settings.get("rate", 175)
                    self.volume = settings.get("volume", 1.0)
                    self.max_queue_size = settings.get("max_queue_size", 10)
                    self.message_delay = settings.get("message_delay", 1.0)
                    self.max_chat_lines = settings.get("max_chat_lines", 25) # Load new setting
                    self.last_channel = settings.get("last_channel", "")
            except json.JSONDecodeError:
                self.save_settings()
        else:
            self.save_settings()

    def save_settings(self):
        """Saves current TTS and last channel settings to a file."""
        settings = {
            "voice_id": self.voice_id,
            "rate": self.rate,
            "volume": self.volume,
            "max_queue_size": self.max_queue_size,
            "message_delay": self.message_delay,
            "max_chat_lines": self.max_chat_lines, # Save new setting
            "last_channel": self.last_channel
        }
        with open(self.settings_file, "w") as f:
            json.dump(settings, f, indent=4)

    def setup_tts_engine(self):
        """Initializes the pyttsx3 engine and applies saved settings."""
        try:
            self.tts_engine = pyttsx3.init()
            voices = self.tts_engine.getProperty('voices')
            if self.voice_id:
                self.tts_engine.setProperty('voice', self.voice_id)
            elif voices:
                self.voice_id = voices[0].id
                self.tts_engine.setProperty('voice', self.voice_id)
            else:
                self.voice_id = None
            self.tts_engine.setProperty('rate', self.rate)
            self.tts_engine.setProperty('volume', self.volume)
        except Exception as e:
            messagebox.showerror("TTS Error", f"Failed to initialize TTS engine: {e}")
            self.tts_engine = None
            
    def speak(self, text):
        """Uses the TTS engine to speak a given text."""
        if self.tts_engine:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

    def setup_gui(self):
        """Builds the main GUI layout."""
        # Main menu bar
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        # Preferences menu
        preferences_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Preferences", menu=preferences_menu)
        preferences_menu.add_command(label="TTS Settings", command=self.open_settings_window)
        preferences_menu.add_command(label="Rate Limitations", command=self.open_rate_limit_window)

        # Top frame for input and button
        top_frame = tk.Frame(self.master, padx=10, pady=10)
        top_frame.pack(fill=tk.X)

        tk.Label(top_frame, text="Channel:").pack(side=tk.LEFT, padx=(0, 5))
        self.channel_entry = tk.Entry(top_frame, width=30)
        self.channel_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.channel_entry.bind("<Return>", self.toggle_connection)
        
        self.connect_btn = tk.Button(top_frame, text="Connect", command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=(5, 0))

        # Main content frame for chat and viewer list
        content_frame = tk.Frame(self.master)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=0)
        
        # Use grid for responsive columns
        content_frame.grid_columnconfigure(0, weight=1) # Chat log column takes remaining space
        content_frame.grid_rowconfigure(0, weight=1)

        # Chat log area (left side)
        chat_frame = tk.Frame(content_frame)
        chat_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        tk.Label(chat_frame, text="Chat Log").pack(side=tk.TOP, pady=(0, 5))
        self.chat_log = scrolledtext.ScrolledText(chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Helvetica", 12), height=20)
        self.chat_log.pack(fill=tk.BOTH, expand=True)
        
        # Viewer list area (right side)
        viewers_frame = tk.Frame(content_frame, width=250)
        viewers_frame.grid(row=0, column=1, sticky="nsew")
        viewers_frame.pack_propagate(False)
        
        tk.Label(viewers_frame, text="Current Viewers").pack(side=tk.TOP, pady=(0, 5))
        self.viewers_log = scrolledtext.ScrolledText(viewers_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Helvetica", 10), height=20)
        self.viewers_log.pack(fill=tk.BOTH, expand=True)

        # Status label at the bottom
        self.status_label = tk.Label(self.master, text="Status: Disconnected", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(fill=tk.X, padx=10, pady=(0, 5))
        
    def open_settings_window(self):
        """Opens a new window for TTS settings."""
        settings_window = tk.Toplevel(self.master)
        settings_window.title("TTS Settings")
        settings_window.geometry("400x350")
        
        settings_frame = tk.Frame(settings_window, padx=10, pady=10)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        
        # Voice selection
        tk.Label(settings_frame, text="Voice:").pack(anchor=tk.W)
        voices = self.tts_engine.getProperty('voices')
        voice_names = [v.name for v in voices]
        
        self.voice_var = tk.StringVar(settings_window)
        current_voice_name = next((v.name for v in voices if v.id == self.voice_id), voice_names[0])
        self.voice_var.set(current_voice_name)
        
        voice_menu = ttk.Combobox(settings_frame, textvariable=self.voice_var, values=voice_names, state="readonly")
        voice_menu.pack(fill=tk.X, pady=(0, 10))
        
        # Rate setting
        tk.Label(settings_frame, text="Rate:").pack(anchor=tk.W)
        self.rate_scale = tk.Scale(settings_frame, from_=50, to=400, orient=tk.HORIZONTAL)
        self.rate_scale.set(self.rate)
        self.rate_scale.pack(fill=tk.X)
        
        # Volume setting
        tk.Label(settings_frame, text="Volume:").pack(anchor=tk.W)
        self.volume_scale = tk.Scale(settings_window, from_=0.0, to=1.0, resolution=0.1, orient=tk.HORIZONTAL)
        self.volume_scale.set(self.volume)
        self.volume_scale.pack(fill=tk.X)
        
        # Buttons for testing and saving
        btn_frame = tk.Frame(settings_window, pady=10)
        btn_frame.pack(fill=tk.X)
        
        test_btn = tk.Button(btn_frame, text="Test Voice", command=self.test_tts)
        test_btn.pack(side=tk.LEFT, padx=(0, 5), expand=True, fill=tk.X)
        
        save_btn = tk.Button(btn_frame, text="Save & Apply", command=lambda: self.apply_and_save_settings(settings_window, voices))
        save_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)
    
    def open_rate_limit_window(self):
        """Opens a new window for TTS and chat rate limiting settings."""
        rate_limit_window = tk.Toplevel(self.master)
        rate_limit_window.title("Rate Limitations")
        rate_limit_window.geometry("400x300") # Updated size
        
        rate_limit_frame = tk.Frame(rate_limit_window, padx=10, pady=10)
        rate_limit_frame.pack(fill=tk.BOTH, expand=True)
        
        # Max queue size for TTS
        tk.Label(rate_limit_frame, text="Max TTS Messages in Queue:").pack(anchor=tk.W)
        self.max_queue_scale = tk.Scale(rate_limit_frame, from_=1, to=20, orient=tk.HORIZONTAL)
        self.max_queue_scale.set(self.max_queue_size)
        self.max_queue_scale.pack(fill=tk.X)
        
        # Message delay for TTS
        tk.Label(rate_limit_frame, text="Delay between TTS messages (seconds):").pack(anchor=tk.W)
        self.delay_scale = tk.Scale(rate_limit_frame, from_=0.0, to=5.0, resolution=0.1, orient=tk.HORIZONTAL)
        self.delay_scale.set(self.message_delay)
        self.delay_scale.pack(fill=tk.X)
        
        # New: Max chat lines
        tk.Label(rate_limit_frame, text="Max Chat Messages to Show:").pack(anchor=tk.W, pady=(10, 0))
        self.max_chat_scale = tk.Scale(rate_limit_frame, from_=1, to=100, orient=tk.HORIZONTAL)
        self.max_chat_scale.set(self.max_chat_lines)
        self.max_chat_scale.pack(fill=tk.X)
        
        # Save button
        save_btn = tk.Button(rate_limit_frame, text="Save & Apply", command=lambda: self.apply_and_save_rate_limits(rate_limit_window))
        save_btn.pack(pady=(10, 0))

    def apply_and_save_rate_limits(self, window):
        """Applies new rate limit settings and saves them."""
        self.max_queue_size = self.max_queue_scale.get()
        self.message_delay = self.delay_scale.get()
        self.max_chat_lines = self.max_chat_scale.get() # Apply new setting
        self.save_settings()
        messagebox.showinfo("Settings", "Rate limitations saved and applied!")
        window.destroy()
        
    def test_tts(self):
        """Tests the TTS engine with the current settings."""
        self.tts_engine.setProperty('rate', self.rate_scale.get())
        self.tts_engine.setProperty('volume', self.volume_scale.get())
        self.tts_engine.say("This is a test of the current settings.")
        self.tts_engine.runAndWait()

    def apply_and_save_settings(self, window, voices):
        """Applies new settings to the engine and saves them."""
        # Update instance variables
        selected_voice_name = self.voice_var.get()
        selected_voice_id = next((v.id for v in voices if v.name == selected_voice_name), self.voice_id)
        
        self.voice_id = selected_voice_id
        self.rate = self.rate_scale.get()
        self.volume = self.volume_scale.get()
        
        # Apply to engine
        self.tts_engine.setProperty('voice', self.voice_id)
        self.tts_engine.setProperty('rate', self.rate)
        self.tts_engine.setProperty('volume', self.volume)
        
        # Save to file
        self.save_settings()
        messagebox.showinfo("Settings", "Settings saved and applied!")
        window.destroy()

    def toggle_connection(self, event=None):
        """Toggles the connection to the Twitch IRC server."""
        if not self.running:
            channel = self.channel_entry.get().lower()
            if not channel:
                messagebox.showerror("Error", "Please enter a channel name.")
                return
            
            self.connected_channel = channel
            self.last_channel = channel # Save the channel before connecting
            self.save_settings() # Persist the channel to the settings file
            
            self.channel_entry.config(state=tk.DISABLED)
            self.connect_btn.config(text="Disconnect")
            self.running = True
            self.viewers.clear() # Clear viewer list on new connection
            self.is_initial_join = True # Reset the flag for a new connection

            # Start the IRC thread to listen for messages
            self.irc_thread = threading.Thread(
                target=self.irc_connection_worker,
                args=(channel,),
                daemon=True
            )
            self.irc_thread.start()

            # Start a separate TTS thread to process audio messages
            self.tts_thread = threading.Thread(
                target=self.process_tts_queue,
                daemon=True
            )
            self.tts_thread.start()
        else:
            self.disconnect()

    def disconnect(self):
        """Stops the IRC thread and resets the GUI."""
        self.running = False
        if self.irc_socket:
            self.irc_socket.close()
        if self.irc_thread:
            self.irc_thread.join(timeout=1)
        if self.tts_thread:
            self.tts_thread.join(timeout=1)
            
        self.channel_entry.config(state=tk.NORMAL)
        self.connect_btn.config(text="Connect")
        self.status_label.config(text="Status: Disconnected")
        self.update_viewer_list_gui([]) # Clear viewer list on disconnect
        self.is_initial_join = True # Reset the flag for a new connection
        
    def irc_connection_worker(self, channel):
        """Worker thread for handling IRC communication."""
        self.irc_socket = self.connect_to_twitch()
        if self.irc_socket:
            if self.authenticate_and_join(self.irc_socket, channel):
                self.listen_for_messages(self.irc_socket, channel)
            else:
                self.message_queue.put(("status", "Failed to authenticate or join."))
        else:
            self.message_queue.put(("status", "Failed to connect to Twitch."))

    def connect_to_twitch(self):
        """Establishes a connection to Twitch's IRC server."""
        server = 'irc.chat.twitch.tv'
        port = 6667
        s = socket.socket()
        try:
            s.connect((server, port))
            self.message_queue.put(("status", "Connected to Twitch IRC server."))
            return s
        except socket.error:
            return None

    def authenticate_and_join(self, s, channel):
        """Authenticates the bot and joins the specified channel."""
        try:
            s.send(f"PASS {OAUTH_TOKEN}\r\n".encode('utf-8'))
            s.send(f"NICK {BOT_USERNAME}\r\n".encode('utf-8'))
            s.send("CAP REQ :twitch.tv/membership twitch.tv/tags twitch.tv/commands\r\n".encode('utf-8'))
            s.send(f"JOIN #{channel}\r\n".encode('utf-8'))
            self.message_queue.put(("status", f"Attempting to join channel #{channel}..."))
            return True
        except socket.error:
            return False

    def listen_for_messages(self, s, channel):
        """Listens for and processes messages from the IRC server."""
        buffer = ""
        while self.running:
            try:
                s.settimeout(0.5)  # Set a short timeout
                response = s.recv(2048).decode('utf-8', errors='ignore')
                
                if not response:
                    self.message_queue.put(("status", "Connection lost."))
                    break
                
                buffer += response
                lines = buffer.split('\r\n')
                buffer = lines.pop()

                for line in lines:
                    if line.startswith("PING"):
                        s.send("PONG :tmi.twitch.tv\r\n".encode('utf-8'))
                    elif "366" in line:
                        self.message_queue.put(("status", f"Successfully joined #{channel}. Waiting for initial viewer list to populate..."))
                        # Start a timer to turn off the initial join flag after 30 seconds
                        threading.Timer(30, self.end_initial_join).start()
                    elif "JOIN" in line and not line.startswith(":jtv"):
                        match = re.search(r':(\w+)!.*JOIN #(\w+)', line)
                        if match:
                            username = match.group(1).lower()
                            self.viewers.add(username)
                            self.message_queue.put(("viewer_update", sorted(list(self.viewers))))
                            # Only greet if the initial join period is over
                            if not self.is_initial_join and self.tts_queue.qsize() < self.max_queue_size:
                                self.tts_queue.put(f"Welcome to the stream, {username}!")
                            else:
                                self.message_queue.put(("status", f"Initial join or TTS queue full, dropping join message for {username}."))
                                    
                    elif "PART" in line:
                        match = re.search(r':(\w+)!.*PART #(\w+)', line)
                        if match:
                            username = match.group(1).lower()
                            self.viewers.discard(username)
                            self.message_queue.put(("viewer_update", sorted(list(self.viewers))))
                            
                    elif "PRIVMSG" in line:
                        match = re.search(r'display-name=([^;]+).*PRIVMSG #\w+ :(.+)', line)
                        if match:
                            username = match.group(1)
                            message_content = match.group(2)
                            
                            # Add user to the viewer set if they chat for the first time
                            if username.lower() not in self.viewers:
                                self.viewers.add(username.lower())
                                self.message_queue.put(("viewer_update", sorted(list(self.viewers))))
                                # Only greet first-time chatters after the initial join period is over
                                if not self.is_initial_join and self.tts_queue.qsize() < self.max_queue_size:
                                    self.tts_queue.put(f"Welcome to the stream, {username}!")
                            
                            # Add message to GUI queue
                            self.message_queue.put(("message", f"{username}: {message_content}"))
                            
                            # Add message to TTS queue if under limit
                            if self.tts_queue.qsize() < self.max_queue_size:
                                self.tts_queue.put(f"{username} says {message_content}")
                            else:
                                self.message_queue.put(("status", f"TTS queue full, dropping message from {username}."))
                                
            except socket.timeout:
                continue
            except socket.error:
                break
            except Exception:
                break
        s.close()
        
    def end_initial_join(self):
        """Sets the initial join flag to False after a delay."""
        self.is_initial_join = False
        self.message_queue.put(("status", "Initial join period over. Greeter is now active!"))

    def process_tts_queue(self):
        """A dedicated thread to process TTS messages from the queue."""
        while self.running:
            try:
                # Get a message from the queue, wait up to 1 second
                message_to_speak = self.tts_queue.get(timeout=1)
                self.speak(message_to_speak)
                self.tts_queue.task_done()
                time.sleep(self.message_delay)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS error: {e}")
                
    def check_message_queue(self):
        """Periodically checks the message queue for new messages and updates the GUI."""
        while not self.message_queue.empty():
            message_type, content = self.message_queue.get_nowait()
            if message_type == "status":
                self.status_label.config(text=f"Status: {content}")
            elif message_type == "message":
                # Display the message in the chat log
                self.chat_log.config(state=tk.NORMAL)
                self.chat_log.insert(tk.END, content + "\n")
                
                # New: Trim the chat log to the maximum number of lines
                if int(self.chat_log.index('end-1c').split('.')[0]) > self.max_chat_lines:
                    self.chat_log.delete(1.0, f"{self.chat_log.index('end-1c').split('.')[0] - self.max_chat_lines + 1}.0")
                
                self.chat_log.see(tk.END)
                self.chat_log.config(state=tk.DISABLED)
                self.message_queue.task_done()
            elif message_type == "viewer_update":
                self.update_viewer_list_gui(content)
                self.message_queue.task_done()
        
        self.master.after(100, self.check_message_queue)

    def update_viewer_list_gui(self, viewers):
        """Updates the viewer list display in the GUI."""
        self.viewers_log.config(state=tk.NORMAL)
        self.viewers_log.delete(1.0, tk.END)
        for viewer in viewers:
            self.viewers_log.insert(tk.END, viewer + "\n")
        self.viewers_log.config(state=tk.DISABLED)


def main():
    """Main function to run the application."""
    root = tk.Tk()
    app = TwitchGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()

