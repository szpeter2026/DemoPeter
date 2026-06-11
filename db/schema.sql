-- szpeter2026 数据库 Schema
-- 包含: 元数据表 + D 盘扫描断点表

-- =============================================
-- 1. 元数据库（文档 + 分块 + 查询日志）
-- =============================================

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    file_path TEXT NOT NULL UNIQUE,
    doc_type TEXT NOT NULL,          -- md / pdf / txt
    file_size INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',      -- JSON: 作者、标签、分类等
    status TEXT DEFAULT 'pending',   -- pending / processing / completed / failed
    chunk_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    char_count INTEGER DEFAULT 0,
    metadata TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS query_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT NOT NULL,
    provider TEXT NOT NULL,
    response_time_ms REAL DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_query_logs_time ON query_logs(created_at);


-- =============================================
-- 2. D 盘扫描断点（断点续传机制）
-- =============================================

-- 每个项目根目录一条记录，追踪扫描进度
CREATE TABLE IF NOT EXISTS scan_checkpoints (
    project_root    TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | in_progress | completed | failed
    completed_dirs  TEXT DEFAULT '[]',                 -- JSON 数组，已完整处理过的目录
    current_dir     TEXT,                              -- 当前正在处理的目录
    current_file    TEXT,                              -- 当前正在处理的文件
    files_scanned   INTEGER DEFAULT 0,
    files_indexed   INTEGER DEFAULT 0,                 -- 实际写入 Chroma 的文件数
    chunks_indexed  INTEGER DEFAULT 0,
    started_at      TEXT,
    updated_at      TEXT,
    completed_at    TEXT,
    error_message   TEXT
);

-- 本地文件索引缓存（避免每次扫描都查 ChromaDB）
-- 匹配规则: path + size + mtime 三者全等 → 跳过读取和索引
CREATE TABLE IF NOT EXISTS indexed_files_cache (
    file_path       TEXT PRIMARY KEY,
    project_root    TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    last_modified   REAL NOT NULL,
    fingerprint     TEXT NOT NULL,
    chunks_count    INTEGER DEFAULT 0,
    indexed_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ifc_project ON indexed_files_cache(project_root);
CREATE INDEX IF NOT EXISTS idx_ifc_path_size_mtime ON indexed_files_cache(file_path, size_bytes, last_modified);
