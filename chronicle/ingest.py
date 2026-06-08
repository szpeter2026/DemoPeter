"""
Chronicle Ingest — 事件写入 Chroma

使用方式:
    from chronicle import ChronicleIngest, ChronicleEvent, EventType, ProjectTag

    ingester = ChronicleIngest()
    event = ChronicleEvent(
        title="盘点 C 盘 D 盘所有工作区",
        event_type=EventType.DISCOVERY,
        full_text="Peter 要求盘点所有工作区...",
        project=ProjectTag.WORKBUDDY,
        tags=["知识管理", "盘点"],
    )
    ingester.ingest(event)
"""
import os
import logging
from typing import Optional
import chromadb
from chromadb.config import Settings as ChromaSettings

from .schema import ChronicleEvent

logger = logging.getLogger(__name__)

CHRONICLE_COLLECTION = "chronicle"


class ChronicleIngest:
    """史料事件写入器"""

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
        self.ollama_url = ollama_url
        self.embedding_model = embedding_model

        # 确保目录存在
        os.makedirs(self.persist_dir, exist_ok=True)

        # 初始化 Chroma 客户端（持久化模式）
        self._client = chromadb.PersistentClient(
            path=self.persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        # 确保 collection 存在
        self._collection = self._client.get_or_create_collection(
            name=CHRONICLE_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

        # 尝试用 Ollama embedding function
        self._ef = None
        try:
            from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
            self._ef = OllamaEmbeddingFunction(
                url=f"{self.ollama_url}/api/embeddings",
                model_name=self.embedding_model,
            )
            logger.info("Chronicle 使用 OllamaEmbeddingFunction: %s", self.embedding_model)
        except Exception:
            logger.warning("OllamaEmbeddingFunction 不可用，回退到 Chroma 默认 ONNX 嵌入")
            self._ef = None

    def ingest(self, event: ChronicleEvent) -> str:
        """写入一条事件到 Chroma"""
        doc_id = f"chronicle_{event.id}"
        text = event.chroma_text
        metadata = event.chroma_metadata

        if self._ef is not None:
            embedding = self._ef([text])
            self._collection.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
                embeddings=embedding,
            )
        else:
            self._collection.add(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )

        logger.info("Chronicle 写入: %s → %s", event.title, doc_id)
        return doc_id

    def ingest_batch(self, events: list[ChronicleEvent]) -> list[str]:
        """批量写入"""
        ids = []
        docs = []
        metas = []
        for e in events:
            ids.append(f"chronicle_{e.id}")
            docs.append(e.chroma_text)
            metas.append(e.chroma_metadata)

        if self._ef is not None:
            embeddings = self._ef(docs)
            self._collection.add(
                ids=ids, documents=docs, metadatas=metas, embeddings=embeddings,
            )
        else:
            self._collection.add(
                ids=ids, documents=docs, metadatas=metas,
            )

        logger.info("Chronicle 批量写入: %d 条", len(events))
        return ids

    @property
    def count(self) -> int:
        return self._collection.count()

    def close(self):
        """关闭（持久化客户端无需显式关闭，这里做接口一致性）"""
        pass
