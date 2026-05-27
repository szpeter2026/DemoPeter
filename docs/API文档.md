# szpeter2026 知识库 API 文档

Base URL: `http://127.0.0.1:5200`

## 统计

### GET /api/stats

获取知识库统计信息。

**响应：**
```json
{
    "documents_total": 42,
    "documents_completed": 38,
    "documents_pending": 4,
    "chunks_total": 1560,
    "total_characters": 1250000,
    "queries_total": 230,
    "vector": {
        "available": true,
        "collection_name": "szpeter2026_kb",
        "total_vectors": 1560
    },
    "ai_provider": "deepseek"
}
```

## 文档管理

### GET /api/documents

获取文档列表。

参数：`?status=completed`（可选：completed/pending/failed）

### GET /api/documents/:id

获取文档详情（含分块）。

### POST /api/documents/import

批量导入文档。

**请求体：**
```json
{
    "directory": "E:\\szpeter2026\\knowledge_base\\documents"
}
```

### DELETE /api/documents/:id

删除文档及其所有分块和向量数据。

## RAG 问答

### POST /api/rag/query

RAG 问答（同步）。

**请求体：**
```json
{
    "query": "你的问题",
    "top_k": 5,
    "threshold": 0.5
}
```

**响应：**
```json
{
    "query": "你的问题",
    "answer": "回答内容...",
    "sources": [
        {
            "content": "相关内容片段...",
            "source": "document.md",
            "similarity": 0.85
        }
    ],
    "response_time_ms": 1250.5,
    "chunk_count": 3
}
```

### GET /api/rag/stream

流式 RAG 问答（SSE）。

参数：`?query=你的问题&top_k=5&threshold=0.5`

**SSE 事件：**
```
data: {"type":"sources","data":[...]}

data: {"type":"text","content":"回"}

data: {"type":"text","content":"答"}

data: {"type":"done","time_ms":1250.5}
```

## 报告

### POST /api/reports/generate

生成报告。

**请求体：**
```json
{
    "type": "daily"
}
```

`type` 可选：daily / weekly / monthly

### GET /api/reports/queries

获取查询历史。

参数：`?limit=50`

## 系统

### GET /api/system/check

系统健康检查。

**响应：**
```json
{
    "status": "ok",
    "ai_provider": "deepseek",
    "chroma_available": true,
    "db_path": "E:\\szpeter2026\\db\\szpeter2026.db"
}
```
