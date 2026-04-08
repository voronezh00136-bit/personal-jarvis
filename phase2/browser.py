"""
browser.py — Браузерная автоматизация (Phase 2)
Построено на Playwright. Синхронная обёртка для удобного использования.

Использование:
    from browser import BrowserSync
    b = BrowserSync(headless=False)
    b.start()
    result = b.search("последние новости AI")
    b.stop()
"""

import threading
import asyncio
from typing import Optional


try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False


class BrowserSync:
    """Синхронная обёртка над Playwright для использования из синхронного кода."""

    def __init__(self, headless: bool = False):
        if not PLAYWRIGHT_OK:
            raise ImportError("pip install playwright && playwright install chromium")
        self._headless = headless
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._browser = None
        self._page = None
        self._ready = threading.Event()

    def start(self) -> None:
        """Запускает браузер в фоновом потоке."""
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=15)

    def stop(self) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._close(), self._loop)

    def search(self, query: str) -> str:
        return self._call(self._search(query))

    def get_weather(self, city: str) -> str:
        return self._call(self._weather(city))

    def youtube_search(self, query: str) -> str:
        return self._call(self._youtube(query))

    def open(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        return self._call(self._goto(url))

    # ── Internal ────────────────────────────────────────────────────────────

    def _call(self, coro) -> str:
        if not self._loop:
            return "Браузер не запущен"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=30)
        except Exception as e:
            return f"Ошибка браузера: {e}"

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._init())
        self._ready.set()
        self._loop.run_forever()

    async def _init(self):
        pw = await async_playwright().__aenter__()
        self._browser = await pw.chromium.launch(headless=self._headless)
        self._page = await self._browser.new_page()
        await self._page.set_extra_http_headers({"Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8"})

    async def _close(self):
        if self._browser:
            await self._browser.close()
        if self._loop:
            self._loop.stop()

    async def _goto(self, url: str) -> str:
        await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        return f"Открыл {url}"

    async def _search(self, query: str) -> str:
        url = f"https://www.google.com/search?q={query.replace(' ', '+')}&hl=ru"
        await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        # Извлекаем первые 3 результата
        results = await self._page.query_selector_all("h3")
        texts = []
        for r in results[:3]:
            t = await r.inner_text()
            if t.strip():
                texts.append(t.strip())
        if texts:
            return "Результаты поиска: " + "; ".join(texts)
        return f"Открыл поиск по запросу: {query}"

    async def _weather(self, city: str) -> str:
        url = f"https://wttr.in/{city.replace(' ', '+')}?format=3&lang=ru"
        await self._page.goto(url, timeout=10000)
        text = await self._page.inner_text("body")
        return text.strip()[:200] if text else f"Погода в {city} недоступна"

    async def _youtube(self, query: str) -> str:
        url = f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
        await self._page.goto(url, wait_until="domcontentloaded", timeout=15000)
        titles = await self._page.query_selector_all("#video-title")
        texts = []
        for t in titles[:3]:
            txt = await t.inner_text()
            if txt.strip():
                texts.append(txt.strip())
        if texts:
            return "YouTube: " + "; ".join(texts)
        return f"Открыл YouTube поиск: {query}"
