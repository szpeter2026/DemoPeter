"""
DScanner - D 盘文件扫描器

遍历预设的项目根目录，发现可索引的文本文件，
跳过二进制/大文件/构建产物，将内容切分为 chunk。
"""
import os
import hashlib
from pathlib import Path
from dataclasses import dataclass, field
from typing import Iterator
from datetime import datetime


# === 可索引的文件扩展名 ===
INDEXABLE_EXTENSIONS = {
    # Python
    ".py", ".pyw",
    # JavaScript / TypeScript
    ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    # Rust
    ".rs",
    # Go
    ".go",
    # PHP
    ".php", ".phtml",
    # Java
    ".java",
    # C / C++
    ".c", ".cpp", ".h", ".hpp",
    # Web
    ".html", ".htm", ".css", ".scss", ".less",
    # Config / Data
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml", ".env", ".properties",
    # Docs
    ".md", ".txt", ".rst", ".tex", ".adoc",
    # Shell
    ".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd",
    # Other text
    ".sql", ".graphql", ".proto", ".api",
    ".gitignore", ".dockerignore", ".editorconfig",
    # Lock files (small, useful for version info)
    ".lock",
}

# === 跳过的目录名 ===
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    "target", "dist", "build", ".next", ".nuxt", "out",
    "data", "chroma_data", "chroma_docker", "db", "pgdata",
    "logs", ".cache", ".pytest_cache", ".mypy_cache", ".tox",
    "vendor", "bower_components", "coverage",
    "wp-content/uploads",  # WordPress uploads (images)
    "backup_*",  # Mac 备份压缩包
}

# === 最大文件大小 (字节) ===
MAX_FILE_SIZE = 50 * 1024  # 50KB

# === 分块参数 ===
CHUNK_SIZE = 1000   # 字符
CHUNK_OVERLAP = 200


@dataclass
class ScanConfig:
    """扫描配置"""
    project_roots: list[str] = field(default_factory=list)
    indexable_extensions: set[str] = field(default_factory=lambda: INDEXABLE_EXTENSIONS)
    skip_dirs: set[str] = field(default_factory=lambda: SKIP_DIRS)
    max_file_size: int = MAX_FILE_SIZE
    chunk_size: int = CHUNK_SIZE
    chunk_overlap: int = CHUNK_OVERLAP


@dataclass
class ScannedFile:
    """扫描到的文件"""
    file_path: str
    project_root: str
    file_type: str  # 扩展名，如 ".py"
    size_bytes: int
    last_modified: float  # timestamp
    fingerprint: str  # 内容 hash，用于去重
    content: str = ""  # 文件全文（读取后填充）


@dataclass
class Chunk:
    """文本分块"""
    chunk_id: str       # {fingerprint}_chunk_{i}
    file_path: str
    project_name: str   # 项目根目录名
    file_type: str
    content: str
    chunk_index: int
    total_chunks: int
    last_modified: float
    metadata: dict = field(default_factory=dict)


class DScanner:
    """D 盘文件扫描器"""

    def __init__(self, config: ScanConfig = None):
        self.config = config or ScanConfig()

    def scan(self) -> Iterator[ScannedFile]:
        """遍历所有项目目录，产出可索引的文件"""
        for root in self.config.project_roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            yield from self._scan_dir(root_path, root)

    def _scan_dir(self, root_path: Path, project_root: str) -> Iterator[ScannedFile]:
        """递归扫描单个目录"""
        for dirpath, dirnames, filenames in os.walk(root_path):
            # 跳过黑名单目录
            dirnames_copy = dirnames[:]
            for d in dirnames_copy:
                if d in self.config.skip_dirs:
                    dirnames.remove(d)
                elif any(d.startswith(p.replace("*", "")) for p in self.config.skip_dirs if "*" in p):
                    dirnames.remove(d)

            current_dir = Path(dirpath)
            for fname in filenames:
                file_path = current_dir / fname
                ext = file_path.suffix.lower()

                if ext not in self.config.indexable_extensions:
                    continue

                try:
                    stat = file_path.stat()
                except OSError:
                    continue

                if stat.st_size > self.config.max_file_size:
                    continue

                if stat.st_size == 0:
                    continue

                file_type = ext[1:] if ext.startswith(".") else ext  # 去掉点

                yield ScannedFile(
                    file_path=str(file_path),
                    project_root=project_root,
                    file_type=file_type,
                    size_bytes=stat.st_size,
                    last_modified=stat.st_mtime,
                    fingerprint="",  # 读取后计算
                )

    def read_and_fingerprint(self, sf: ScannedFile) -> ScannedFile:
        """读取文件内容并计算指纹"""
        try:
            with open(sf.file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            content = ""

        sf.content = content
        sf.fingerprint = hashlib.md5(content.encode("utf-8")).hexdigest()
        return sf

    def chunk_file(self, sf: ScannedFile) -> list[Chunk]:
        """将单个文件切分为多个 chunk"""
        if not sf.content:
            return []

        content = sf.content
        project_name = Path(sf.project_root).name
        chunks = []

        # 短文本不需要切分
        if len(content) <= self.config.chunk_size:
            chunk = Chunk(
                chunk_id=f"{sf.fingerprint}_chunk_0",
                file_path=sf.file_path,
                project_name=project_name,
                file_type=sf.file_type,
                content=content,
                chunk_index=0,
                total_chunks=1,
                last_modified=sf.last_modified,
                metadata={
                    "size": sf.size_bytes,
                    "path": sf.file_path,
                    "project_root": sf.project_root,
                },
            )
            chunks.append(chunk)
        else:
            # 滑动窗口切分
            step = self.config.chunk_size - self.config.chunk_overlap
            total = max(1, (len(content) - self.config.chunk_overlap + step - 1) // step)

            for i in range(total):
                start = i * step
                end = start + self.config.chunk_size
                chunk_text = content[start:end]

                chunk = Chunk(
                    chunk_id=f"{sf.fingerprint}_chunk_{i}",
                    file_path=sf.file_path,
                    project_name=project_name,
                    file_type=sf.file_type,
                    content=chunk_text,
                    chunk_index=i,
                    total_chunks=total,
                    last_modified=sf.last_modified,
                    metadata={
                        "size": sf.size_bytes,
                        "path": sf.file_path,
                        "project_root": sf.project_root,
                    },
                )
                chunks.append(chunk)

        return chunks

    def get_stats(self) -> dict:
        """估算扫描范围统计"""
        total_files = 0
        total_size = 0
        projects_found = 0

        for root in self.config.project_roots:
            root_path = Path(root)
            if not root_path.exists():
                continue
            projects_found += 1
            for sf in self.scan_for_stats(root):
                total_files += 1
                total_size += sf.size_bytes

        return {
            "project_roots_configured": len(self.config.project_roots),
            "project_roots_accessible": projects_found,
            "indexable_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
        }

    def scan_for_stats(self, root: str) -> Iterator[ScannedFile]:
        """快速统计（不读内容）"""
        return self._scan_dir(Path(root), root)
