# TraceLens — AI 日志报错分析工具

一个本地优先的日志诊断小工具。粘贴或上传日志后，它会提取异常、关键堆栈和错误统计，匹配常见故障模式，并给出按优先级排列的排查建议。配置 OpenAI 兼容接口后，还可进行 AI 深度分析。

## 功能

- 支持粘贴和拖拽上传 `.log`、`.txt`、`.out`、`.json`
- 覆盖 Python、Java、Node.js、数据库、网络、容器等常见错误
- 输出严重程度、置信度、可能根因、证据和修复步骤
- 调用 AI 前自动脱敏密码、Token、API Key、邮箱和 IP
- 支持 OpenAI、兼容 Chat Completions 的服务及本地 Ollama
- 一键复制 Markdown 分析报告

## 启动

```powershell
cd "D:\PyCharm 2025.2.3\AI\ai_log_analyzer"
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 5000
```

浏览器访问 <http://127.0.0.1:5000>。不配置 AI 也可以使用完整的本地规则分析。

## 配置 AI（可选）

复制配置模板并编辑项目目录中的 `.env`：

```powershell
Copy-Item .env.example .env
```

`.env` 内容示例：

```dotenv
AI_API_KEY=你的密钥
AI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4.1-mini
AI_TIMEOUT=60
```

然后直接启动：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 5000
```

程序会自动读取 `ai_log_analyzer/.env`，且系统环境变量的优先级高于 `.env`。真实 `.env` 已被 `.gitignore` 排除，不要把密钥写入 `.env.example` 或提交到版本库。

本地 Ollama 示例：

```powershell
AI_BASE_URL=http://127.0.0.1:11434/v1
AI_MODEL=qwen2.5:7b
AI_TIMEOUT=60
```

配置好 `.env` 后启动：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 5000
```

完整配置参考 `.env.example`。

## 测试

```powershell
python -m pytest -q
```

FastAPI 自动接口文档位于 <http://127.0.0.1:5000/docs>，备用 ReDoc 文档位于 <http://127.0.0.1:5000/redoc>。

## 隐私说明

本地规则分析不会把日志发送到外部。只有主动打开“AI 深度分析”时，脱敏后的日志才会发送到你配置的模型服务。脱敏是辅助保护，生产日志仍建议在输入前确认符合公司的数据安全规范。

