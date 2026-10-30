# 深度研究助手

输入研究主题，可添加一份 PDF 作为参考资料，结合文档片段和网页资料生成研究报告。

简要设计见 [RAG_ARCHITECTURE.md](docs/RAG_ARCHITECTURE.md)，原始案例架构见 [DESIGN.md](docs/DESIGN.md)。

## 本地启动

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --app-dir backend/src --host 127.0.0.1 --port 8001
```

在另一个终端执行：

```powershell
cd frontend
npm install
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8001'
npm run dev -- --host 127.0.0.1 --port 5174
```

模型、搜索和 Embedding 配置位于 `backend/.env`，配置项示例见 `backend/.env.example`。聊天模型与 Embedding 使用各自的配置。使用本机模型反代时需先启动对应服务；项目不会自动启动或修改反代。

## 使用方式

1. 点击“添加 PDF”并选择含文本层的文件，选择后自动开始导入。首版一次使用一份 PDF，文件最大 20 MB，暂不支持扫描件 OCR。
2. 等待解析和向量入库完成，成功后自动作为当前研究的资料。移除只解除当前关联；刷新或重新打开页面后如需使用，请重新上传。
3. 输入研究主题，开始研究。每个子任务分别检索文档与网页，再整理证据和生成总结。
4. 在来源区查看文档片段或网页链接。页面与报告使用 `[1]`、`[2]` 等数字引用，报告末尾的参考来源来自实际返回的来源记录，并注明文档或网页。

不添加资料时只执行联网研究；一路检索失败时仍可使用另一路的有效证据，两路都没有证据时说明资料不足。引用编号会检查是否存在，但这不等于逐条事实正确性已获自动验证。

默认使用 `.runtime/knowledge_bases/` 中的本地持久化 Qdrant；配置 `QDRANT_URL` 后可连接外部服务。本地模式适用于单进程运行，请勿同时启动多个后端进程共享同一存储目录。

## 日志与验证

核心阶段同时记录到控制台和 `.runtime/logs/research.log`，可按研究 ID、任务 ID、知识库 ID 查找。日志文件自动轮转。

后续修改按约定交由用户提供真实任务验收，不主动运行自动化测试。以下命令保留供需要时手动使用。

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
cd frontend
npm run build
```

自动化测试使用固定向量验证存储和分支逻辑，真实 Embedding 与聊天模型的验证结果单独记录，避免将模拟测试当成外部服务可用性证明。
