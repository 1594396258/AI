# 可复用支付通道自动化框架

详细的目录职责、依赖方向和导包规范见 `ARCHITECTURE.md`。

框架按职责分层：

```text
api/                       HTTP 基类和支付 API
config/                    YAML、环境变量、通道契约加载
database/                  MySQL 客户端和订单 Repository
cache/                     Redis 客户端
models/                    通道和订单数据模型
utils/                     签名、轮询、脱敏
mocks/                     PPP 和商户 Mock
services/                  校验、场景、证据
ai/                        AI 配置草稿和失败分析
reports/                   Markdown 报告
contracts/                 通道差异配置
tests/                     单元、契约和真实环境测试
```

## 先跑框架自身测试

```powershell
cd "D:\PyCharm 2025.2.3\AI"
pip install -r payment_python_tests\requirements.txt
python -m pytest -q -c payment_python_tests\pytest.ini payment_python_tests\tests\test_framework_contract.py
```

这些测试不需要 Java、MQ 或数据库，验证框架的配置解析、字段校验、Mock 服务和证据分析。

## 用 AI 生成新通道配置初稿

先将通道文档中的请求、查询、回调样例脱敏，保存为 JSON 数组：

```powershell
python -m payment_python_tests draft payment_python_tests/ai_samples/ppp_samples.json --channel ppp --output payment_python_tests/contracts/ppp.generated.yaml
```

初稿必须人工确认：真实 service 常量、字段含义、币种单位、状态映射、签名原文规则和 ACK。AI 只生成草稿，不能决定测试通过与否。

## 失败分析

测试会把商户请求、Java 响应、通道回调、ACK、数据库快照写入 `artifacts/evidence.db`。导出为 JSON 后可运行：

```powershell
python -m payment_python_tests analyze payment_python_tests/artifacts/evidence.json
```

本地规则会先判断是否缺少回调、数据库或商户通知证据；企业批准的模型网关可以在 `ai_assistant.py` 的 `ask_llm` 中接入，用于对完整证据做自然语言归因。

配置 `AI_BASE_URL`、`AI_API_KEY`、`AI_MODEL` 后，可显式增加 `--ai`：

```powershell
python -m payment_python_tests draft payment_python_tests/ai_samples/ppp_samples.json --channel ppp --output payment_python_tests/contracts/ppp.generated.yaml --ai
python -m payment_python_tests analyze payment_python_tests/artifacts/evidence.json --ai
python -m payment_python_tests report payment_python_tests/artifacts/evidence.json --output payment_python_tests/reports/ppp-report.md
```

模型不会在 pytest 中自动调用，避免网络波动、费用和非确定性影响回归结果。送入模型前仍要对账号、姓名、卡号、手机号、密钥和生产数据脱敏。

## 接入真实 Java

复制 `.env.example` 为 `.env`，填写商户 RSA 私钥、响应验签公钥和测试数据库连接。`PaymentApi` 调用的是被测 Java `/disburse`、`/disburse/query`、`/disburse/notifyv2/{service}@{orderNo}`，不会把 Java 系统替换成 Fake。

数据库表当前按源码确认使用 `FIN_PAY_ORDER`，字段为 `ORDER_NO`、`TRADE_STATE`、`TRANSACTION_ID`、`AMOUNT`、`CHANNEL_AMOUNT`、`NOTIFY_STATE`。数据库账号、密码和环境必须由测试环境提供，不能写进仓库。

PPP 的已确认常量和特殊回调入口：

```text
下单：pay.ppppay.disburse
统一查询：unified.disburse.query
静态回调：/ppp/disburse/notify
```

PPP 与多数通道不同：PPP Dashboard 静态配置 webhook，通过 `merchantOrderId` 定位平台订单，不走 `notifyv2/{service}@{orderNo}`。框架同时支持 `send_static_callback` 和通用 `send_callback`，由通道 YAML 的 `callback.route_mode` 决定。

`tests/live/test_ppp_real_java.py` 是真实 Java 的安全起步样例，默认跳过。它只对指定的测试处理中订单发送“金额错误但签名正确”的 PPP 回调，验证 Java 返回 HTTP 400。运行前必须填写专用测试订单和测试密钥，不能指向生产环境。

新通道通常只需要新增一个 YAML 和一个极薄的适配器；公共校验、状态机安全、幂等、通知、证据和 AI 分析都复用。

## 验证 Java 发给通道的请求

Mock 通道会保存 Java 实际发送的 method、path、headers 和 body。通道 YAML 的 `outbound_request` 描述每个字段的正确来源：

```yaml
outbound_request:
  body:
    amount:
      source: merchant.inrQuantity
      transform: minor_to_major_2
    currencyKey:
      constant: inr
    customerEmail:
      pattern: '^WLT[0-9]{8}_[0-9]{7,8}@gmail[.]com$'
    hash:
      validator: hmac_sha256_sorted_values
```

因此既能发现字段缺失，也能发现“字段存在但取错来源”，例如把 `bankCode` 错写成 `ifscCode`、金额未从分转元、平台订单号错用商户 `msgId`、Bearer Token 取错配置。PPP 查询还会校验 GET URL 是否拼接了数据库中的 `transactionId`。原始请求只在内存中作断言，落盘的出站证据会遮盖密钥、卡号等敏感字段。

完整的新通道接入步骤见 `NEW_CHANNEL_GUIDE.md`。
