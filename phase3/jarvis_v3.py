"""
jarvis_v3.py — JARVIS Phase 3: агенты + планировщик + аватар

Запуск:
    python jarvis_v3.py
    python jarvis_v3.py --no-avatar   # без аватара
    python jarvis_v3.py --avatar did  # D-ID аватар (нужен DID_API_KEY)

Зависимости: pip install -r requirements_v3.txt
"""

import os
import sys
import time
import wave
import queue
import tempfile
import threading
import argparse
from datetime import datetime

# ── Базовые зависимости ────────────────────────────────────────────────────
try:
    import anthropic
    import whisper
    import pyttsx3
    import pyaudio
    import keyboard
    from colorama import Fore, Style, init as colorama_init
except ImportError as e:
    print(f"❌ {e}\npip install -r requirements_v3.txt")
    sys.exit(1)

colorama_init(autoreset=True)
CJ = Fore.CYAN; CU = Fore.GREEN; CS = Fore.YELLOW; CE = Fore.RED; DIM = Style.DIM; RST = Style.RESET_ALL

# ── Фаза 2 модули ─────────────────────────────────────────────────────────
try:
    from memory import Memory
except ImportError:
    Memory = None

# ── Фаза 3 модули ─────────────────────────────────────────────────────────
try:
    from orchestrator import JarvisGraph
    GRAPH_OK = True
except ImportError:
    GRAPH_OK = False
    print(f"{CS}⚠  orchestrator.py не найден — используется прямой вызов Claude{RST}")

try:
    from scheduler import get_scheduler
    SCHED_OK = True
except ImportError:
    SCHED_OK = False

try:
    from avatar import Avatar
    AVATAR_OK = True
except ImportError:
    AVATAR_OK = False

# ── Конфиг ────────────────────────────────────────────────────────────────
WHISPER_MODEL = "small"
SAMPLE_RATE   = 16000
CHANNELS      = 1
CHUNK         = 1024
HOTKEY        = "space"


class AudioRecorder:
    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self._frames, self._recording, self._stream = [], False, None

    def start(self):
        self._frames = []; self._recording = True
        self._stream = self.pa.open(
            format=pyaudio.paInt16, channels=CHANNELS,
            rate=SAMPLE_RATE, input=True, frames_per_buffer=CHUNK,
        )
        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        while self._recording:
            try:
                self._frames.append(self._stream.read(CHUNK, exception_on_overflow=False))
            except Exception:
                break

    def stop(self):
        self._recording = False; time.sleep(0.1)
        if self._stream:
            self._stream.stop_stream(); self._stream.close(); self._stream = None
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
    def __init__(self, avatar=None):
        self.engine  = pyttsx3.init()
        self._avatar = avatar
        self._q: queue.Queue = queue.Queue()
        voices = self.engine.getProperty("voices")
        ru = next((v for v in voices if "ru" in v.id.lower() or "russian" in v.name.lower()), None)
        if ru:
            self.engine.setProperty("voice", ru.id)
        elif voices:
            self.engine.setProperty("voice", voices[0].id)
        self.engine.setProperty("rate", 175)
        threading.Thread(target=self._worker, daemon=True).start()

    def speak(self, text: str):
        self._q.put(text)

    def _worker(self):
        while True:
            text = self._q.get()
            if text is None:
                break
            # Синхронизируем аватар
            if self._avatar:
                self._avatar.speak(text)
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception:
                pass

    def stop(self):
        self._q.put(None)


class JarvisV3:
    def __init__(self, avatar_mode: str = "local", no_avatar: bool = False):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(f"{CE}❌  Нужен ANTHROPIC_API_KEY{RST}"); sys.exit(1)

        # Whisper
        print(f"{CS}⚙  Whisper {WHISPER_MODEL}...{RST}", end="", flush=True)
        self.whisper_model = whisper.load_model(WHISPER_MODEL)
        print(f" {CJ}✓{RST}")

        # Аватар
        self.avatar = None
        if not no_avatar and AVATAR_OK:
            try:
                self.avatar = Avatar(mode=avatar_mode)
                self.avatar.show()
                print(f"{CJ}✓  Аватар ({avatar_mode}) запущен{RST}")
            except Exception as e:
                print(f"{CS}⚠  Аватар недоступен: {e}{RST}")

        # TTS
        self.tts = TTSEngine(avatar=self.avatar)

        # Память
        self.memory = None
        if Memory:
            try:
                self.memory = Memory()
                print(f"{CJ}✓  Память ({len(self.memory)} фактов){RST}")
            except Exception as e:
                print(f"{CS}⚠  Память: {e}{RST}")

        # Граф агентов
        self.graph = None
        if GRAPH_OK:
            self.graph = JarvisGraph()
            print(f"{CJ}✓  Граф агентов LangGraph{RST}")

        # Планировщик
        self.scheduler = None
        if SCHED_OK:
            self.scheduler = get_scheduler()
            self.scheduler.set_tts(self.tts.speak)
            self.scheduler.setup_break_reminder(90)  # напоминание каждые 90 мин
            print(f"{CJ}✓  Планировщик ({len(self.scheduler.list_tasks())} задач){RST}")

        # Аудио
        self.recorder = AudioRecorder()
        self.client   = anthropic.Anthropic(api_key=api_key)

    # ── STT ────────────────────────────────────────────────────────────────
    def transcribe(self, wav_path: str) -> str:
        result = self.whisper_model.transcribe(wav_path, fp16=False)
        os.unlink(wav_path)
        return result["text"].strip()

    # ── Обработка запроса ──────────────────────────────────────────────────
    def process(self, user_text: str) -> str:
        if self.avatar:
            self.avatar.think()

        # Достаём воспоминания
        memory_facts = []
        if self.memory:
            facts = self.memory.search(user_text, n=4)
            memory_facts = [f["text"] for f in facts]

            # Автосохранение: "запомни что..."
            import re
            m = re.search(r"(?:запомни|помни)[,\s]+(?:что\s+)?(.+)", user_text, re.I)
            if m:
                self.memory.save(m.group(1).strip())

        # Через граф агентов или напрямую
        if self.graph:
            result = self.graph.run_sync(user_text, memory_facts=memory_facts)
            response = result["response"]
            route    = result["route"]
            print(f"  {DIM}[{route}]{RST}", end=" ")
        else:
            # Fallback — прямой Claude
            messages = [{"role": "user", "content": user_text}]
            resp = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                system="Ты JARVIS. Отвечай кратко, 2-3 предложения.",
                messages=messages,
            )
            response = resp.content[0].text

        return response

    # ── Главный цикл ──────────────────────────────────────────────────────
    def run(self):
        self._banner()
        self.tts.speak("JARVIS активирован. Все системы в норме.")
        print(f"\n{CS}[ПРОБЕЛ] говорить · [ESC] выход{RST}\n")

        recording = False
        try:
            while True:
                if keyboard.is_pressed(HOTKEY) and not recording:
                    recording = True
                    self.recorder.start()
                    if self.avatar:
                        self.avatar.listen()
                    print(f"\r{CU}🎤 Запись...{RST}            ", end="", flush=True)

                elif not keyboard.is_pressed(HOTKEY) and recording:
                    recording = False
                    print(f"\r{CS}⏳ Обрабатываю...{RST}       ", end="", flush=True)

                    wav = self.recorder.stop()
                    if not wav:
                        print(f"\r{CE}(слишком коротко){RST}      ")
                        continue

                    text = self.transcribe(wav)
                    if not text:
                        print(f"\r{CE}(не услышал){RST}           ")
                        continue

                    ts = datetime.now().strftime("%H:%M")
                    print(f"\r{CU}[{ts}] Ты: {text}{RST}          ")

                    response = self.process(text)
                    print(f"{CJ}[{ts}] JARVIS: {response}{RST}")
                    self.tts.speak(response)

                elif keyboard.is_pressed("esc"):
                    break

                time.sleep(0.05)

        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _banner(self):
        features = []
        if self.memory:    features.append("Память")
        if self.graph:     features.append("Агенты")
        if self.scheduler: features.append("Планировщик")
        if self.avatar:    features.append("Аватар")
        f = " · ".join(features) if features else "базовый"
        print(f"""
{CJ}╔══════════════════════════════════════╗
║          J A R V I S  v3.0           ║
║  {f:<36}║
╚══════════════════════════════════════╝{RST}""")

    def _shutdown(self):
        print(f"\n{CS}Завершение...{RST}")
        self.tts.stop()
        self.recorder.cleanup()
        if self.scheduler:
            self.scheduler.shutdown()
        if self.avatar:
            self.avatar.cleanup()
        print(f"{CJ}До встречи!{RST}")


# ── CLI ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JARVIS v3.0")
    parser.add_argument("--no-avatar",  action="store_true", help="Без аватара")
    parser.add_argument("--avatar",     default="local",     help="local | did")
    args = parser.parse_args()

    JarvisV3(avatar_mode=args.avatar, no_avatar=args.no_avatar).run()
