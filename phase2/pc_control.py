"""
pc_control.py — Управление ПК (Phase 2)
Скриншоты + анализ через Claude Vision + мышь/клавиатура через PyAutoGUI.

Использование:
    from pc_control import PCControl
    pc = PCControl(anthropic_client)
    result = pc.execute("сделай скриншот и скажи что на экране")
"""

import os
import base64
import tempfile
import subprocess
import platform
from typing import Optional


try:
    import pyautogui
    import anthropic
    from PIL import Image
    PYAUTOGUI_OK = True
except ImportError:
    PYAUTOGUI_OK = False


# Команды для открытия приложений
APP_MAP = {
    "браузер":    {"darwin": "open -a Safari",     "win32": "start chrome", "linux": "xdg-open http://"},
    "хром":       {"darwin": "open -a 'Google Chrome'", "win32": "start chrome", "linux": "google-chrome"},
    "терминал":   {"darwin": "open -a Terminal",   "win32": "start cmd",    "linux": "xterm"},
    "файлы":      {"darwin": "open ~",             "win32": "explorer .",   "linux": "xdg-open ~"},
    "калькулятор":{"darwin": "open -a Calculator", "win32": "calc",         "linux": "gnome-calculator"},
    "spotify":    {"darwin": "open -a Spotify",    "win32": "start spotify","linux": "spotify"},
    "vscode":     {"darwin": "open -a 'Visual Studio Code'", "win32": "code", "linux": "code"},
}


class PCControl:
    """Управляет мышью, клавиатурой, скриншотами."""

    def __init__(self, client: "anthropic.Anthropic"):
        if not PYAUTOGUI_OK:
            raise ImportError("pip install pyautogui pillow")
        self.client = client
        self._sys = platform.system().lower()  # darwin / windows / linux
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.3

    def execute(self, cmd: str) -> str:
        """Выполняет PC-команду по текстовому описанию."""
        cmd_l = cmd.lower()

        if any(w in cmd_l for w in ["скриншот", "screenshot", "что на экране", "what's on screen"]):
            return self.screenshot_and_describe()

        if any(w in cmd_l for w in ["громкость", "volume", "звук"]):
            return self._volume(cmd_l)

        if any(w in cmd_l for w in ["открой", "запусти", "open", "launch", "start"]):
            return self._open_app(cmd_l)

        if any(w in cmd_l for w in ["скопируй", "copy", "ctrl+c"]):
            pyautogui.hotkey("ctrl", "c")
            return "Скопировано в буфер обмена"

        if any(w in cmd_l for w in ["вставь", "paste", "ctrl+v"]):
            pyautogui.hotkey("ctrl", "v")
            return "Вставлено"

        return f"Не знаю как выполнить: {cmd}"

    def screenshot_and_describe(self) -> str:
        """Делает скриншот и описывает содержимое через Claude Vision."""
        path = self._take_screenshot()
        if not path:
            return "Не удалось сделать скриншот"

        with open(path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode()
        os.unlink(path)

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_data}},
                        {"type": "text", "text": "Опиши кратко (2-3 предложения) что изображено на этом скриншоте экрана."},
                    ],
                }],
            )
            return response.content[0].text
        except Exception as e:
            return f"Ошибка анализа скриншота: {e}"

    def _take_screenshot(self) -> Optional[str]:
        try:
            screenshot = pyautogui.screenshot()
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            screenshot.save(tmp.name)
            return tmp.name
        except Exception:
            return None

    def _volume(self, cmd: str) -> str:
        if self._sys == "darwin":
            if "выкл" in cmd or "mute" in cmd:
                os.system("osascript -e 'set volume output muted true'")
                return "Звук выключен"
            elif "вкл" in cmd or "unmute" in cmd:
                os.system("osascript -e 'set volume output muted false'")
                return "Звук включён"
            elif "тише" in cmd or "down" in cmd:
                pyautogui.press("volumedown")
                return "Громкость уменьшена"
            else:
                pyautogui.press("volumeup")
                return "Громкость увеличена"
        elif self._sys == "windows":
            if "тише" in cmd or "down" in cmd:
                pyautogui.press("volumedown")
            else:
                pyautogui.press("volumeup")
            return "Громкость изменена"
        return "Управление громкостью не поддерживается на этой ОС"

    def _open_app(self, cmd: str) -> str:
        platform_key = "darwin" if self._sys == "darwin" else ("win32" if self._sys == "windows" else "linux")
        for keyword, cmds in APP_MAP.items():
            if keyword in cmd:
                shell_cmd = cmds.get(platform_key, "")
                if shell_cmd:
                    subprocess.Popen(shell_cmd, shell=True)
                    return f"Открываю {keyword}"
        return "Не знаю какое приложение открыть"
