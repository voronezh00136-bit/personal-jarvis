"""
avatar.py — Говорящий аватар JARVIS (Phase 3)
Два режима:
  - "local"  : HTML/WebSocket аватар (анимированный круг, работает без API)
  - "did"    : D-ID фотореалистичный аватар (нужен DID_API_KEY)

Использование:
    from avatar import Avatar
    avatar = Avatar(mode="local")
    avatar.show()
    avatar.speak("JARVIS активирован")
    avatar.think()   # анимация "думаю"
    avatar.listen()  # анимация "слушаю"
    avatar.cleanup()
"""

import os
import threading
import json
import time
import webbrowser
import tempfile
from typing import Optional

try:
    import websockets
    import asyncio
    WS_OK = True
except ImportError:
    WS_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False


# ── HTML аватар (локальный) ───────────────────────────────────────────────────

AVATAR_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>JARVIS</title>
<style>
  body { background: #0a0a1a; display: flex; flex-direction: column;
         align-items: center; justify-content: center; height: 100vh; margin: 0; }
  .orb { width: 200px; height: 200px; border-radius: 50%;
         background: radial-gradient(circle at 35% 35%, #4af, #007, #002);
         box-shadow: 0 0 40px #0af, 0 0 80px #007;
         transition: all 0.3s ease; }
  .orb.idle    { animation: pulse 3s ease-in-out infinite; }
  .orb.listen  { box-shadow: 0 0 60px #0f8, 0 0 120px #060; animation: bounce 0.3s infinite; }
  .orb.think   { animation: spin 1s linear infinite; opacity: 0.7; }
  .orb.speak   { animation: speak 0.15s ease-in-out infinite; }
  @keyframes pulse  { 0%,100%{transform:scale(1)} 50%{transform:scale(1.05)} }
  @keyframes bounce { 0%,100%{transform:scale(1)} 50%{transform:scale(1.1)} }
  @keyframes spin   { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
  @keyframes speak  { 0%,100%{transform:scale(1)} 50%{transform:scale(1.08)} }
  #label { color: #4af; font-family: 'Courier New', monospace; font-size: 14px;
           margin-top: 20px; letter-spacing: 3px; text-transform: uppercase; }
  #text  { color: #8cf; font-family: 'Courier New', monospace; font-size: 12px;
           margin-top: 10px; max-width: 400px; text-align: center; opacity: 0.8;
           min-height: 40px; }
</style>
</head>
<body>
<div class="orb idle" id="orb"></div>
<div id="label">J.A.R.V.I.S</div>
<div id="text">Инициализация...</div>
<script>
const orb   = document.getElementById('orb');
const label = document.getElementById('label');
const txt   = document.getElementById('text');
const ws    = new WebSocket('ws://localhost:8765');

ws.onmessage = (e) => {
  const data = JSON.parse(e.data);
  orb.className = 'orb ' + (data.state || 'idle');
  if (data.text) txt.textContent = data.text;
  const labels = {idle:'J.A.R.V.I.S', listen:'СЛУШАЮ', think:'ДУМАЮ...', speak:'ГОВОРЮ'};
  label.textContent = labels[data.state] || 'J.A.R.V.I.S';
};
ws.onopen  = () => { txt.textContent = 'Подключён'; };
ws.onclose = () => { txt.textContent = 'Отключён'; orb.className = 'orb'; };
</script>
</body>
</html>"""


class LocalAvatar:
    """WebSocket-аватар на HTML."""

    def __init__(self):
        if not WS_OK:
            raise ImportError("pip install websockets")
        self._clients = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._html_path: Optional[str] = None

    def show(self):
        # Сохраняем HTML
        tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
        tmp.write(AVATAR_HTML)
        tmp.close()
        self._html_path = tmp.name

        # Запускаем WebSocket сервер
        t = threading.Thread(target=self._run_server, daemon=True)
        t.start()
        time.sleep(0.5)

        # Открываем в браузере
        webbrowser.open(f"file://{self._html_path}")
        time.sleep(1)

    def _run_server(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve())

    async def _serve(self):
        async def handler(ws):
            self._clients.add(ws)
            await ws.wait_closed()
            self._clients.discard(ws)

        async with websockets.serve(handler, "localhost", 8765):
            await asyncio.Future()

    def _send(self, state: str, text: str = ""):
        if not self._loop or not self._clients:
            return
        msg = json.dumps({"state": state, "text": text})
        asyncio.run_coroutine_threadsafe(self._broadcast(msg), self._loop)

    async def _broadcast(self, msg: str):
        dead = set()
        for ws in self._clients:
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead

    def speak(self, text: str):  self._send("speak", text)
    def think(self):              self._send("think", "Думаю...")
    def listen(self):             self._send("listen", "Слушаю...")
    def idle(self):               self._send("idle", "Готов")

    def cleanup(self):
        if self._html_path and os.path.exists(self._html_path):
            os.unlink(self._html_path)


class DIDAvatar:
    """D-ID фотореалистичный аватар через API."""

    API_URL = "https://api.d-id.com"

    def __init__(self, api_key: str):
        if not REQUESTS_OK:
            raise ImportError("pip install requests")
        self._key = api_key
        self._headers = {"Authorization": f"Basic {api_key}", "Content-Type": "application/json"}

    def show(self):
        print("D-ID аватар готов (видео генерируется при каждой фразе)")

    def speak(self, text: str):
        try:
            resp = requests.post(f"{self.API_URL}/talks", headers=self._headers, json={
                "script": {"type": "text", "input": text, "provider": {"type": "microsoft", "voice_id": "ru-RU-SvetlanaNeural"}},
                "source_url": "https://www.d-id.com/wp-content/uploads/2023/01/person_image.jpg",
            }, timeout=10)
            if resp.ok:
                talk_id = resp.json().get("id")
                print(f"D-ID: генерирую видео {talk_id}")
        except Exception as e:
            print(f"D-ID ошибка: {e}")

    def think(self):  pass
    def listen(self): pass
    def idle(self):   pass
    def cleanup(self): pass


# ── Фасад ─────────────────────────────────────────────────────────────────────

class Avatar:
    """Единый интерфейс для local/did аватара."""

    def __init__(self, mode: str = "local"):
        self.mode = mode
        if mode == "did":
            api_key = os.environ.get("DID_API_KEY")
            if not api_key:
                raise ValueError("Нужен DID_API_KEY в переменных окружения")
            self._impl = DIDAvatar(api_key)
        else:
            self._impl = LocalAvatar()

    def show(self):    self._impl.show()
    def speak(self, text: str): self._impl.speak(text)
    def think(self):   self._impl.think()
    def listen(self):  self._impl.listen()
    def idle(self):    self._impl.idle()
    def cleanup(self): self._impl.cleanup()
