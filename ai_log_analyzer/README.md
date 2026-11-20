# TraceLens — AI 日志报错分析工具

一个本地优先的日志诊断小工具。粘贴或上传日志后，它会提取异常、关键堆栈和错误统计，匹配常见故障模式，并给出按优先级排列的排查建议。配置 OpenAI 兼容接口后，还可进行 AI 深度分析。

## 功能

- 支持粘贴和拖拽上传 `.log`、`.txt`、`.out`、`.json`
- 覆盖 Python、Java、Node.js、数据库、网络、容器等常见错误
- 输出严重程度、置信度、可能根因、证据和修复步骤
- 调用 AI 前自动脱敏密码、Token、API Key、邮箱和 IP
- 可选择关联本地代码库，由 AI 多轮使用只读工具调查目录、源码、调用链和配置
- 可选择白名单只读数据库，由 AI 查看表结构并执行受限 SELECT 查询
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

# 可选：允许页面选择的代码库，多个路径使用英文分号分隔
AI_CODE_ROOTS=D:\projects\service-a;D:\projects\service-b
```

然后直接启动：

```powershell
python -m uvicorn app:app --host 127.0.0.1 --port 5000
```

程序会自动读取 `ai_log_analyzer/.env`，且系统环境变量的优先级高于 `.env`。真实 `.env` 已被 `.gitignore` 排除，不要把密钥写入 `.env.example` 或提交到版本库。

配置 `AI_CODE_ROOTS` 后，页面会出现“关联本地代码”选择框。开启后进入智能代码调查模式：模型可以多轮使用“浏览目录、查找文件、搜索源码、按行读取”四种只读工具，沿堆栈追踪调用方、实现和配置，直到证据充分或预算用尽。

后端不会读取允许范围之外的路径，不执行代码、不运行 Shell、不修改文件，并会忽略依赖、虚拟环境和构建目录。每次工具返回的源码都会脱敏，报告会展示调查轮数、工具调用和引用文件。相关源码会发送到 `AI_BASE_URL` 配置的模型服务，请先确认符合项目的数据安全要求。

调查预算可以在 `.env` 调整：

```dotenv
AI_CODE_MAX_ROUNDS=8
AI_CODE_MAX_TOOL_CALLS=12
AI_CODE_MAX_CHARS=60000
```

## 配置只读数据库（可选）

在 `.env` 中先声明允许使用的数据源别名，再配置连接信息：

```dotenv
AI_DATABASES=payin_test,order_readonly

AI_DB_PAYIN_TEST_NAME=出入金测试库
AI_DB_PAYIN_TEST_URL=mysql+pymysql://readonly_user:url_encoded_password@127.0.0.1:3306/payin_payout?charset=utf8mb4
AI_DB_PAYIN_TEST_SCHEMAS=payin_payout

AI_DB_ORDER_READONLY_NAME=订单只读库
AI_DB_ORDER_READONLY_URL=postgresql+psycopg://readonly_user:url_encoded_password@127.0.0.1:5432/orders
AI_DB_ORDER_READONLY_SCHEMAS=public

AI_DB_MAX_TOOL_CALLS=8
AI_DB_MAX_ROWS=50
AI_DB_QUERY_TIMEOUT_MS=5000
AI_DB_MAX_CHARS=40000
```

配置后重启服务，页面会出现“查询只读数据库”选择框。模型可以列出表、查看表结构和执行单条 `SELECT`/只读 CTE；后端拒绝增删改、DDL、多语句、SQL 注释和 `SELECT ... INTO`，并强制限制查询行数、返回字符、调用次数和超时。查询结果中的密码、Token、密钥、证件号、银行卡号、邮箱、IP 和手机号等会脱敏后再发送给模型。

应用层限制不能替代数据库权限控制。数据库账号必须使用专门的只读账号，只授予需要调查的库表和 schema 的 `SELECT`/元数据权限；不要配置生产写账号。连接串只从 `.env` 读取，不会返回给网页或模型。密码中存在 `@`、`:`、`/` 等字符时需要进行 URL 编码。

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

