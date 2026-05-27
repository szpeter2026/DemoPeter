"""
szpeter2026 - 文档处理管道
吸收自 HKIE/Wukong 的文档处理模式：PDF/MD/TXT → 文本提取 → 智能分块
"""
import re
import json
from pathlib import Path
from typing import Iterator

from config.settings import config


class DocumentProcessor:
    """文档处理管道 — 导入 → 提取 → 分块"""

    SUPPORTED_TYPES = {".md", ".pdf", ".txt", ".markdown"}

    def __init__(self):
        self.chunk_size = config.CHUNK_SIZE
        self.chunk_overlap = config.CHUNK_OVERLAP

    # ===== 文本提取 =====

    @staticmethod
    def extract_text(file_path: str | Path) -> str:
        """从文件提取文本内容"""
        file_path = Path(file_path)
        suffix = file_path.suffix.lower()

        if suffix in (".md", ".markdown"):
            return file_path.read_text(encoding="utf-8")
        elif suffix == ".txt":
            # 尝试多种编码
            for enc in ["utf-8", "gbk", "gb2312", "latin-1"]:
                try:
                    return file_path.read_text(encoding=enc)
                except (UnicodeDecodeError, UnicodeError):
                    continue
            return file_path.read_text(encoding="utf-8", errors="replace")
        elif suffix == ".pdf":
            return DocumentProcessor._extract_pdf(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {suffix}")

    @staticmethod
    def _extract_pdf(file_path: Path) -> str:
        """PDF 文本提取 — 优先使用 pdfplumber，回退 pypdf"""
        text_parts = []
        try:
            import pdfplumber
            with pdfplumber.open(str(file_path)) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text_parts.append(t)
            if text_parts:
                return "\n\n".join(text_parts)
        except ImportError:
            pass

        # 回退到 pypdf
        from pypdf import PdfReader
        reader = PdfReader(str(file_path))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text_parts.append(t)
        return "\n\n".join(text_parts)

    # ===== 智能分块 =====

    def chunk_text(self, text: str, metadata: dict | None = None) -> list[dict]:
        """将文本智能分块，保留段落/章节边界"""
        meta = metadata or {}
        chunks = []
        paragraphs = self._split_by_structure(text)

        current_chunk = ""
        for para in paragraphs:
            if not para.strip():
                continue

            if len(current_chunk) + len(para) <= self.chunk_size:
                current_chunk += para + "\n\n"
            else:
                # 保存当前块
                if current_chunk.strip():
                    chunks.append({
                        "index": len(chunks),
                        "content": current_chunk.strip(),
                        "metadata": {**meta, "char_count": len(current_chunk.strip())}
                    })
                # 开始新块（带重叠）
                overlap_text = current_chunk[-self.chunk_overlap:] if self.chunk_overlap and current_chunk else ""
                current_chunk = overlap_text + para + "\n\n"

        # 最后一个块
        if current_chunk.strip():
            chunks.append({
                "index": len(chunks),
                "content": current_chunk.strip(),
                "metadata": {**meta, "char_count": len(current_chunk.strip())}
            })

        return chunks

    @staticmethod
    def _split_by_structure(text: str) -> list[str]:
        """按 Markdown 标题和自然段落分割"""
        # 先按 Markdown 标题分割
        sections = re.split(r'(?=^#{1,6}\s)', text, flags=re.MULTILINE)
        result = []
        for section in sections:
            # 再在内部按双换行分割
            paras = re.split(r'\n\s*\n', section)
            result.extend(paras)
        return result

    # ===== 批量导入 =====

    def scan_directory(self, directory: str | Path) -> list[dict]:
        """扫描目录下所有可处理的文件"""
        directory = Path(directory)
        files = []
        for file_path in directory.rglob("*"):
            if file_path.suffix.lower() in self.SUPPORTED_TYPES:
                files.append({
                    "title": file_path.stem,
                    "file_path": str(file_path.resolve()),
                    "doc_type": file_path.suffix.lower().lstrip("."),
                    "file_size": file_path.stat().st_size,
                })
        return files

    def process_file(self, file_path: str | Path) -> tuple[str, list[dict]]:
        """处理单个文件：提取文本 + 分块"""
        text = self.extract_text(file_path)
        file_path = Path(file_path)
        chunks = self.chunk_text(text, metadata={
            "source_file": file_path.name,
            "source_path": str(file_path.parent),
            "doc_type": file_path.suffix.lower().lstrip("."),
        })
        return text, chunks
