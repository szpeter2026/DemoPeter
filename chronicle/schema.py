"""
Chronicle Schema — 事件数据结构定义

每条记录 = {
    "id": "uuid",
    "timestamp": "ISO 8601",
    "event_type": "决策 | 操作 | 发现 | 配置 | 对话",
    "project": "Nezha | SurfaceZervi | DemoPeter | WorkBuddy | ...",
    "title": "一句话摘要",
    "summary": "2-3 句描述",
    "tags": ["知识管理", "架构"],
    "participants": ["嘟嘟", "Peter"],
    "related_events": ["prev_event_id"],
    "full_text": "完整上下文...",
    "source": "workbuddy_session | manual | import",
    "metadata": { 任意扩展 },
}
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field, asdict
import uuid


class EventType(str, Enum):
    DECISION = "决策"       # 做出技术/架构/方向决定
    ACTION = "操作"         # 执行了具体操作（部署、迁移、安装等）
    DISCOVERY = "发现"      # 发现了问题、规律或新信息
    CONFIG = "配置"         # 修改了系统/项目配置
    CONVERSATION = "对话"   # 常规讨论，值得记录


class ProjectTag(str, Enum):
    NEZHA = "Nezha"
    DEMOPETER = "DemoPeter"
    SURFACEZERVI = "SurfaceZervi"
    WORKBUDDY = "WorkBuddy"
    DEMOPPI = "DemoPPI"
    TATHA = "Tatha"
    GITEA = "Gitea"
    SYSTEM = "System"  # 系统级操作（D盘清理等）


@dataclass
class ChronicleEvent:
    """一条史料事件"""

    title: str                          # 一句话标题
    event_type: EventType               # 事件类型
    full_text: str                      # 完整上下文
    project: ProjectTag = ProjectTag.WORKBUDDY
    summary: str = ""
    tags: list[str] = field(default_factory=list)
    participants: list[str] = field(default_factory=lambda: ["嘟嘟", "Peter"])
    related_events: list[str] = field(default_factory=list)
    source: str = "workbuddy_session"
    metadata: dict = field(default_factory=dict)

    # 自动生成
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value if isinstance(self.event_type, EventType) else self.event_type
        d["project"] = self.project.value if isinstance(self.project, ProjectTag) else self.project
        return d

    @property
    def chroma_text(self) -> str:
        """生成用于 Chroma embedding 的文本"""
        return (
            f"事件: {self.title}\n"
            f"类型: {self.event_type.value}\n"
            f"项目: {self.project.value}\n"
            f"时间: {self.timestamp}\n"
            f"标签: {', '.join(self.tags)}\n"
            f"参与者: {', '.join(self.participants)}\n"
            f"摘要: {self.summary}\n"
            f"详情:\n{self.full_text}"
        )

    @property
    def chroma_metadata(self) -> dict:
        return {
            "event_type": self.event_type.value,
            "project": self.project.value,
            "title": self.title,
            "tags": ",".join(self.tags),
            "participants": ",".join(self.participants),
            "source": self.source,
            "related_events": ",".join(self.related_events),
            "timestamp": self.timestamp,
        }
