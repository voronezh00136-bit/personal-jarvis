"""
memory.py — Долгосрочная память JARVIS (Phase 2)
Хранит факты в ChromaDB (локальная векторная БД).

Использование:
    from memory import Memory
    mem = Memory()
    mem.save("Пользователь работает над проектом FlowMoney")
    results = mem.search("FlowMoney", n=3)
    ctx = mem.context_for_prompt("расскажи про FlowMoney")
"""

import os
import hashlib
from datetime import datetime
from typing import Optional


try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_OK = True
except ImportError:
    CHROMA_OK = False


CHROMA_PATH = os.path.join(os.path.dirname(__file__), ".jarvis_memory")
COLLECTION  = "jarvis_facts"


class Memory:
    """Сохраняет и извлекает факты из ChromaDB."""

    def __init__(self, path: str = CHROMA_PATH):
        if not CHROMA_OK:
            raise ImportError("pip install chromadb sentence-transformers")

        self._client = chromadb.PersistentClient(path=path)
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        self._col = self._client.get_or_create_collection(
            name=COLLECTION,
            embedding_function=self._ef,
        )

    def __len__(self) -> int:
        return self._col.count()

    def save(self, fact: str) -> None:
        """Сохраняет факт. Дубликаты игнорируются по хешу."""
        doc_id = hashlib.md5(fact.encode()).hexdigest()
        existing = self._col.get(ids=[doc_id])
        if existing["ids"]:
            return  # уже есть
        self._col.add(
            documents=[fact],
            ids=[doc_id],
            metadatas=[{"saved_at": datetime.now().isoformat()}],
        )

    def search(self, query: str, n: int = 4) -> list[dict]:
        """Возвращает до n самых похожих фактов."""
        if self._col.count() == 0:
            return []
        results = self._col.query(query_texts=[query], n_results=min(n, self._col.count()))
        facts = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            facts.append({"text": doc, "saved_at": meta.get("saved_at", "")})
        return facts

    def context_for_prompt(self, query: str, n: int = 4) -> str:
        """Форматирует воспоминания как блок для системного промпта."""
        facts = self.search(query, n=n)
        if not facts:
            return ""
        lines = "\n".join(f"- {f['text']}" for f in facts)
        return f"ВСПОМНИ (релевантные факты о пользователе):\n{lines}"

    def forget(self, fact: str) -> None:
        """Удаляет конкретный факт."""
        doc_id = hashlib.md5(fact.encode()).hexdigest()
        self._col.delete(ids=[doc_id])

    def all_facts(self) -> list[str]:
        """Возвращает все сохранённые факты."""
        if self._col.count() == 0:
            return []
        return self._col.get()["documents"]
