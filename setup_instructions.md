---

# 🟣 Twitch TTS Chat App – Setup Instructions

This guide will help you set up and run the Twitch TTS Chat App with integrated Twitch login, customizable voices, and blacklist/voice management.

---

## 1. 📦 Install Python

Make sure you have **Python 3.9+** installed.

* [Download Python](https://www.python.org/downloads/)
* On Linux/Mac, check with:

  ```bash
  python3 --version
  ```

---

## 2. 📥 Clone or Download Project

Download this project to your computer, then open a terminal inside the project folder.

---

## 3. 📚 Install Dependencies

Run:

```bash
pip install -r requirements.txt
```

If you are on **Linux**, you may also need:

```bash
sudo apt-get install python3-tk
```

---

## 4. 🔑 Twitch Developer Setup (OAuth Login)

Since Twitch discontinued the old `twitchapps.com/tmi` method, you’ll generate your own OAuth tokens via the **Twitch Developer Console**.

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console/apps).
2. Click **“Register Your Application”**.

   * **Name:** `TTS Chat App`
   * **OAuth Redirect URL:** `http://localhost:17563`
   * **Category:** `Chat Bot`
3. Copy down your **Client ID** and **Client Secret**.

⚠️ Keep your Client Secret safe and never share it.

---

## 5. ⚙️ First-Time App Setup

When you first run the app (`python twitch_tts.py`):

* You’ll be asked to enter your **Client ID** and **Client Secret**.
* The app will open a **Twitch login page** in your browser.
* Once you approve, the app automatically retrieves your **OAuth Token**.
* This token is saved securely in `config.json` for future sessions.

---

## 6. 🗣️ Voices & Voice Manager

* In the GUI, you can choose a **Default Voice**.
* You can also allow Twitch chatters to switch their voice by typing a special command (example: `!voice brian`).
* The **Voice Manager UI** shows all active chatters with buttons to change their voice on the fly.
* A **Preview Voice** button lets you test each voice with a sample phrase.

  <!-- TODO: Allow entering a custom preview message for better testing -->  

---

## 7. ⛔ Blacklist & Autoplay

* You can **Blacklist Users** to mute their messages.
* Import/Export blacklist as `.txt` files.
* Toggle **Autoplay** to have all chat messages read aloud automatically.

---

## 8. ▶️ Running the App

Run the app with:

```bash
python twitch_tts.py
```

---

✅ Done! You’re now ready to use Twitch TTS Chat with real Twitch login and multiple voices.

---

