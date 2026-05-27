"""
szpeter2026 知识库 - 统一配置中心
吸收自 Wukong 项目的配置管理模式，支持 .env + 默认值
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 加载 .env
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Config:
    """全局配置"""

    # ===== 项目路径 =====
    PROJECT_ROOT: Path = PROJECT_ROOT
    DB_DIR: Path = PROJECT_ROOT / "db"
    KB_DIR: Path = PROJECT_ROOT / "knowledge_base"
    DOCS_DIR: Path = KB_DIR / "documents"
    CHUNKS_DIR: Path = KB_DIR / "chunks"
    TEMPLATES_DIR: Path = PROJECT_ROOT / "templates"
    STATIC_DIR: Path = PROJECT_ROOT / "static"
    SCRIPTS_DIR: Path = PROJECT_ROOT / "scripts"

    # ===== 元数据库 =====
    METADATA_DB: str = str(DB_DIR / "szpeter2026.db")

    # ===== AI 配置 =====
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "deepseek")
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen2:latest")

    # ===== 向量数据库 =====
    # 模式: "auto"(默认,优先远程→回退本地) / "persistent"(仅本地文件) / "remote"(仅Docker服务)
    CHROMA_MODE: str = os.getenv("CHROMA_MODE", "auto")
    CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
    CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "szpeter2026_kb")

    # ===== pgvector 向量数据库（可选） =====
    PGVECTOR_ENABLED: bool = os.getenv("PGVECTOR_ENABLED", "false").lower() == "true"
    PGVECTOR_HOST: str = os.getenv("PGVECTOR_HOST", "localhost")
    PGVECTOR_PORT: int = int(os.getenv("PGVECTOR_PORT", "5432"))
    PGVECTOR_USER: str = os.getenv("PGVECTOR_USER", "szpeter")
    PGVECTOR_PASSWORD: str = os.getenv("PGVECTOR_PASSWORD", "Szpeter2026!")
    PGVECTOR_DATABASE: str = os.getenv("PGVECTOR_DATABASE", "szpeter2026")
    PGVECTOR_EMBEDDING_DIM: int = int(os.getenv("PGVECTOR_EMBEDDING_DIM", "768"))

    # ===== Ollama Embedding 模型 =====
    OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text:latest")

    # ===== Web 配置 =====
    WEB_HOST: str = os.getenv("WEB_HOST", "127.0.0.1")
    WEB_PORT: int = int(os.getenv("WEB_PORT", "5200"))
    WEB_DEBUG: bool = os.getenv("WEB_DEBUG", "false").lower() == "true"

    # ===== 文档处理 =====
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "1000"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "200"))

    # ===== Notion 集成 =====
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

    # ===== Gitea Webhook =====
    GITEA_WEBHOOK_SECRET: str = os.getenv("GITEA_WEBHOOK_SECRET", "")
    GITEA_BASE_URL: str = os.getenv("GITEA_BASE_URL", "")

    # ===== Outlook / Microsoft Graph OAuth2 =====
    OUTLOOK_CLIENT_ID: str = os.getenv("OUTLOOK_CLIENT_ID", "")
    OUTLOOK_CLIENT_SECRET: str = os.getenv("OUTLOOK_CLIENT_SECRET", "")
    OUTLOOK_REDIRECT_URI: str = os.getenv("OUTLOOK_REDIRECT_URI", "http://localhost:5200/auth/outlook/callback")
    OUTLOOK_TOKEN_PATH: str = str(DB_DIR / "outlook_tokens.json")

    # ===== 外部数据库（可选） =====
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "")
    PG_HOST: str = os.getenv("PG_HOST", "")
    PG_PORT: int = int(os.getenv("PG_PORT", "5432"))
    PG_USER: str = os.getenv("PG_USER", "")
    PG_PASSWORD: str = os.getenv("PG_PASSWORD", "")
    PG_DATABASE: str = os.getenv("PG_DATABASE", "")

    def __repr__(self) -> str:
        return f"<Config provider={self.AI_PROVIDER}, web={self.WEB_HOST}:{self.WEB_PORT}>"


# 单例
config = Config()
