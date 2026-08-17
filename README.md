# 🐺 WOLF AI Assistant

**WOLF** is a powerful Windows desktop AI assistant inspired by Iron Man’s JARVIS.  
It listens, thinks, speaks, and executes real system tasks — in a sarcastic military-butler tone.

---

## ⚙️ Key Features

- 🎙️ **Real-Time Voice** — Powered by Google Realtime Voice via LiveKit Agents.
- 🌐 **Web Search** — DuckDuckGo and Wikipedia fallback for factual answers.
- 🗂️ **Open File Explorer** — Always spawns a new window.
- 🔗 **Open Websites** — Opens any URL in a fresh tab.
- 🎵 **Play Music** — Local files or YouTube search.
- ☁️ **Get Weather** — Live search for city temperatures.
- 🗣️ **Personality** — Smart, witty, and calls you *Sir* — just like JARVIS.

---

## 🚀 How to Run

1️⃣ **Clone the Repo**
```bash
git clone https://github.com/YOUR_USERNAME/wolf-ai-assistant.git
cd wolf-ai-assistant
2️⃣ Install Requirements

bash
Copy
Edit
pip install -r requirements.txt
3️⃣ Add .env
Create a .env file in your project folder:

env
Copy
Edit
# .env example
LIVEKIT_API_KEY=YOUR_API_KEY
LIVEKIT_API_SECRET=YOUR_API_SECRET
4️⃣ Run WOLF

bash
Copy
Edit
python agent.py
📁 Tech Stack
Python

LiveKit Agents

Google Realtime Voice

DuckDuckGo + Wikipedia

Webbrowser & Subprocess (Windows)

🧩 Current Tools
✅ get_weather — Get live temperature for any city.

✅ open_default_browser — Opens Google in a new tab every time.

✅ open_website — Open any custom URL.

✅ open_file_explorer — Open File Explorer reliably.

✅ play_music — Play local audio files.

✅ play_youtube_music — Search and open YouTube music.

✅ search_web — DuckDuckGo with Wikipedia fallback for facts.

📌 Status
⚡ Prototype — personal side project inspired by JARVIS.
✅ Windows-first — Mac/Linux may need tweaks.
🔧 Extensible — Add your own tools easily.

📄 License
MIT License — free to use, modify, and extend.
Credit is appreciated if you share your version.

🫡 Built by
[Mohd Adeeb] — because everyone deserves a personal JARVIS.

