"""
DIndexer - D 盘文件 Chroma 索引器

将扫描器产出的 chunk 写入 Chroma 向量库，
支持去重（同文件同内容不重复索引）和语义搜索。
"""
import os
import time
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional

from .scanner import DScanner, ScanConfig, Chunk
from config.settings import config as app_config
from config.logging_config import get_logger

logger = get_logger("d_indexer")


# D 盘索引专用 Collection
INDEX_COLLECTION = "d_drive_index"


@dataclass
class SearchResult:
    """搜索结果"""
    chunk_id: str
    file_path: str
    project_name: str
    content: str
    file_type: str
    similarity: float
    last_modified: str


@dataclass
class IndexStats:
    """索引统计"""
    collection_name: str
    total_chunks: int
    total_files: int
    last_scan_time: str = ""
    scan_duration_seconds: float = 0
    new_chunks: int = 0
    skipped_chunks: int = 0


class DIndexer:
    """D 盘文件 Chroma 索引器"""

    def __init__(self, scanner: DScanner = None, persist_dir: str = None):
        self.scanner = scanner or DScanner()
        self.persist_dir = persist_dir or app_config.CHROMA_PERSIST_DIR
        self._client = None
        self._collection = None
        self._mode = "unavailable"
        self._init_chroma()

    def _init_chroma(self):
        """初始化 Chroma PersistentClient"""
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            try:
                embedding_fn = embedding_functions.DefaultEmbeddingFunction()
            except Exception as e:
                logger.error("Embedding 加载失败: %s", e)
                return

            os.makedirs(self.persist_dir, exist_ok=True)
            self._client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = self._client.get_or_create_collection(
                name=INDEX_COLLECTION,
                embedding_function=embedding_fn,
                metadata={
                    "description": "D: drive project file index",
                    "hnsw:space": "cosine",
                },
            )
            self._mode = "persistent"
            logger.info("Chroma 已连接 collection=%s path=%s", INDEX_COLLECTION, self.persist_dir)
        except Exception as e:
            logger.error("Chroma 初始化失败: %s", e)
            self._client = None
            self._collection = None
            self._mode = "unavailable"

    @property
    def is_available(self) -> bool:
        return self._collection is not None

    @property
    def count(self) -> int:
        if not self.is_available:
            return 0
        return self._collection.count()

    # 批量 upsert 大小
    BATCH_SIZE = 200

    def index_all(self) -> IndexStats:
        """全量扫描并索引（首次运行或强制刷新）"""
        stats = IndexStats(
            collection_name=INDEX_COLLECTION,
            total_chunks=0,
            total_files=0,
        )
        start_time = time.time()
        scanned_files = set()
        batch_chunks: list = []  # 批量缓冲区

        for sf in self.scanner.scan():
            sf = self.scanner.read_and_fingerprint(sf)
            chunks = self.scanner.chunk_file(sf)
            scanned_files.add(sf.file_path)
            batch_chunks.extend(chunks)
            stats.total_chunks += len(chunks)

            # 进度输出（每 50 个文件）
            if len(scanned_files) % 50 == 0:
                elapsed = time.time() - start_time
                logger.info("已处理 %d 文件 (%d chunks, %.0fs)...",
                           len(scanned_files), stats.total_chunks, elapsed)

            # 批量写入
            if len(batch_chunks) >= self.BATCH_SIZE:
                n = self._batch_upsert(batch_chunks)
                stats.new_chunks += n
                stats.skipped_chunks += len(batch_chunks) - n
                batch_chunks = []

        # 写入剩余
        if batch_chunks:
            n = self._batch_upsert(batch_chunks)
            stats.new_chunks += n
            stats.skipped_chunks += len(batch_chunks) - n

        stats.total_files = len(scanned_files)
        stats.scan_duration_seconds = round(time.time() - start_time, 2)
        stats.last_scan_time = datetime.now().isoformat()

        logger.info("全量索引完成: %d 文件 %d chunks 耗时 %.1fs",
                    stats.total_files, stats.new_chunks, stats.scan_duration_seconds)
        return stats

    def incremental_scan(self) -> IndexStats:
        """增量扫描：只索引变更的文件"""
        stats = IndexStats(
            collection_name=INDEX_COLLECTION,
            total_chunks=0,
            total_files=0,
        )
        start_time = time.time()
        scanned_files = 0
        batch_chunks: list = []

        for sf in self.scanner.scan():
            sf = self.scanner.read_and_fingerprint(sf)
            scanned_files += 1

            # 检查是否需要更新（使用文件路径+修改时间）
            if not self._needs_update_by_mtime(sf):
                stats.skipped_chunks += 1
                continue

            # 先删除旧 chunk
            self._delete_by_path(sf.file_path)

            chunks = self.scanner.chunk_file(sf)
            batch_chunks.extend(chunks)
            stats.total_chunks += len(chunks)

            if scanned_files % 50 == 0:
                elapsed = time.time() - start_time
                logger.info("增量扫描: 已处理 %d 文件 (%d chunks, %.0fs)...",
                           scanned_files, stats.total_chunks, elapsed)

            if len(batch_chunks) >= self.BATCH_SIZE:
                n = self._batch_upsert(batch_chunks)
                stats.new_chunks += n
                batch_chunks = []

        if batch_chunks:
            n = self._batch_upsert(batch_chunks)
            stats.new_chunks += n

        stats.total_files = scanned_files
        stats.scan_duration_seconds = round(time.time() - start_time, 2)
        stats.last_scan_time = datetime.now().isoformat()
        return stats

    def _batch_upsert(self, chunks: list) -> int:
        """批量写入 chunk 到 Chroma（一次性 embedding 计算）"""
        if not self.is_available or not chunks:
            return 0
        try:
            ids = [c.chunk_id for c in chunks]
            documents = [c.content for c in chunks]
            metadatas = [{
                "file_path": c.file_path,
                "project_name": c.project_name,
                "file_type": c.file_type,
                "chunk_index": c.chunk_index,
                "total_chunks": c.total_chunks,
                "last_modified": c.last_modified,
            } for c in chunks]

            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )
            return len(chunks)
        except Exception as e:
            logger.error("批量 upsert 失败: %s", e)
            return 0

    def _needs_update_by_mtime(self, sf) -> bool:
        """检查文件是否需要重新索引（基于路径+修改时间）"""
        if not self.is_available:
            return True
        try:
            results = self._collection.get(
                where={"file_path": sf.file_path},
                include=["metadatas"],
            )
            if not results["ids"]:
                return True
            # 检查是否有不同的修改时间
            for meta in results.get("metadatas", []):
                if meta.get("last_modified") != sf.last_modified:
                    return True
            return False
        except Exception:
            return True

    def _needs_update(self, sf) -> bool:
        """检查文件是否需要重新索引"""
        if not self.is_available:
            return True
        try:
            results = self._collection.get(
                ids=[f"{sf.fingerprint}_chunk_0"],
            )
            return len(results["ids"]) == 0
        except Exception:
            return True

    def _delete_by_path(self, file_path: str):
        """删除某个文件的所有 chunk"""
        if not self.is_available:
            return
        try:
            self._collection.delete(where={"file_path": file_path})
        except Exception:
            pass

    def search(self, query: str, top_k: int = 10,
               project_filter: str = None,
               file_type_filter: str = None) -> list[SearchResult]:
        """语义搜索 D 盘文件内容"""
        if not self.is_available:
            return []

        where = {}
        if project_filter:
            where["project_name"] = project_filter
        if file_type_filter:
            where["file_type"] = file_type_filter
        if not where:
            where = None

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error("搜索失败: %s", e)
            return []

        hits = []
        if results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                distance = results.get("distances", [[1.0]])[0][i]
                similarity = max(0.0, min(1.0, 1.0 - distance / 2.0))

                last_mod = datetime.fromtimestamp(
                    metadata.get("last_modified", 0)
                ).strftime("%Y-%m-%d %H:%M")

                hits.append(SearchResult(
                    chunk_id=results["ids"][0][i],
                    file_path=metadata.get("file_path", ""),
                    project_name=metadata.get("project_name", ""),
                    content=results["documents"][0][i][:300] if results.get("documents") else "",
                    file_type=metadata.get("file_type", ""),
                    similarity=round(similarity, 4),
                    last_modified=last_mod,
                ))

        return hits

    def list_projects(self) -> list[dict]:
        """列出已索引的项目及文件数"""
        if not self.is_available:
            return []
        project_counts = {}
        # 遍历所有元数据统计
        try:
            all_data = self._collection.get(include=["metadatas"])
            for meta in all_data.get("metadatas", []):
                pn = meta.get("project_name", "unknown")
                if pn not in project_counts:
                    project_counts[pn] = {"files": set(), "types": set()}
                project_counts[pn]["files"].add(meta.get("file_path", ""))
                project_counts[pn]["types"].add(meta.get("file_type", ""))
        except Exception:
            return []

        result = []
        for name, data in sorted(project_counts.items()):
            result.append({
                "project": name,
                "files": len(data["files"]),
                "chunks": self._count_by_project(name),
                "file_types": sorted(data["types"]),
            })
        return result

    def _count_by_project(self, project_name: str) -> int:
        try:
            result = self._collection.get(
                where={"project_name": project_name},
                include=[],
            )
            return len(result.get("ids", []))
        except Exception:
            return 0

    def clear_index(self):
        """清空索引"""
        if not self.is_available:
            return
        try:
            self._client.delete_collection(INDEX_COLLECTION)
            self._init_chroma()
        except Exception:
            pass
