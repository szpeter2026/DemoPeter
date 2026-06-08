"""
Chronicle — 史料记录员模块
自动归档 WorkBuddy 对话/操作事件 → Chroma 向量化 → 语义可检索

Collection: chronicle
数据流: 事件 → schema 结构化 → Ollama embedding → Chroma 写入
"""
from .schema import ChronicleEvent, EventType, ProjectTag
from .ingest import ChronicleIngest
from .retrieve import ChronicleRetrieve

__all__ = [
    "ChronicleEvent",
    "EventType",
    "ProjectTag",
    "ChronicleIngest",
    "ChronicleRetrieve",
]
