# 🤖 JARVIS — Personal AI Assistant

> *"Sometimes you gotta run before you can walk."* — Tony Stark

A fully open-source, voice-controlled AI assistant for PC and Mac. Built in three progressive phases — from a 50-line voice bot to a full multi-agent system with memory, browser control, task scheduling, and a talking avatar.

---

## ✨ Demo

```
[09:01] You:    найди последние новости по AI и напомни в 18:00
[09:01] JARVIS: [search] OpenAI выпустила GPT-5, DeepMind анонсировала... Напоминание поставлено на 18:00.
[18:00] 🔔     Напоминание: последние новости по AI
```

---

## 🗺 Architecture

```
┌─────────────────────────────────────────────┐
│              Voice Interface                │
│     Whisper STT · Avatar · pyttsx3 TTS     │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│         LangGraph Orchestrator              │
│   routes: chat · search · scheduler ·      │
│           code · smarthome                 │
└──┬──────────┬──────────┬──────────┬────────┘
   │          │          │          │
┌──▼──┐  ┌───▼───┐  ┌───▼──┐  ┌───▼──────┐
│Chat │  │Search │  │Sched.│  │PC/Browser│
│LLM  │  │Tavily │  │APSch.│  │Playwright│
└──┬──┘  └───┬───┘  └───┬──┘  └───┬──────┘
   └──────────┴──────────┴─────────┘
                     │
┌────────────────────▼────────────────────────┐
│              Memory Layer                   │
│     ChromaDB (vectors) · SQLite (tasks)    │
└─────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- `ffmpeg` installed ([download](https://ffmpeg.org/download.html))
- Anthropic API key ([get one](https://console.anthropic.com))

### Phase 1 — Voice Bot (3 days)

```bash
cd phase1
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...   # Windows: set ANTHROPIC_API_KEY=...
python jarvis.py
```

Hold `SPACE` to speak. Release to get a response. Press `ESC` to quit.

### Phase 2 — Memory + PC Control + Browser (2–4 weeks)

```bash
cd phase2
pip install -r requirements.txt
playwright install chromium

python jarvis_v2.py
```

### Phase 3 — Multi-Agent + Scheduler + Avatar (2–3 months)

```bash
cd phase3
pip install -r requirements.txt
playwright install chromium

export TAVILY_API_KEY=tvly-...   # free tier at tavily.com

python jarvis_v3.py              # with local avatar
python jarvis_v3.py --no-avatar  # headless
python jarvis_v3.py --avatar did # D-ID photorealistic avatar
```

---

## 📁 Project Structure

```
jarvis/
├── phase1/                  # Voice bot — minimal working JARVIS
│   ├── jarvis.py            # Main loop: STT → Claude → TTS
│   └── requirements.txt
│
├── phase2/                  # Extended capabilities
│   ├── jarvis_v2.py         # Main loop with all Phase 2 modules
│   ├── memory.py            # Long-term memory (ChromaDB + vectors)
│   ├── pc_control.py        # Mouse, keyboard, screenshot analysis
│   ├── browser.py           # Browser automation (Playwright)
│   └── requirements.txt
│
└── phase3/                  # Full JARVIS
    ├── jarvis_v3.py         # Entry point — wires everything together
    ├── orchestrator.py      # LangGraph multi-agent router
    ├── scheduler.py         # APScheduler — reminders & cron tasks
    ├── avatar.py            # Talking avatar (local HTML or D-ID API)
    └── requirements.txt
```

---

## 🧠 Capabilities by Phase

| Feature | Phase 1 | Phase 2 | Phase 3 |
|---|:---:|:---:|:---:|
| Voice input (Whisper) | ✅ | ✅ | ✅ |
| Claude AI brain | ✅ | ✅ | ✅ |
| Text-to-speech | ✅ | ✅ | ✅ |
| Long-term memory | — | ✅ | ✅ |
| PC control (mouse/kb) | — | ✅ | ✅ |
| Browser automation | — | ✅ | ✅ |
| Screenshot analysis | — | ✅ | ✅ |
| Multi-agent routing | — | — | ✅ |
| Web search (real-time) | — | — | ✅ |
| Task scheduler | — | — | ✅ |
| Talking avatar | — | — | ✅ |
| Smart home control | — | — | ✅ |
| Code execution | — | — | ✅ |

---

## 🔧 Configuration

### Environment Variables

| Variable | Required | Description |
|---|:---:|---|
| `ANTHROPIC_API_KEY` | ✅ | Claude API key |
| `TAVILY_API_KEY` | Phase 3 | Web search (free tier available) |
| `DID_API_KEY` | Optional | Photorealistic avatar via D-ID |
| `HA_URL` | Optional | Home Assistant URL |
| `HA_TOKEN` | Optional | Home Assistant long-lived token |

### Whisper Models

Trade speed for accuracy. Edit `WHISPER_MODEL` in any `jarvis*.py`:

| Model | VRAM | Quality | Speed |
|---|---|---|---|
| `tiny` | ~1 GB | Good | Very fast |
| `base` | ~1 GB | Better | Fast |
| `small` | ~2 GB | Great | Medium |
| `medium` | ~5 GB | Excellent | Slow |
| `large` | ~10 GB | Best | Slow |

**Recommended for RTX 4070 Super:** `small` or `medium`

---

## 🎙 Voice Commands (Phase 3)

| Say | What happens |
|---|---|
| *"найди последние новости по AI"* | Web search via Tavily → summary |
| *"напомни в 18:30 позвонить маме"* | Schedules reminder with APScheduler |
| *"посчитай 15% от 3500"* | Generates & runs Python code |
| *"открой браузер"* | Launches browser via PC control |
| *"сделай скриншот и скажи что на экране"* | Screenshot → Claude Vision → TTS |
| *"включи свет на кухне"* | Home Assistant API call |
| *"запомни, что я работаю над FlowMoney"* | Saves to ChromaDB vector store |

---

## 🧩 Tech Stack

- **STT:** [OpenAI Whisper](https://github.com/openai/whisper) — local, free, multilingual
- **AI Brain:** [Claude Sonnet](https://anthropic.com) via Anthropic API
- **TTS:** [pyttsx3](https://github.com/nateshmbhat/pyttsx3) (free) or [ElevenLabs](https://elevenlabs.io) (premium)
- **Agents:** [LangGraph](https://github.com/langchain-ai/langgraph) — stateful multi-agent orchestration
- **Memory:** [ChromaDB](https://www.trychroma.com/) — local vector database
- **Browser:** [Playwright](https://playwright.dev/) — full browser automation
- **Scheduler:** [APScheduler](https://apscheduler.readthedocs.io/) — persistent task scheduling
- **PC Control:** [PyAutoGUI](https://pyautogui.readthedocs.io/) + [Pillow](https://pillow.readthedocs.io/)
- **Avatar:** Local HTML/WebSocket or [D-ID API](https://www.d-id.com/)
- **Web Search:** [Tavily](https://tavily.com/) — AI-optimized search API

---

## 🛠 Troubleshooting

**PyAudio on Windows:**
```bash
pip install pipwin
pipwin install pyaudio
```

**ffmpeg not found:**
- Windows: download from [ffmpeg.org](https://ffmpeg.org/download.html), add to PATH
- Mac: `brew install ffmpeg`
- Ubuntu: `sudo apt install ffmpeg`

**Russian TTS sounds robotic:**
- Windows: Settings → Time & Language → Speech → add Russian voice pack
- Mac: System Settings → Accessibility → Spoken Content → add Siri Russian

**PyAudio: PortAudio not found (Mac):**
```bash
brew install portaudio
pip install pyaudio
```

---

## 🗺 Roadmap

- [ ] Wake word detection (`Hey JARVIS`) without holding SPACE
- [ ] ElevenLabs voice integration
- [ ] Calendar integration (Google Calendar API)
- [ ] Email summarization and drafting
- [ ] Local LLM fallback (Ollama + Llama 3)
- [ ] Electron desktop UI
- [ ] iOS/Android companion app

---

## 📄 License

MIT — do whatever you want. Build something cool.

---

## 🙏 Credits

Built with Claude (Anthropic), OpenAI Whisper, LangGraph, and a lot of coffee.

Star ⭐ the repo if JARVIS helps you out!
