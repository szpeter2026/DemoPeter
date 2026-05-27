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
    return render_template("query.html", ai_provider=config.AI_PROVIDER)


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


@app.route("/api/documents/import", methods=["POST"])
def api_import_documents():
    """批量导入文档"""
    data = request.get_json() or {}
    directory = data.get("directory", str(config.DOCS_DIR))
    if not Path(directory).exists():
        return jsonify({"error": f"目录不存在: {directory}"}), 400

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
            if vector_store.is_available:
                vector_store.add_documents(str(doc_id), chunks)

            if pgvector_store.is_available:
                pgvector_store.add_documents(doc_id, chunks)

            # 更新状态
            db.update_document_status(doc_id, "completed", len(chunks))
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

    result = rag.query(query_text, top_k=top_k, threshold=threshold)
    return jsonify({
        "query": result.query,
        "answer": result.answer,
        "sources": result.sources,
        "response_time_ms": result.response_time_ms,
        "chunk_count": result.chunk_count,
    })


@app.route("/api/rag/stream")
def api_rag_stream():
    """流式 RAG 问答"""
    query_text = request.args.get("query", "").strip()
    if not query_text:
        return jsonify({"error": "请输入问题"}), 400

    def generate():
        stream_gen, hits = rag.query_stream(query_text)
        # 先发送来源
        yield f"data: {json.dumps({'type': 'sources', 'data': [{'content': h['content'][:300], 'source': h['metadata'].get('source_file', '')} for h in hits]}, ensure_ascii=False)}\n\n"
        # 流式发送回答
        for chunk in stream_gen:
            if isinstance(chunk, float):
                # 最后一个是耗时
                yield f"data: {json.dumps({'type': 'done', 'time_ms': chunk * 1000}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'text', 'content': chunk}, ensure_ascii=False)}\n\n"

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
    return jsonify({
        "status": "ok",
        "ai_provider": config.AI_PROVIDER,
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

    chroma_status = "不可用"
    if vec_stats.get("available"):
        mode = vec_stats.get("mode", "?")
        count = vec_stats.get("total_vectors", 0)
        chroma_status = f"{mode}模式 ({count} 向量)"

    pg_status = "不可用"
    if pg_stats.get("available"):
        v = pg_stats.get("total_vectors", 0)
        m = pg_stats.get("embedding_model", "")
        pg_status = f"pgvector ({v} 向量, {m})"

    print(f"""
╔══════════════════════════════════════════════╗
║       szpeter2026 知识库管理面板            ║
║  AI 提供商: {config.AI_PROVIDER:<31}║
║  Chroma:    {chroma_status:<31}║
║  pgvector:  {pg_status:<31}║
║  Ollama:    {config.OLLAMA_BASE_URL:<31}║
║  Webhook:   /api/webhook/gitea                ║
║  Notion:    {'已配置' if config.NOTION_TOKEN else '未配置':<31}║
║  访问地址:  http://{config.WEB_HOST}:{config.WEB_PORT:<21}║
╚══════════════════════════════════════════════╝
    """)
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, debug=config.WEB_DEBUG)


if __name__ == "__main__":
    main()
