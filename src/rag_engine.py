"""
szpeter2026 - RAG 检索引擎
吸收自 72changes RAGService，实现检索增强生成
支持 Chroma + pgvector 双向量后端
"""
import time
from dataclasses import dataclass, field

from src.ai_client import AIClient
from src.vector_store import VectorStore
from src.db_manager import DBManager
from src.pgvector_store import PgvectorStore


@dataclass
class RAGResult:
    """RAG 查询结果"""
    query: str
    answer: str
    sources: list[dict] = field(default_factory=list)
    response_time_ms: float = 0
    chunk_count: int = 0


# RAG 提示词模板
RAG_PROMPT_TEMPLATE = """你是一个智能知识库助手，请根据以下参考资料回答用户的问题。

## 规则
1. 优先使用参考资料中的信息回答
2. 如果参考资料不足以回答问题，请诚实说明
3. 回答要简洁、准确、有条理
4. 引用资料时注明来源

## 参考资料
{context}

## 用户问题
{query}

## 回答"""


class RAGEngine:
    """RAG 检索引擎 — 检索 → 增强 → 生成
    检索优先级: Chroma → pgvector → 纯 AI
    """

    def __init__(self):
        self.ai = AIClient()
        self.vector_store = VectorStore()
        self.pgvector_store = PgvectorStore()
        self.db = DBManager()

    def _search(self, query_text: str, top_k: int = 5,
                threshold: float = 0.5) -> list[dict]:
        """多源检索：Chroma → pgvector → SQLite 关键词 依次尝试"""
        # 1. Chroma 语义搜索
        if self.vector_store.is_available:
            hits = self.vector_store.search(query_text, top_k=top_k, threshold=threshold)
            if hits:
                return hits
        # 2. pgvector 语义搜索
        if self.pgvector_store.is_available:
            return self.pgvector_store.search(query_text, top_k=top_k, threshold=threshold)
        # 3. SQLite 关键词检索（兜底，确保始终能从知识库召回内容）
        return self.db.search_chunks(query_text, top_k=top_k)

    def query(self, query_text: str, top_k: int = 5,
              threshold: float = 0.5) -> RAGResult:
        """执行 RAG 查询"""
        start = time.time()

        # 1. 检索
        hits = self._search(query_text, top_k=top_k, threshold=threshold)
        chunk_count = len(hits)

        if not hits:
            # 所有检索方式均无结果，告知用户
            answer = "知识库中暂未找到与您问题相关的资料，请尝试更换关键词或导入更多文档。"
            elapsed_ms = (time.time() - start) * 1000
            self.db.log_query(query_text, self.ai.provider, elapsed_ms, 0)
            return RAGResult(
                query=query_text,
                answer=answer,
                sources=[],
                response_time_ms=round(elapsed_ms, 2),
                chunk_count=0,
            )
        else:
            # 2. 增强：构建上下文
            context_parts = []
            for i, hit in enumerate(hits):
                src = hit["metadata"].get("source_file", "未知来源")
                context_parts.append(f"[来源 {i + 1}: {src}]\n{hit['content']}")
            context = "\n\n---\n\n".join(context_parts)

            # 3. 生成
            messages = [
                {"role": "system", "content": RAG_PROMPT_TEMPLATE.format(
                    context=context, query=query_text
                )},
            ]

        answer, _ = self.ai.chat(messages)
        elapsed_ms = (time.time() - start) * 1000

        # 记录日志
        self.db.log_query(query_text, self.ai.provider, elapsed_ms, chunk_count)

        return RAGResult(
            query=query_text,
            answer=answer,
            sources=[{
                "content": h["content"][:300],
                "source": h["metadata"].get("source_file", ""),
                "similarity": h["similarity"],
            } for h in hits],
            response_time_ms=round(elapsed_ms, 2),
            chunk_count=chunk_count,
        )

    def query_stream(self, query_text: str, top_k: int = 5,
                     threshold: float = 0.5) -> tuple:
        """流式 RAG 查询，返回 (生成器, context)"""
        hits = self._search(query_text, top_k=top_k, threshold=threshold)

        if not hits:
            # 所有检索方式均无结果
            def _empty():
                yield "知识库中暂未找到与您问题相关的资料，请尝试更换关键词或导入更多文档。"
                yield 0.0
            return _empty(), []
        else:
            context_parts = [f"[来源 {i + 1}: {h['metadata'].get('source_file', '')}]\n{h['content']}"
                             for i, h in enumerate(hits)]
            context = "\n\n---\n\n".join(context_parts)
            messages = [{"role": "system", "content": RAG_PROMPT_TEMPLATE.format(
                context=context, query=query_text)}]

        return self.ai.chat_stream(messages), hits

    @property
    def is_vector_available(self) -> bool:
        return self.vector_store.is_available
