"""
jarvis.py — JARVIS v2.0 (Фаза 2)
Добавлено: долгосрочная память, управление ПК, браузер

Запуск:
    python jarvis.py

Горячие клавиши:
    ПРОБЕЛ  — говорить
    ESC     — выход
"""

import os
import sys
import tempfile
import threading
import time
import queue
import wave
import re
from datetime import datetime

# ─── Зависимости ─────────────────────────────────────────────────────────────
try:
    import anthropic
    import whisper
    import pyttsx3
    import pyaudio
    import keyboard
    import numpy as np
    from colorama import Fore, Style, init as colorama_init
except ImportError as e:
    print(f"\n❌  Не хватает: {e}")
    print("pip install anthropic openai-whisper pyttsx3 pyaudio keyboard numpy colorama")
    sys.exit(1)

# Фаза 2 модули (грузятся с предупреждением если нет)
try:
    from memory import Memory
    MEMORY_OK = True
except ImportError:
    MEMORY_OK = False
    print("⚠  memory.py не найден или нет ChromaDB — память отключена")

try:
    from pc_control import PCControl
    PC_OK = True
except ImportError:
    PC_OK = False
    print("⚠  pc_control.py не найден или нет pyautogui — управление ПК отключено")

try:
    from browser import BrowserSync
    BROWSER_OK = True
except ImportError:
    BROWSER_OK = False
    print("⚠  browser.py не найден или нет playwright — браузер отключён")

colorama_init(autoreset=True)

# ─── Конфиг ──────────────────────────────────────────────────────────────────
CLAUDE_MODEL  = "claude-sonnet-4-20250514"
WHISPER_MODEL = "small"    # base / small / medium — на RTX 4070 Super ставь small
SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK         = 1024
HOTKEY        = "space"
MAX_HISTORY   = 20

# ─── Цвета ───────────────────────────────────────────────────────────────────
CJ    = Fore.CYAN       # JARVIS
CU    = Fore.GREEN      # User
CS    = Fore.YELLOW     # System
CE    = Fore.RED        # Error
CB    = Fore.MAGENTA    # Browser
CM    = Fore.BLUE       # Memory
DIM   = Style.DIM
RST   = Style.RESET_ALL

# ─── Системный промпт (динамически расширяется памятью) ──────────────────────
BASE_SYSTEM = """Ты JARVIS — личный ИИ-ассистент.

РЕЖИМЫ РАБОТЫ:
Если пользователь просит что-то связанное с браузером (открыть сайт, найти информацию, погода, YouTube) — начни ответ с тега [BROWSER: <команда>].
Если пользователь просит управлять компьютером (открыть программу, громкость, скриншот, скопировать) — начни с тега [PC: <команда>].
Если пользователь говорит запомни/помни — начни с тега [MEMORY: <факт>].
Иначе — просто отвечай.

СТИЛЬ:
- Отвечай кратко (2-4 предложения максимум) — ты голосовой ассистент
- Говори на языке пользователя (русский или английский)
- Не используй списки и маркеры — только живой текст"""


class AudioRecorder:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self._frames = []
        self._recording = False
        self._stream = None

    def start(self):
        self._frames = []
        self._recording = True
        self._stream = self.pa.open(
            format=pyaudio.paInt16, channels=CHANNELS,
            rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK,
        )
        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        while self._recording:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self._frames.append(data)
            except Exception:
                break

    def stop(self) -> str | None:
        self._recording = False
        time.sleep(0.1)
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if len(self._frames) < 5:
            return None
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        with wave.open(tmp.name, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.pa.get_sample_size(pyaudio.paInt16))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b"".join(self._frames))
        return tmp.name

    def cleanup(self):
        self.pa.terminate()


class TTSEngine:
    def __init__(self):
        self.engine = pyttsx3.init()
        voices = self.engine.getProperty("voices")
        ru = next((v for v in voices if "ru" in v.id.lower() or "russian" in v.name.lower()), None)
        if ru:
            self.engine.setProperty("voice", ru.id)
        elif voices:
            self.engine.setProperty("voice", voices[0].id)
        self.engine.setProperty("rate", 175)
        self.engine.setProperty("volume", 0.95)
        self._q: queue.Queue = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str):
        # Убираем теги перед озвучкой
        clean = re.sub(r"\[(?:BROWSER|PC|MEMORY|SEARCH):[^\]]*\]", "", text).strip()
        if clean:
            self._q.put(clean)

    def _worker(self):
        while True:
            t = self._q.get()
            if t is None:
                break
            try:
                self.engine.say(t)
                self.engine.runAndWait()
            except Exception:
                pass

    def stop(self):
        self._q.put(None)


class JarvisV2:
    """JARVIS v2 — с памятью, управлением ПК и браузером."""

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(f"{CE}❌  Нужен ANTHROPIC_API_KEY{RST}")
            sys.exit(1)

        self.client   = anthropic.Anthropic(api_key=api_key)
        self.recorder = AudioRecorder()
        self.tts      = TTSEngine()
        self.history: list[dict] = []

        # Загружаем Whisper
        print(f"{CS}⚙  Загружаю Whisper ({WHISPER_MODEL})...{RST}", end="", flush=True)
        self.whisper = whisper.load_model(WHISPER_MODEL)
        print(f" {CJ}✓{RST}")

        # Память
        self.memory: Memory | None = None
        if MEMORY_OK:
            print(f"{CS}⚙  Инициализирую память...{RST}", end="", flush=True)
            try:
                self.memory = Memory()
                print(f" {CJ}✓  ({len(self.memory)} фактов){RST}")
            except Exception as e:
                print(f" {CE}✗ {e}{RST}")

        # Управление ПК
        self.pc: PCControl | None = None
        if PC_OK:
            self.pc = PCControl(self.client)
            print(f"{CJ}✓  Управление ПК готово{RST}")

        # Браузер (запускается лениво при первой команде)
        self.browser: BrowserSync | None = None
        self._browser_started = False

    def _ensure_browser(self):
        if BROWSER_OK and not self._browser_started:
            print(f"{CB}🌐 Запускаю браузер...{RST}")
            self.browser = BrowserSync(headless=False)
            self.browser.start()
            self._browser_started = True
            print(f"{CB}✓  Браузер готов{RST}")

    # ── STT ──────────────────────────────────────────────────────────────────
    def transcribe(self, wav_path: str) -> str:
        result = self.whisper.transcribe(wav_path, fp16=False)
        os.unlink(wav_path)
        return result["text"].strip()

    # ── LLM с памятью ─────────────────────────────────────────────────────────
    def ask_claude(self, user_text: str) -> str:
        # Подтягиваем релевантные воспоминания
        memory_ctx = ""
        if self.memory:
            memory_ctx = self.memory.context_for_prompt(user_text)

        system = BASE_SYSTEM
        if memory_ctx:
            system += f"\n\n{memory_ctx}"

        self.history.append({"role": "user", "content": user_text})
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=system,
            messages=self.history,
        )
        answer = response.content[0].text
        self.history.append({"role": "assistant", "content": answer})
        return answer

    # ── Разбор тегов и выполнение действий ───────────────────────────────────
    def _handle_response(self, response: str, user_text: str) -> str:
        """Разбирает теги в ответе Claude и выполняет действия."""

        # [MEMORY: факт]
        m = re.search(r"\[MEMORY:\s*(.+?)\]", response)
        if m and self.memory:
            fact = m.group(1).strip()
            self.memory.save(fact)
            print(f"  {CM}💾 Запомнено: {fact}{RST}")

        # [BROWSER: команда]
        b = re.search(r"\[BROWSER:\s*(.+?)\]", response)
        if b:
            cmd = b.group(1).strip().lower()
            self._ensure_browser()
            browser_result = self._handle_browser_cmd(cmd, user_text)
            if browser_result:
                print(f"  {CB}🌐 {browser_result}{RST}")
                # Добавляем результат в ответ
                clean = re.sub(r"\[BROWSER:[^\]]*\]", "", response).strip()
                return clean + "\n" + browser_result

        # [PC: команда]
        p = re.search(r"\[PC:\s*(.+?)\]", response)
        if p and self.pc:
            cmd = p.group(1).strip()
            pc_result = self.pc.execute(cmd)
            print(f"  {CJ}🖥  {pc_result}{RST}")

        return response

    def _handle_browser_cmd(self, cmd: str, original: str) -> str:
        if not self.browser:
            return ""
        try:
            if "погода" in cmd or "weather" in cmd:
                city = re.search(r"(?:в|in)\s+(.+)", original)
                c = city.group(1) if city else "New York"
                return self.browser.get_weather(c)
            elif "youtube" in cmd or "ютуб" in cmd:
                query = re.sub(r"(?:найди|включи|поставь|play|search|youtube|ютуб)\s*", "", original).strip()
                return self.browser.youtube_search(query)
            elif "найди" in cmd or "search" in cmd or "поищи" in cmd:
                query = re.sub(r"(?:найди|поищи|search|google)\s*", "", original).strip()
                return self.browser.search(query)
            elif re.search(r"https?://|\.com|\.ru|\.org", cmd):
                url = re.search(r"[\w\-]+\.[\w\-]+(?:\.[\w\-]+)*", cmd)
                if url:
                    return self.browser.open(url.group())
            return ""
        except Exception as e:
            return f"Ошибка браузера: {e}"

    # ── Главный цикл ─────────────────────────────────────────────────────────
    def run(self):
        self._banner()
        print(f"\n{CS}Зажми {CJ}[ПРОБЕЛ]{CS} → говори → отпусти. {CJ}[ESC]{CS} — выход.{RST}\n")

        recording = False
        try:
            while True:
                if keyboard.is_pressed(HOTKEY) and not recording:
                    recording = True
                    self.recorder.start()
                    print(f"\r{CU}🎤 Запись...{RST}               ", end="", flush=True)

                elif not keyboard.is_pressed(HOTKEY) and recording:
                    recording = False
                    print(f"\r{CS}⏳ Распознаю...{RST}            ", end="", flush=True)

                    wav = self.recorder.stop()
                    if not wav:
                        print(f"\r{CE}(слишком коротко){RST}           ")
                        continue

                    user_text = self.transcribe(wav)
                    if not user_text:
                        print(f"\r{CE}(не услышал){RST}                ")
                        continue

                    ts = datetime.now().strftime("%H:%M")
                    print(f"\r{CU}[{ts}] Ты: {user_text}{RST}          ")

                    print(f"{DIM}💭 Думаю...{RST}", end="", flush=True)
                    raw_answer = self.ask_claude(user_text)
                    answer = self._handle_response(raw_answer, user_text)

                    # Чистый текст для вывода и TTS
                    clean = re.sub(r"\[(?:BROWSER|PC|MEMORY|SEARCH):[^\]]*\]", "", answer).strip()
                    print(f"\r{CJ}[{ts}] JARVIS: {clean}{RST}          ")
                    self.tts.speak(clean)

                elif keyboard.is_pressed("esc"):
                    break

                time.sleep(0.05)

        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _banner(self):
        modules = []
        if MEMORY_OK:  modules.append("Память")
        if PC_OK:      modules.append("ПК")
        if BROWSER_OK: modules.append("Браузер")
        mods = " · ".join(modules) if modules else "базовый режим"
        print(f"""
{CJ}╔══════════════════════════════════════╗
║          J A R V I S  v2.0           ║
║  {mods:<36}║
╚══════════════════════════════════════╝{RST}""")

    def _shutdown(self):
        print(f"\n{CS}👋 Завершение...{RST}")
        self.tts.stop()
        self.recorder.cleanup()
        if self.browser:
            self.browser.stop()
        print(f"{CJ}До встречи!{RST}")


if __name__ == "__main__":
    JarvisV2().run()
