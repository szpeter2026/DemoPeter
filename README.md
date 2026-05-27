# szpeter2026 知识库平台

> Your Personal Knowledge Base, Powered by RAG

一个现代、轻量、功能完整的本地知识库管理平台。支持多格式文档导入、智能分块、向量检索、RAG 问答、Web 管理面板，以及日/周/月报告生成。

---

## 🏗️ 架构设计

```
szpeter2026/
├── config/                  # 配置中心
│   └── settings.py          # 统一配置（.env + 默认值）
├── src/                     # 核心引擎
│   ├── db_manager.py        # 元数据库管理器（SQLite）
│   ├── doc_processor.py     # 文档处理管道（PDF/MD/TXT → 智能分块）
│   ├── vector_store.py      # Chroma 向量存储
│   ├── rag_engine.py        # RAG 检索引擎（检索→增强→生成）
│   ├── ai_client.py         # AI 统一客户端（DeepSeek / Ollama）
│   ├── report_gen.py        # 报告生成器（日/周/月报）
│   └── web_dashboard.py     # Flask Web 管理面板
├── templates/               # Web 前端模板
│   ├── base.html            # 基础布局
│   ├── index.html           # 仪表盘
│   ├── documents.html       # 文档管理
│   ├── query.html           # RAG 问答（支持流式）
│   └── reports.html         # 报告中心
├── static/css/style.css     # 现代 UI 样式
├── scripts/                 # 运维脚本
│   ├── manage.ps1           # 统一管理脚本
│   ├── import_docs.py       # 批量文档导入
│   └── query.py            # CLI 查询工具
├── knowledge_base/          # 知识库存储
│   ├── documents/           # 原始文档（md/pdf/txt）
│   └── chunks/              # 分块缓存
├── db/                      # 元数据库
│   └── szpeter2026.db       # SQLite 元数据
├── docs/                    # 项目文档
├── tests/                   # 测试套件
└── reports/                 # 报告输出
```

## 🎯 核心能力

| 模块 | 功能 | 吸收来源 |
|------|------|----------|
| **文档管道** | PDF/MD/TXT → 文本提取 → 智能分块（保留段落/章节边界） | HKIE + Wukong |
| **向量检索** | Chroma 语义搜索 + 相似度阈值过滤 | 72changes |
| **RAG 引擎** | 检索增强生成（检索→上下文增强→AI 生成） | 72changes |
| **AI 客户端** | DeepSeek API / Ollama 本地模型，双模式一键切换 | Wukong ai_sql |
| **元数据库** | SQLite 管理文档/分块/查询日志 | Wukong metadata |
| **Web 面板** | Flask 仪表盘 + 文档管理 + 流式问答 + 报告 | Wukong web_dashboard |
| **报告系统** | 日/周/月报自动生成 | Wukong report_gen |
| **运维脚本** | PowerShell 统一管理入口 | Wukong scripts |

## 🚀 快速开始

### 1. 环境准备

```powershell
# 进入项目目录
cd E:\szpeter2026

# 一键初始化（安装依赖 + 创建配置）
.\scripts\manage.ps1 -Action setup
```

### 2. 配置 AI

编辑 `.env` 文件，填入 API Key：

```env
# 使用 DeepSeek（推荐）
DEEPSEEK_API_KEY=sk-your-key-here
AI_PROVIDER=deepseek

# 或使用 Ollama 本地模型
# AI_PROVIDER=ollama
# OLLAMA_MODEL=qwen2:latest
```

### 3. 启动向量数据库容器（Docker）

```powershell
# 一键启动 Chroma + pgvector（数据持久化到 db/ 目录）
.\scripts\manage.ps1 -Action docker-up

# 查看状态
.\scripts\manage.ps1 -Action docker-status

# 停止容器（保留数据）
.\scripts\manage.ps1 -Action docker-down
```

> **数据持久化说明**：向量数据存储在 `db/chroma_docker/`（Chroma）和 `db/pgdata/`（pgvector），容器重启数据不丢失。SQLite 元数据库在 `db/szpeter2026.db`。

### 4. 导入文档

```powershell
# 导入 knowledge_base/documents/ 下的所有文档
.\scripts\manage.ps1 -Action import

# 或指定目录
python scripts\import_docs.py --path "C:\MyDocs"
```

### 5. 启动 Web 面板

```powershell
.\scripts\manage.ps1 -Action web
# 访问 http://127.0.0.1:5200
```

## 📖 使用指南

### Web 面板

| 页面 | 功能 |
|------|------|
| **仪表盘** | 实时统计、快速问答、系统状态 |
| **文档管理** | 批量导入、文档列表、详情预览、删除 |
| **RAG 问答** | 流式对话、多轮对话、来源追踪、参数调节 |
| **报告中心** | 日报/周报/月报生成、查询历史 |

### CLI 工具

```powershell
# Docker 容器管理
.\scripts\manage.ps1 -Action docker-up       # 启动向量数据库容器
.\scripts\manage.ps1 -Action docker-down     # 停止容器（保留数据）
.\scripts\manage.ps1 -Action docker-status   # 健康检查
.\scripts\manage.ps1 -Action docker-reset    # 清除所有数据

# 命令行查询
python scripts\query.py "知识库中有哪些关于XXX的内容？"

# 查看统计
.\scripts\manage.ps1 -Action stats

# 生成报告
.\scripts\manage.ps1 -Action report

# 运行测试
.\scripts\manage.ps1 -Action test
```

## 🔧 技术栈

- **后端**: Python 3.10+ / Flask / SQLite
- **向量库**: Chroma
- **AI**: DeepSeek API / Ollama（本地）
- **文档处理**: pdfplumber / pypdf / markdown
- **前端**: 原生 HTML/CSS/JS（零依赖）

## 📂 数据流程

```
文档文件 (PDF/MD/TXT)
    ↓ doc_processor.py
文本提取 + 智能分块
    ↓
SQLite 元数据库 (documents + chunks)
    ↓ vector_store.py
Chroma 向量嵌入
    ↓ rag_engine.py
用户查询 → 向量检索 → 上下文增强 → AI 生成 → 返回答案
```

## 📊 元数据库表结构

| 表 | 说明 |
|----|------|
| `documents` | 文档注册表（标题、路径、类型、状态） |
| `chunks` | 分块表（文档→分块索引→内容→字符数） |
| `query_logs` | 查询日志（问题、AI 提供商、耗时） |

## 🧪 测试

```powershell
.\scripts\manage.ps1 -Action test
```

## 📝 许可证

MIT License
