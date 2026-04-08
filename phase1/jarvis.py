"""
JARVIS — голосовой ИИ-ассистент
Стек: Whisper (STT) + Claude API (мозг) + pyttsx3 (TTS)

Запуск:
    python jarvis.py

Горячая клавиша: удерживай ПРОБЕЛ → говори → отпусти → получи ответ
"""

import os
import sys
import tempfile
import threading
import time
import queue
import wave
from datetime import datetime

# ─── Проверка зависимостей ────────────────────────────────────────────────────
try:
    import anthropic
    import whisper
    import pyttsx3
    import pyaudio
    import keyboard
    import numpy as np
    from colorama import Fore, Style, init as colorama_init
except ImportError as e:
    print(f"\n❌  Не хватает зависимости: {e}")
    print("Установи всё командой:\n")
    print("  pip install anthropic openai-whisper pyttsx3 pyaudio keyboard numpy colorama")
    print("\nДля Windows pyaudio устанавливается так:")
    print("  pip install pipwin && pipwin install pyaudio\n")
    sys.exit(1)

colorama_init(autoreset=True)

# ─── Конфиг ──────────────────────────────────────────────────────────────────
CLAUDE_MODEL      = "claude-sonnet-4-20250514"
WHISPER_MODEL     = "base"          # tiny | base | small | medium | large
SAMPLE_RATE       = 16000
CHANNELS          = 1
CHUNK             = 1024
HOTKEY            = "space"         # клавиша записи (удерживать)
MAX_HISTORY       = 20              # сколько сообщений помнить

SYSTEM_PROMPT = """Ты JARVIS — личный ИИ-ассистент. Говоришь кратко и по делу.
Отвечаешь на том языке, на котором тебя спросили (русский или английский).
Избегай длинных списков — ты голосовой ассистент, не текстовый.
Если не знаешь что-то — честно скажи. Максимум 3-4 предложения на ответ."""

# ─── Цвета для вывода ────────────────────────────────────────────────────────
C_JARVIS  = Fore.CYAN
C_USER    = Fore.GREEN
C_SYSTEM  = Fore.YELLOW
C_ERROR   = Fore.RED
C_DIM     = Style.DIM
RESET     = Style.RESET_ALL


class AudioRecorder:
    """Записывает аудио пока зажата клавиша."""

    def __init__(self):
        self.pa = pyaudio.PyAudio()
        self._frames = []
        self._recording = False
        self._stream = None

    def start(self):
        self._frames = []
        self._recording = True
        self._stream = self.pa.open(
            format=pyaudio.paInt16,
            channels=CHANNELS,
            rate=SAMPLE_RATE,
            input=True,
            frames_per_buffer=CHUNK,
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
        """Останавливает запись и возвращает путь к WAV-файлу."""
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
    """Text-to-Speech через pyttsx3 с очередью."""

    def __init__(self):
        self.engine = pyttsx3.init()
        self._configure()
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _configure(self):
        voices = self.engine.getProperty("voices")
        # Пытаемся найти русский голос
        ru_voice = next(
            (v for v in voices if "ru" in v.id.lower() or "russian" in v.name.lower()),
            None,
        )
        if ru_voice:
            self.engine.setProperty("voice", ru_voice.id)
        elif voices:
            self.engine.setProperty("voice", voices[0].id)

        self.engine.setProperty("rate", 175)    # скорость речи
        self.engine.setProperty("volume", 0.95)

    def speak(self, text: str):
        self._queue.put(text)

    def _worker(self):
        while True:
            text = self._queue.get()
            if text is None:
                break
            try:
                self.engine.say(text)
                self.engine.runAndWait()
            except Exception as e:
                print(f"{C_ERROR}TTS ошибка: {e}{RESET}")

    def stop(self):
        self._queue.put(None)


class JarvisAssistant:
    """Основной класс ассистента."""

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print(f"{C_ERROR}❌  Установи переменную ANTHROPIC_API_KEY{RESET}")
            print("  Windows:  set ANTHROPIC_API_KEY=sk-ant-...")
            print("  Mac/Linux: export ANTHROPIC_API_KEY=sk-ant-...")
            sys.exit(1)

        print(f"{C_SYSTEM}⚙  Загружаю Whisper ({WHISPER_MODEL})...{RESET}", end="", flush=True)
        self.whisper = whisper.load_model(WHISPER_MODEL)
        print(f" {C_JARVIS}✓{RESET}")

        self.client   = anthropic.Anthropic(api_key=api_key)
        self.recorder = AudioRecorder()
        self.tts      = TTSEngine()
        self.history: list[dict] = []

        print(f"{C_SYSTEM}⚙  Инициализация TTS...{RESET} {C_JARVIS}✓{RESET}")

    # ── Распознавание речи ───────────────────────────────────────────────────
    def transcribe(self, wav_path: str) -> str:
        result = self.whisper.transcribe(wav_path, language=None, fp16=False)
        os.unlink(wav_path)  # удаляем временный файл
        return result["text"].strip()

    # ── Ответ от Claude ──────────────────────────────────────────────────────
    def ask_claude(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})

        # Обрезаем историю чтобы не переполнить контекст
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

        response = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            messages=self.history,
        )
        answer = response.content[0].text
        self.history.append({"role": "assistant", "content": answer})
        return answer

    # ── Главный цикл ─────────────────────────────────────────────────────────
    def run(self):
        self._print_banner()

        recording = False

        print(f"\n{C_SYSTEM}Зажми {C_JARVIS}[ПРОБЕЛ]{C_SYSTEM} чтобы говорить. "
              f"Нажми {C_JARVIS}[ESC]{C_SYSTEM} для выхода.{RESET}\n")

        try:
            while True:
                # Начало записи
                if keyboard.is_pressed(HOTKEY) and not recording:
                    recording = True
                    self.recorder.start()
                    print(f"\r{C_USER}🎤 Запись...{RESET}          ", end="", flush=True)

                # Конец записи
                elif not keyboard.is_pressed(HOTKEY) and recording:
                    recording = False
                    print(f"\r{C_SYSTEM}⏳ Распознаю...{RESET}        ", end="", flush=True)

                    wav_path = self.recorder.stop()
                    if not wav_path:
                        print(f"\r{C_ERROR}(слишком коротко, попробуй ещё){RESET}          ")
                        continue

                    # STT
                    user_text = self.transcribe(wav_path)
                    if not user_text:
                        print(f"\r{C_ERROR}(ничего не услышал){RESET}          ")
                        continue

                    ts = datetime.now().strftime("%H:%M")
                    print(f"\r{C_USER}[{ts}] Ты: {user_text}{RESET}          ")

                    # LLM
                    print(f"{C_DIM}💭 Думаю...{RESET}", end="", flush=True)
                    answer = self.ask_claude(user_text)
                    print(f"\r{C_JARVIS}[{ts}] JARVIS: {answer}{RESET}          ")

                    # TTS
                    self.tts.speak(answer)

                # Выход
                elif keyboard.is_pressed("esc"):
                    break

                time.sleep(0.05)

        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def _print_banner(self):
        banner = f"""
{C_JARVIS}╔══════════════════════════════════════╗
║          J A R V I S  v1.0           ║
║   Whisper · Claude · pyttsx3         ║
╚══════════════════════════════════════╝{RESET}"""
        print(banner)

    def _shutdown(self):
        print(f"\n{C_SYSTEM}👋 Завершение...{RESET}")
        self.tts.stop()
        self.recorder.cleanup()
        print(f"{C_JARVIS}До встречи!{RESET}")


# ─── Точка входа ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assistant = JarvisAssistant()
    assistant.run()
