"""
szpeter2026 - Web 管理面板
吸收自 Wukong web_dashboard.py，提供知识库管理、RAG 问答、统计报表
"""
import sys
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_cors import CORS

from config.settings import config
from src.db_manager import DBManager
from src.doc_processor import DocumentProcessor
from src.vector_store import VectorStore
from src.pgvector_store import PgvectorStore
from src.rag_engine import RAGEngine
from src.ai_client import AIClient
from src.report_gen import ReportGenerator
from src.gitea_webhook import GiteaWebhookHandler
from src.outlook_client import OutlookClient

app = Flask(__name__, template_folder=str(config.TEMPLATES_DIR),
            static_folder=str(config.STATIC_DIR))
CORS(app)

db = DBManager()
processor = DocumentProcessor()
vector_store = VectorStore()
pgvector_store = PgvectorStore()
rag = RAGEngine()
reporter = ReportGenerator()
webhook_handler = GiteaWebhookHandler()


# ===== 页面路由 =====

@app.route("/")
def index():
    """主页 — 知识库仪表盘"""
    stats = db.get_stats()
    vec_stats = vector_store.get_collection_stats()
    pg_stats = pgvector_store.get_stats() if pgvector_store.is_available else {"available": False}
    return render_template("index.html", stats=stats, vec_stats=vec_stats,
                           pg_stats=pg_stats, ai_provider=config.AI_PROVIDER)


@app.route("/documents")
def documents_page():
    """文档管理页面"""
    return render_template("documents.html")


@app.route("/query")
def query_page():
    """RAG 问答页面"""
    ai_ok, ai_hint = AIClient.is_configured()
    return render_template(
        "query.html",
        ai_provider=config.AI_PROVIDER,
        ai_configured=ai_ok,
        ai_hint=ai_hint,
    )


@app.route("/reports")
def reports_page():
    """报告页面"""
    return render_template("reports.html")


# ===== API — 统计 =====

@app.route("/api/stats")
def api_stats():
    """获取知识库统计"""
    stats = db.get_stats()
    stats["chroma"] = vector_store.get_collection_stats()
    stats["pgvector"] = pgvector_store.get_stats() if pgvector_store.is_available else {"available": False}
    stats["ai_provider"] = config.AI_PROVIDER
    return jsonify(stats)


# ===== API — 文档管理 =====

@app.route("/api/documents")
def api_documents():
    """获取文档列表"""
    status = request.args.get("status")
    docs = db.get_documents(status=status)
    return jsonify(docs)


@app.route("/api/documents/<int:doc_id>")
def api_document(doc_id):
    """获取单个文档详情"""
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "文档不存在"}), 404
    chunks = db.get_chunks(doc_id)
    doc["chunks"] = chunks
    return jsonify(doc)


@app.route("/api/health/vector")
def api_vector_health():
    """向量存储健康检查 API"""
    health = vector_store.health_check()
    pg_available = pgvector_store.is_available
    return jsonify({
        "chroma": health,
        "pgvector": {"available": pg_available},
        "search_mode": config.SEARCH_MODE,
        "fallback_chain": [
            "Chroma 向量检索",
            "pgvector 向量检索 (备选)",
            "SQLite FTS5 关键词检索 (兜底)",
        ],
    })


@app.route("/api/documents/import", methods=["POST"])
def api_import_documents():
    """批量导入文档"""
    data = request.get_json() or {}
    raw_path = data.get("directory") or ""
    if raw_path:
        # 相对路径 → 基于项目根目录解析为绝对路径
        directory = str(Path(raw_path).resolve()
                        if Path(raw_path).is_absolute()
                        else (config.PROJECT_ROOT / raw_path).resolve())
    else:
        directory = str(config.DOCS_DIR)
    if not Path(directory).exists():
        return jsonify({"error": f"目录不存在: {directory}",
                        "details": [], "total": 0, "success": 0, "failed": 0}), 400

    # 扫描文件
    files = processor.scan_directory(directory)
    results = {"total": len(files), "success": 0, "failed": 0, "details": []}

    for file_info in files:
        try:
            # 检查是否已存在
            existing = db.get_documents()
            existing_paths = {d.get("file_path", "") for d in existing if isinstance(d, dict)}
            if file_info["file_path"] in existing_paths:
                results["details"].append({
                    "title": file_info["title"],
                    "status": "skipped",
                    "reason": "已存在",
                })
                continue

            # 注册文档
            doc_id = db.register_document(
                title=file_info["title"],
                file_path=file_info["file_path"],
                doc_type=file_info["doc_type"],
                file_size=file_info.get("file_size", 0),
            )

            # 提取文本并分块
            text, chunks = processor.process_file(file_info["file_path"])

            # 保存分块到元数据库
            db.save_chunks(doc_id, chunks)

            # 添加到向量库
            vector_write_ok = True
            if vector_store.is_available:
                added = vector_store.add_documents(str(doc_id), chunks)
                # 写入后验证：用第一条 chunk 内容做检索验证
                if added > 0 and chunks:
                    verify_query = chunks[0]["content"][:100]
                    verify_hits = vector_store.search(verify_query, top_k=1, threshold=0.0)
                    if verify_hits:
                        print(f"[Import] ✓ 向量写入验证通过: doc_id={doc_id}")
                    else:
                        vector_write_ok = False
                        print(f"[Import] ⚠️ 向量写入验证失败: doc_id={doc_id} 无法通过检索找回")

            if pgvector_store.is_available:
                pgvector_store.add_documents(doc_id, chunks)

            # 更新状态（标注向量写入状态）
            status = "completed" if vector_write_ok else "completed_no_vector"
            db.update_document_status(doc_id, status, len(chunks))
            results["success"] += 1
            results["details"].append({
                "title": file_info["title"],
                "doc_id": doc_id,
                "status": "completed",
                "chunks": len(chunks),
            })

        except Exception as e:
            results["failed"] += 1
            results["details"].append({
                "title": file_info["title"],
                "status": "failed",
                "reason": str(e)[:200],
            })

    return jsonify(results)


@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
def api_delete_document(doc_id):
    """删除文档"""
    db.delete_document(doc_id)
    if vector_store.is_available:
        vector_store.delete_document(str(doc_id))
    if pgvector_store.is_available:
        pgvector_store.delete_document(doc_id)
    return jsonify({"status": "deleted", "doc_id": doc_id})


# ===== API — RAG 问答 =====

@app.route("/api/rag/query", methods=["POST"])
def api_rag_query():
    """RAG 问答"""
    data = request.get_json()
    query_text = (data or {}).get("query", "").strip()
    if not query_text:
        return jsonify({"error": "请输入问题"}), 400

    top_k = data.get("top_k", 5)
    threshold = data.get("threshold", 0.5)

    try:
        result = rag.query(query_text, top_k=top_k, threshold=threshold)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"问答失败: {exc}"}), 500

    ai_ok, _ = AIClient.is_configured()
    return jsonify({
        "query": result.query,
        "answer": result.answer,
        "sources": result.sources,
        "response_time_ms": result.response_time_ms,
        "chunk_count": result.chunk_count,
        "retrieval_mode": result.retrieval_mode,
        "ai_configured": ai_ok,
        "retrieval_only": "+retrieval_only" in (result.retrieval_mode or ""),
    })


@app.route("/api/rag/stream")
def api_rag_stream():
    """流式 RAG 问答"""
    query_text = request.args.get("query", "").strip()
    if not query_text:
        return jsonify({"error": "请输入问题"}), 400

    top_k = request.args.get("top_k", 5, type=int)
    threshold = request.args.get("threshold", 0.5, type=float)

    def generate():
        try:
            ai_ok, _ = AIClient.is_configured()
            stream_gen, hits = rag.query_stream(
                query_text, top_k=top_k, threshold=threshold,
            )
            retrieval_only = not ai_ok
            if hits and not retrieval_only:
                sources_payload = [{
                    "content": h["content"][:1200],
                    "source": h["metadata"].get("source_file", ""),
                    "similarity": h.get("similarity", 0),
                    "below_threshold": h.get("_below_threshold", False),
                } for h in hits]
                yield f"data: {json.dumps({'type': 'sources', 'data': sources_payload, 'retrieval_only': False}, ensure_ascii=False)}\n\n"
            elif hits and retrieval_only:
                yield f"data: {json.dumps({'type': 'meta', 'retrieval_only': True, 'chunk_count': len(hits)}, ensure_ascii=False)}\n\n"
            for chunk in stream_gen:
                if isinstance(chunk, float):
                    yield f"data: {json.dumps({'type': 'done', 'time_ms': chunk * 1000}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'问答失败: {exc}'}, ensure_ascii=False)}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


# ===== API — 报告 =====

@app.route("/api/reports/generate", methods=["POST"])
def api_generate_report():
    """生成报告"""
    data = request.get_json() or {}
    report_type = data.get("type", "daily")
    if report_type == "daily":
        path = reporter.generate_daily()
    elif report_type == "weekly":
        path = reporter.generate_weekly()
    elif report_type == "monthly":
        path = reporter.generate_monthly()
    else:
        return jsonify({"error": f"不支持的报告类型: {report_type}"}), 400
    return jsonify({"status": "generated", "path": path, "type": report_type})


@app.route("/api/reports/queries")
def api_recent_queries():
    """最近查询记录"""
    limit = request.args.get("limit", 20, type=int)
    queries = db.get_recent_queries(limit=limit)
    return jsonify(queries)


# ===== API — 系统 =====

@app.route("/api/system/check")
def api_system_check():
    """系统健康检查"""
    vec_stats = vector_store.get_collection_stats()
    pg_stats = pgvector_store.get_stats() if pgvector_store.is_available else {"available": False}
    ai_ok, ai_hint = AIClient.is_configured()
    return jsonify({
        "status": "ok",
        "ai_provider": config.AI_PROVIDER,
        "ai_configured": ai_ok,
        "ai_hint": ai_hint if not ai_ok else "",
        "chroma": {
            "available": vec_stats.get("available"),
            "mode": vec_stats.get("mode"),
            "vectors": vec_stats.get("total_vectors", 0),
        },
        "pgvector": pg_stats,
        "db_path": config.METADATA_DB,
    })


# ===== Outlook OAuth 回调 =====

@app.route("/auth/outlook/callback")
def auth_outlook_callback():
    """Microsoft OAuth2 回调 — 用授权码换取 token"""
    code = request.args.get("code")
    error = request.args.get("error")
    if error:
        return f"<h2>授权失败</h2><p>{error}</p>", 400
    if not code:
        return "<h2>缺少授权码</h2>", 400
    try:
        client = OutlookClient()
        client.exchange_code(code)
        return "<h2>✅ 授权成功！</h2><p>Outlook 邮箱已连接，可以关闭此页面。</p>"
    except Exception as e:
        return f"<h2>❌ 授权失败</h2><p>{e}</p>", 500


@app.route("/auth/outlook/login")
def auth_outlook_login():
    """跳转到 Microsoft 授权页面"""
    auth_url = OutlookClient.get_auth_url()
    return f'<meta http-equiv="refresh" content="0;url={auth_url}"><p>正在跳转到 Microsoft 登录...</p>'


# ===== Gitea Webhook =====

@app.route("/api/webhook/gitea", methods=["POST"])
def api_gitea_webhook():
    """接收 Gitea webhook 事件并同步到 Notion"""
    # 验证签名
    if not webhook_handler.verify_signature(request):
        return jsonify({"status": "error", "message": "签名验证失败"}), 403

    # 处理事件
    result = webhook_handler.handle(request)
    return jsonify(result)


# ===== 启动入口 =====

def main():
    vec_stats = vector_store.get_collection_stats()
    pg_stats = pgvector_store.get_stats() if pgvector_store.is_available else {"available": False}
    vec_health = vector_store.health_check()

    chroma_status = "不可用"
    if vec_stats.get("available"):
        mode = vec_stats.get("mode", "?")
        count = vec_stats.get("total_vectors", 0)
        emb_status = ""
        emb_ok = vec_health.get("embedding_ok")
        if emb_ok is False:
            emb_status = " [Embedding异常!]"
        elif emb_ok is None:
            emb_status = ""
        else:
            emb_status = " [Embedding正常]"
        chroma_status = f"{mode}模式 ({count} 向量){emb_status}"

    pg_status = "不可用"
    if pg_stats.get("available"):
        v = pg_stats.get("total_vectors", 0)
        m = pg_stats.get("embedding_model", "")
        pg_status = f"pgvector ({v} 向量, {m})"

    ai_ok, ai_hint = AIClient.is_configured()
    ai_status = config.AI_PROVIDER if ai_ok else "未就绪(仅检索模式)"

    # Embedding 健康警告
    if vec_health.get("embedding_ok") is False:
        print("[VectorStore] ⚠️  Embedding 函数异常，请运行 scripts/verify_persistence.py 排查")
        print("[VectorStore]    常见原因: 缺少 onnxruntime → pip install onnxruntime>=1.18.0")

    print(f"""
╔══════════════════════════════════════════════╗
║       szpeter2026 知识库管理面板            ║
║  AI 提供商: {ai_status:<31}║
║  Chroma:    {chroma_status:<31}║
║  pgvector:  {pg_status:<31}║
║  Ollama:    {config.OLLAMA_BASE_URL:<31}║
║  Webhook:   /api/webhook/gitea                ║
║  Notion:    {'已配置' if config.NOTION_TOKEN else '未配置':<31}║
║  Health:    http://{config.WEB_HOST}:{config.WEB_PORT}/api/health/vector║
║  访问地址:  http://{config.WEB_HOST}:{config.WEB_PORT:<21}║
╚══════════════════════════════════════════════╝
    """)
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=config.WEB_DEBUG)


if __name__ == "__main__":
    main()
