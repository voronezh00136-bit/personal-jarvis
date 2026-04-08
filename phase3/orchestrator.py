"""
orchestrator.py — LangGraph мультиагентный роутер (Phase 3)
Маршрутизирует запросы: chat | search | scheduler | code | smarthome

Использование:
    from orchestrator import JarvisGraph
    graph = JarvisGraph()
    result = graph.run_sync("найди новости по AI")
    # result = {"response": "...", "route": "search"}
"""

import os
import re
from typing import TypedDict, Annotated, Optional


try:
    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage
    from langgraph.graph import StateGraph, END
    LANGGRAPH_OK = True
except ImportError:
    LANGGRAPH_OK = False

try:
    from tavily import TavilyClient
    TAVILY_OK = True
except ImportError:
    TAVILY_OK = False


# ── Состояние графа ─────────────────────────────────────────────────────────

class JarvisState(TypedDict):
    user_input:   str
    route:        str
    response:     str
    memory_facts: list[str]
    search_results: str


# ── Ключевые слова для маршрутизации ────────────────────────────────────────

SEARCH_KW   = ["найди", "поищи", "search", "новости", "news", "погода", "weather", "курс", "цена"]
SCHEDULE_KW = ["напомни", "поставь напоминание", "remind", "schedule", "через", "в ", "поставь будильник"]
CODE_KW     = ["посчитай", "вычисли", "calculate", "код", "code", "написать функцию", "python"]
HOME_KW     = ["включи свет", "выключи свет", "умный дом", "home assistant", "светом", "термостат"]


def _classify(text: str) -> str:
    t = text.lower()
    if any(k in t for k in SEARCH_KW):   return "search"
    if any(k in t for k in SCHEDULE_KW): return "scheduler"
    if any(k in t for k in CODE_KW):     return "code"
    if any(k in t for k in HOME_KW):     return "smarthome"
    return "chat"


# ── Узлы графа ───────────────────────────────────────────────────────────────

def router_node(state: JarvisState) -> JarvisState:
    state["route"] = _classify(state["user_input"])
    return state


def _make_llm():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    return ChatAnthropic(model="claude-sonnet-4-20250514", anthropic_api_key=api_key, max_tokens=400)


def chat_node(state: JarvisState) -> JarvisState:
    llm = _make_llm()
    memory_ctx = ""
    if state.get("memory_facts"):
        memory_ctx = "\n".join(f"- {f}" for f in state["memory_facts"])
        memory_ctx = f"\n\nРелевантные факты о пользователе:\n{memory_ctx}"

    system = f"Ты JARVIS — краткий голосовой ассистент. 2-3 предложения максимум.{memory_ctx}"
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=state["user_input"])])
    state["response"] = response.content
    return state


def search_node(state: JarvisState) -> JarvisState:
    if TAVILY_OK and os.environ.get("TAVILY_API_KEY"):
        try:
            client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
            results = client.search(state["user_input"], max_results=3)
            snippets = [r.get("content", "")[:200] for r in results.get("results", [])]
            search_ctx = " | ".join(snippets)

            llm = _make_llm()
            prompt = f"Вопрос: {state['user_input']}\n\nРезультаты поиска:\n{search_ctx}\n\nОтветь кратко (2-3 предложения)."
            response = llm.invoke([HumanMessage(content=prompt)])
            state["response"] = response.content
            return state
        except Exception as e:
            state["response"] = f"Ошибка поиска: {e}. Отвечаю без интернета."

    # Fallback без Tavily
    return chat_node(state)


def code_node(state: JarvisState) -> JarvisState:
    llm = _make_llm()
    system = ("Ты JARVIS. Если пользователь просит что-то посчитать или написать код — "
              "выполни вычисление и дай краткий ответ. Если нужен код — дай готовый рабочий код.")
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=state["user_input"])])
    state["response"] = response.content
    return state


def scheduler_node(state: JarvisState) -> JarvisState:
    # Парсим время из запроса
    text = state["user_input"]
    time_match = re.search(r"\b(\d{1,2})[:\.](\d{2})\b", text)
    minutes_match = re.search(r"через\s+(\d+)\s+(?:минут|мин)", text, re.I)

    if time_match:
        h, m = time_match.group(1), time_match.group(2)
        state["response"] = f"Напоминание поставлено на {h}:{m}."
    elif minutes_match:
        mins = minutes_match.group(1)
        state["response"] = f"Напомню через {mins} минут."
    else:
        state["response"] = "Укажи конкретное время, например: 'напомни в 18:30'"

    return state


def smarthome_node(state: JarvisState) -> JarvisState:
    ha_url   = os.environ.get("HA_URL", "")
    ha_token = os.environ.get("HA_TOKEN", "")

    if not ha_url or not ha_token:
        state["response"] = "Home Assistant не настроен. Задай HA_URL и HA_TOKEN в переменных окружения."
        return state

    try:
        import requests
        headers = {"Authorization": f"Bearer {ha_token}", "Content-Type": "application/json"}
        text = state["user_input"].lower()

        if "включи" in text:
            entity = "light.kitchen" if "кухн" in text else "light.living_room"
            requests.post(f"{ha_url}/api/services/light/turn_on",
                         headers=headers, json={"entity_id": entity}, timeout=5)
            state["response"] = f"Свет включён."
        elif "выключи" in text:
            entity = "light.kitchen" if "кухн" in text else "light.living_room"
            requests.post(f"{ha_url}/api/services/light/turn_off",
                         headers=headers, json={"entity_id": entity}, timeout=5)
            state["response"] = f"Свет выключен."
        else:
            state["response"] = "Что нужно сделать? (включи / выключи)"
    except Exception as e:
        state["response"] = f"Ошибка Home Assistant: {e}"

    return state


def route_selector(state: JarvisState) -> str:
    return state["route"]


# ── Граф ──────────────────────────────────────────────────────────────────────

def build_graph():
    if not LANGGRAPH_OK:
        raise ImportError("pip install langgraph langchain-core langchain-anthropic")

    g = StateGraph(JarvisState)
    g.add_node("router",    router_node)
    g.add_node("chat",      chat_node)
    g.add_node("search",    search_node)
    g.add_node("code",      code_node)
    g.add_node("scheduler", scheduler_node)
    g.add_node("smarthome", smarthome_node)

    g.set_entry_point("router")
    g.add_conditional_edges("router", route_selector, {
        "chat":      "chat",
        "search":    "search",
        "code":      "code",
        "scheduler": "scheduler",
        "smarthome": "smarthome",
    })
    for node in ["chat", "search", "code", "scheduler", "smarthome"]:
        g.add_edge(node, END)

    return g.compile()


class JarvisGraph:
    def __init__(self):
        self._graph = build_graph()

    def run_sync(self, user_input: str, memory_facts: list[str] | None = None) -> dict:
        state: JarvisState = {
            "user_input":    user_input,
            "route":         "chat",
            "response":      "",
            "memory_facts":  memory_facts or [],
            "search_results": "",
        }
        result = self._graph.invoke(state)
        return {"response": result["response"], "route": result["route"]}
