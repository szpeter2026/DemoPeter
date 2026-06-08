"""
Chronicle Retrieve — 事件检索

使用方式:
    from chronicle import ChronicleRetrieve

    retriever = ChronicleRetrieve()
    results = retriever.search("上次盘点工作区是什么结果", top_k=5)
    for r in results:
        print(r["title"], r["similarity"])
"""
import os
import json
import logging
from typing import Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from .ingest import CHRONICLE_COLLECTION

logger = logging.getLogger(__name__)


class ChronicleRetrieve:
    """史料事件检索器"""

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        ollama_url: str = "http://localhost:11434",
        embedding_model: str = "nomic-embed-text:latest",
    ):
        persist_dir = persist_dir or os.environ.get(
            "CHROMA_PERSIST_DIR",
            os.path.join(os.path.dirname(__file__), "..", "db", "chroma_data"),
        )
        self.persist_dir = os.path.abspath(persist_dir)

        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        try:
            self._collection = self._client.get_collection(CHRONICLE_COLLECTION)
        except Exception:
            logger.warning("Chronicle collection 不存在，创建空 collection")
            self._collection = self._client.create_collection(
                name=CHRONICLE_COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

        # Ollama embedding function
        self._ef = None
        try:
            from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
            self._ef = OllamaEmbeddingFunction(
                url=f"{ollama_url}/api/embeddings",
                model_name=embedding_model,
            )
        except Exception:
            self._ef = None

    def search(
        self,
        query: str,
        top_k: int = 5,
        project: Optional[str] = None,
        event_type: Optional[str] = None,
    ) -> list[dict]:
        """语义搜索历史事件

        Args:
            query: 搜索文本
            top_k: 返回条数
            project: 可选按项目过滤
            event_type: 可选按事件类型过滤
        """
        where_filter = None
        conditions = []
        if project:
            conditions.append({"project": project})
        if event_type:
            conditions.append({"event_type": event_type})
        if len(conditions) == 1:
            where_filter = conditions[0]
        elif len(conditions) > 1:
            where_filter = {"$and": conditions}

        kwargs = {
            "query_texts": [query],
            "n_results": min(top_k, self._collection.count()),
        }
        if where_filter:
            kwargs["where"] = where_filter

        if self._collection.count() == 0:
            return []

        results = self._collection.query(**kwargs)

        # 格式化结果
        formatted = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                doc = results["documents"][0][i] if results["documents"] else ""
                dist = results["distances"][0][i] if results["distances"] else 1.0
                formatted.append({
                    "id": doc_id,
                    "title": meta.get("title", ""),
                    "event_type": meta.get("event_type", ""),
                    "project": meta.get("project", ""),
                    "tags": (meta.get("tags", "") or "").split(",") if meta.get("tags") else [],
                    "timestamp": meta.get("timestamp", ""),
                    "text": doc,
                    "distance": dist,
                    "similarity": round(max(0, 1 - dist), 4),  # cosine distance → similarity
                })

        return formatted

    def list_recent(self, limit: int = 20) -> list[dict]:
        """列出最近事件（按时间倒序，走 Chroma metadata + Python 排序）"""
        if self._collection.count() == 0:
            return []

        # 获取全部 metadatas
        all_data = self._collection.get(limit=min(limit * 3, self._collection.count()))
        if not all_data["ids"]:
            return []

        events = []
        for i, doc_id in enumerate(all_data["ids"]):
            meta = all_data["metadatas"][i]
            events.append({
                "id": doc_id,
                "title": meta.get("title", ""),
                "event_type": meta.get("event_type", ""),
                "project": meta.get("project", ""),
                "timestamp": meta.get("timestamp", ""),
            })

        events.sort(key=lambda e: e["timestamp"], reverse=True)
        return events[:limit]

    @property
    def count(self) -> int:
        return self._collection.count()
