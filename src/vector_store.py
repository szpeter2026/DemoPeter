"""
szpeter2026 - 向量存储
吸收自 72changes 的 Chroma 集成，管理文档向量化和检索
支持本地持久化（PersistentClient，零依赖）和远程服务（HttpClient）双模式
"""
import os
from typing import Optional

from config.settings import config

# Chroma 本地持久化目录（项目内置，无需 Docker）
CHROMA_PERSIST_DIR = str(config.DB_DIR / "chroma_data")


class VectorStore:
    """Chroma 向量数据库管理器
    
    初始化优先级：
    1. 本地持久化模式 (PersistentClient) — 数据存 db/chroma_data/，零依赖
    2. 远程服务模式 (HttpClient) — 需要 Docker/远程 Chroma 服务
    3. 不可用 — is_available = False
    """

    def __init__(self):
        self.collection_name = config.CHROMA_COLLECTION
        self._client = None
        self._collection = None
        self._mode = "unavailable"
        self._init_client()

    def _init_client(self):
        """初始化 Chroma 客户端，按配置的模式选择"""
        try:
            import chromadb
        except ImportError:
            self._client = None
            self._collection = None
            self._mode = "unavailable"
            return

        mode = config.CHROMA_MODE

        if mode == "persistent":
            self._try_persistent()
        elif mode == "remote":
            self._try_remote()
        else:  # "auto": 优先远程 → 回退本地
            if not self._try_remote():
                self._try_persistent()

    def _try_remote(self) -> bool:
        """尝试连接远程 Chroma 服务"""
        try:
            import chromadb
            self._client = chromadb.HttpClient(
                host=config.CHROMA_HOST,
                port=config.CHROMA_PORT,
            )
            # 心跳检测
            self._client.heartbeat()
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "szpeter2026 知识库向量存储 (remote)"},
            )
            self._mode = "remote"
            return True
        except Exception:
            self._client = None
            self._collection = None
            return False

    def _try_persistent(self) -> bool:
        """尝试本地持久化模式
        
        显式注入 DefaultEmbeddingFunction，避免 Chroma 隐式加载
        embedding 函数时因缺少 onnxruntime 而静默失败。
        """
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            # 显式加载 embedding 函数，尽早发现依赖缺失
            try:
                embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            except Exception as e:
                print(f"[VectorStore] ⚠️ 默认 Embedding 函数加载失败: {e}")
                print("[VectorStore] 请确保已安装 onnxruntime: pip install onnxruntime")
                self._client = None
                self._collection = None
                self._mode = "unavailable"
                return False

            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            self._client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_fn,
                metadata={"description": "szpeter2026 知识库向量存储 (persistent)"},
            )
            self._mode = "persistent"
            return True
        except Exception as e:
            print(f"[VectorStore] 本地持久化初始化失败: {e}")
            self._client = None
            self._collection = None
            self._mode = "unavailable"
            return False

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    def add_documents(self, doc_id: str, chunks: list[dict]) -> int:
        """批量添加文档分块到向量库"""
        if not self.is_available:
            return 0

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(chunks):
            ids.append(f"{doc_id}_chunk_{i}")
            documents.append(chunk["content"])
            metadatas.append({
                "doc_id": doc_id,
                "chunk_index": i,
                **(chunk.get("metadata", {})),
            })

        # 分批插入（Chroma 有限制）
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            self._collection.add(
                ids=ids[i:i + batch_size],
                documents=documents[i:i + batch_size],
                metadatas=metadatas[i:i + batch_size],
            )

        return len(ids)

    def search(self, query: str, top_k: int = 5,
               threshold: float = 0.5) -> list[dict]:
        """语义搜索"""
        if not self.is_available:
            return []

        results = self._collection.query(
            query_texts=[query],
            n_results=top_k,
        )

        hits = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results.get("distances", [[0]] * top_k)[0][i]
                # Chroma 默认用 squared L2 距离（对归一化向量: 0=相同, 4=相反）
                # 转换公式: cosine_similarity = 1 - L2/2
                similarity = 1.0 - distance / 2.0
                similarity = max(0.0, min(1.0, similarity))
                if similarity >= threshold:
                    hits.append({
                        "id": results["ids"][0][i],
                        "content": results["documents"][0][i],
                        "metadata": results.get("metadatas", [[{}]])[0][i],
                        "similarity": round(similarity, 4),
                    })

        return hits

    def delete_document(self, doc_id: str):
        """删除文档的所有向量"""
        if not self.is_available:
            return
        try:
            self._collection.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    def health_check(self) -> dict:
        """健康检查：验证向量存储和 embedding 是否正常工作
        
        返回:
            dict: {
                "available": bool,         # 集合是否已初始化
                "mode": str,               # persistent / remote / unavailable
                "total_vectors": int,      # 向量总数
                "embedding_ok": bool|None, # embedding 函数是否正常 (None=无数据无法验证)
                "embedding_error": str|None, # embedding 错误信息
            }
        """
        if not self.is_available:
            return {"available": False, "mode": self._mode,
                    "total_vectors": 0, "embedding_ok": False,
                    "embedding_error": "collection not initialized"}

        result = {
            "available": True,
            "mode": self._mode,
            "total_vectors": self._collection.count(),
        }

        # 如果有向量数据，执行测试查询验证 embedding 函数可用
        if result["total_vectors"] > 0:
            try:
                test_result = self._collection.query(
                    query_texts=["健康检查测试"],
                    n_results=1,
                )
                has_ids = bool(test_result.get("ids") and test_result["ids"][0])
                result["embedding_ok"] = has_ids
                if not has_ids:
                    result["embedding_error"] = "query returned no results"
            except Exception as e:
                result["embedding_ok"] = False
                result["embedding_error"] = str(e)[:200]
        else:
            result["embedding_ok"] = None  # 无数据，无法验证

        return result

    def get_collection_stats(self) -> dict:
        """获取集合统计"""
        if not self.is_available:
            return {"available": False}
        count = self._collection.count()
        return {
            "available": True,
            "mode": self._mode,
            "collection_name": self.collection_name,
            "total_vectors": count,
        }

    def delete_collection(self):
        """重置集合"""
        if not self.is_available:
            return
        try:
            self._client.delete_collection(self.collection_name)
        except Exception:
            pass
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"description": f"szpeter2026 知识库向量存储 ({self._mode})"},
        )
