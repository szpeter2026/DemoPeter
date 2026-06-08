"""
d_indexer - D 盘自动扫描索引模块

定期扫描 D 盘项目目录，提取文本内容，向量化存入 Chroma，
支持语义搜索"那个做跨境电商的项目在哪"。

三层架构：
- scanner: 文件扫描 + 文本提取
- indexer: Chroma 嵌入 + 存储
- scheduler: 每日定时触发
"""
from .scanner import DScanner, ScanConfig
from .indexer import DIndexer, SearchResult
from .scheduler import DScheduler

__all__ = [
    "DScanner", "ScanConfig",
    "DIndexer", "SearchResult",
    "DScheduler",
]
