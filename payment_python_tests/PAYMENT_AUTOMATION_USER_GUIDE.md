# 支付通道自动化测试框架使用指南

版本：1.0  
更新日期：2026-09-30  
适用对象：支付测试、通道接入开发、测试环境维护人员

## 1. 框架解决什么问题

本框架用于测试支付中间系统的通道接入。被测对象始终是真实 Java 支付系统：

```text
Python pytest
  -> 真实 Java 支付系统
  -> Mock 通道
  -> 测试数据库
  -> Mock 商户通知服务
```

主要覆盖：

- 商户调用代付接口。
- Java 发给通道的请求参数、取值来源、金额转换、请求头和签名。
- 外部代付查询和内部自动查询。
- 通道查询响应与本地订单数据一致性。
- 通道回调验签、金额和订单号校验。
- 本地订单状态扭转和终态保护。
- 终态触发商户通知、幂等和失败重试。
- 数据库状态、通道订单号、金额、通知状态校验。
- 测试证据保存、AI 失败分析和 Markdown 报告。

`ppp_demo` 只是学习状态机的教学代码。正式测试必须调用真实 Java。

## 2. 职责分工

测试人员负责：

- 准备测试数据和通道脱敏样例。
- 编写或审核通道 YAML 契约。
- 执行 pytest，检查证据和报告。
- 给出通道是否准入的测试结论。

开发或环境维护人员负责：

- 启动真实 Java、MQ、Redis 和测试数据库。
- 将 Java 的通道 URL 指向 Python Mock。
- 提供专用测试商户和测试通道配置。
- 保证测试环境与生产环境隔离。

AI负责：

- 根据脱敏样例生成 YAML 初稿。
- 审查字段映射和建议异常场景。
- 汇总失败证据，给出排查方向。

最终通过或失败必须由 Python 确定性断言决定，不能由 AI 决定。

## 3. 目录说明

```text
payment_python_tests/
  contracts/                    通道契约配置
    ppp.yaml                     PPP 标准样板
  api/                          HTTP 基类和支付 API
    base_api.py                  GET/POST/PUT/DELETE/PATCH 基类
    payment_api.py               真实 Java 商户接口客户端
  config/                       YAML、.env 和通道契约加载
  database/                     MySQL 客户端和订单 Repository
  cache/                        Redis 客户端
  models/                       通道契约、订单模型
  utils/                        签名、轮询、脱敏工具
  mocks/                        Mock 通道和 Mock 商户
  services/                     校验、场景、证据服务
  ai/                           AI 配置审查和失败分析
  reports/                      Markdown 报告
  payment_auto_framework/       旧代码兼容层，新代码不要导入
  tests/                         框架和业务测试
  tests/live/                    真实环境测试，默认跳过
  ai_samples/                    脱敏通道报文样例
  .env.example                   环境变量模板
  NEW_CHANNEL_GUIDE.md           新通道接入检查表
```

## 4. 第一次安装

要求 Python 3.10 或更高版本。PowerShell 执行：

```powershell
cd "D:\PyCharm 2025.2.3\AI"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r payment_python_tests\requirements.txt
```

如果 PowerShell 禁止激活虚拟环境，可仅对当前窗口执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

## 5. 先验证框架本身

```powershell
python -m pytest -q -c payment_python_tests\pytest.ini payment_python_tests\tests
```

未配置真实环境时，正常结果应类似：

```text
15 passed, 4 skipped
```

`skipped` 表示真实 Java 测试未启用，不是失败。该命令不会发送真实代付。

## 6. 配置测试环境

复制环境变量模板：

```powershell
Copy-Item payment_python_tests\.env.example payment_python_tests\.env
```

常用配置：

```dotenv
PAYMENT_BASE_URL=http://127.0.0.1:9012/finance-payment-service/v1
MCH_ID=测试商户号
MCH_PRIVATE_KEY=测试商户RSA私钥Base64
RESPONSE_PUBLIC_KEY=Java响应验签公钥Base64
REQUEST_TIMEOUT=15

DB_HOST=测试数据库地址
DB_PORT=3306
DB_NAME=测试数据库名
DB_USER=只读账号
DB_PASSWORD=只读账号密码
DB_CHARSET=utf8mb4

REDIS_HOST=测试Redis地址
REDIS_PORT=6379
REDIS_PASSWORD=测试Redis密码
REDIS_DB=0
REDIS_PROTOCOL=2
REDIS_KEY_PREFIX=payment-auto:

RUN_LIVE_TESTS=false
```

安全要求：

- `.env` 已被 `.gitignore` 排除，禁止提交。
- 只能使用测试商户、测试密钥和测试数据库。
- 数据库账号建议只授予 `SELECT`。
- 禁止把生产卡号、姓名、手机号和密钥送给 AI。
- 准备发送代付前再次检查 `PAYMENT_BASE_URL`，确认不是生产地址。

## 7. 标准基础层使用方式

所有业务 API 都继承统一 HTTP 基类：

```python
from payment_python_tests.api.base_api import BaseApi


class ExampleChannelApi(BaseApi):
    def create_order(self, body: dict):
        response = self.post("orders", json=body)
        response.raise_for_status()
        return response.json()
```

`BaseApi` 已统一封装：

```text
GET / POST / PUT / DELETE / PATCH
requests.Session
公共请求头和 Bearer Token
超时
URL 拼接
请求、响应日志及敏感字段脱敏
```

数据库统一通过 Client 和 Repository 两层使用：

```python
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.database.order_repository import OrderRepository

settings = AppSettings.from_env()

with MysqlClient(settings.database) as mysql:
    orders = OrderRepository(mysql)
    order = orders.get_by_out_order_no("商户msgId")
```

`MysqlClient` 默认只读。需要写数据库时必须显式传入 `allow_write=True`，普通业务自动化禁止开启。

Redis 统一使用：

```python
from payment_python_tests.cache.redis_client import RedisClient
from payment_python_tests.config.settings import AppSettings

settings = AppSettings.from_env()
cache = RedisClient(settings.redis)

cache.set_json("order:ORDER-001", {"status": "PROCESSING"}, expire_seconds=60)
data = cache.get_json("order:ORDER-001")
cache.close()
```

所有自动化 Redis key 必须配置 `REDIS_KEY_PREFIX`，不能直接使用业务系统的公共 key。

## 8. 启动 Mock PPP 和 Mock 商户

推荐在测试文件中使用固定端口 fixture：

```python
import pytest

from payment_python_tests.mocks import MockMerchantServer, MockPppServer


@pytest.fixture(scope="session")
def ppp_mock():
    server = MockPppServer(port=18080).start()
    yield server
    server.close()


@pytest.fixture(scope="session")
def merchant_mock():
    server = MockMerchantServer(port=19090).start()
    yield server
    server.close()
```

测试环境 Java 的 PPP 地址配置为：

```text
pppDisburseUrl=http://127.0.0.1:18080/v1/payouts/
pppDisburseQueryUrl=http://127.0.0.1:18080/v1/payouts/status/
```

如果 Java 运行在容器、远程服务器或 Kubernetes 中，`127.0.0.1` 指向的是 Java 所在机器，不能直接访问测试人员电脑。此时需要使用测试环境可访问的 IP、域名或端口转发地址。

商户通知地址使用：

```text
http://测试机IP:19090/merchant/notify
```

PPP 的通道配置 `notifyUrl` 如果会覆盖商户请求中的 `notifyUrl`，也必须指向 Mock 商户。

## 9. PPP 第一条完整用例

第一条用例只验证成功主链路：

```text
Mock PPP 启动
  -> Python 调用真实 Java 代付
  -> Java 请求 Mock PPP
  -> 校验 Java 发给 PPP 的参数
  -> 数据库订单进入 PROCESSING
  -> Python 发送 PPP 成功回调给真实 Java
  -> 数据库订单进入 SUCCESS
  -> Mock 商户收到一次成功通知
```

建议商户请求数据保存为变量，后续用于出站字段来源校验：

```python
merchant_data = {
    "trxAmount": "10000",
    "amount": "10000",
    "tradeAmount": "10000",
    "inrQuantity": "10000",
    "userId": "AUTO-USER-001",
    "bankAccount": "Test User",
    "bankCardNo": "602801536155",
    "bankCode": "PUNB0027120",
    "ifscCode": "PUNB0027120",
    "currency": "INR",
    "mobileNumber": "9770038888",
    "notifyUrl": merchant_mock.url + "/merchant/notify",
}
```

调用真实 Java：

```python
msg_id = payment_client.new_message_id("PPP")

payment_client.create_payout(
    contract.service,
    msgId=msg_id,
    **merchant_data,
)
```

使用商户 `msgId` 查找平台订单，不要查询“最新一条”：

```python
from payment_python_tests.utils.wait_utils import wait_until

db_order = wait_until(
    lambda: order_repository.get_by_out_order_no(msg_id),
    lambda order: order is not None and order.state_name == "PROCESSING",
    timeout=30,
    description="PPP订单进入PROCESSING",
)
```

## 10. 校验 Java 发给通道的请求参数

从 Mock PPP 读取 Java 实际请求：

```python
channel_request = wait_until(
    lambda: ppp_mock.last_record("POST"),
    lambda record: record is not None,
    timeout=10,
    description="Java请求Mock PPP",
)
```

执行出站契约校验：

```python
from payment_python_tests.services.validation_service import assert_valid_outbound_request

assert_valid_outbound_request(
    contract,
    channel_request,
    {
        "merchant": merchant_data,
        "database": {
            "orderNo": db_order.order_no,
        },
        "channel_config": {
            "payMerchant": "测试PPP商户标识",
            "pin": "测试PPP PIN",
        },
    },
    signing_secret="测试PPP SecretKey",
)
```

PPP 契约当前会检查：

- `amount` 是否来自 `inrQuantity`，并正确从最小单位转为两位小数。
- `customerAccNo` 是否来自 `bankCardNo`。
- `customerIfsc` 是否来自 `bankCode`。
- `customerMobile`、`customerName` 是否取值正确。
- `merchantIdentifier` 是否来自通道 `payMerchant`。
- `merchantOrderId` 是否使用数据库平台订单号。
- `currencyKey=inr`、`transactionModeKey=imps`。
- 动态邮箱是否满足 PPP 格式。
- Bearer Token、Content-Type 和 HMAC-SHA256 签名。
- `notifyUrl`、`callbackUrl` 等禁止字段是否被错误发送。

## 11. 查询请求校验

PPP 查询是 GET，请求 URL 最后一段必须使用数据库中的 `TRANSACTION_ID`：

```python
query_request = wait_until(
    lambda: ppp_mock.last_record("GET"),
    lambda record: record is not None,
    timeout=30,
    description="Java查询Mock PPP",
)

assert_valid_outbound_request(
    contract,
    query_request,
    {
        "database": {
            "transactionId": db_order.transaction_id,
        },
        "channel_config": {
            "pin": "测试PPP PIN",
        },
    },
    operation="query",
)
```

注意 PPP 源码限制下单满两分钟后才查询通道。外部查询对非终态订单可能直接返回本地状态，因此查询用例需要区分“外部查询”和“内部自动查询”。

## 12. 通道回调测试

PPP 使用静态回调：

```text
POST /ppp/disburse/notify
```

正确签名回调：

```python
from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values

callback = {
    "status": "success",
    "merchantOrderId": db_order.order_no,
    "transactionId": db_order.transaction_id,
    "amount": "100.00",
    "utr": "AUTO-UTR-001",
}
callback["hash"] = hmac_sha256_sorted_values(callback, ppp_secret)

response = payment_client.send_static_callback(
    contract.callback["endpoint"],
    db_order.order_no,
    callback,
)

assert response.status_code == 200
assert response.text == "SUCCESS"
```

至少覆盖以下异常回调：

- 错误签名。
- 金额多一分、少一分、为空。
- `merchantOrderId` 不存在。
- `transactionId` 与数据库不一致。
- 缺少必填字段。
- 相同回调重复发送。
- 成功订单收到失败回调。

异常回调不仅断言 HTTP 400，还要断言：

```text
数据库订单没有被错误修改
通道订单号和金额没有被覆盖
商户没有收到错误通知
```

## 13. 商户通知校验

等待商户通知，不使用固定 `sleep`：

```python
notice = wait_until(
    lambda: merchant_mock.last_record("POST"),
    lambda record: record is not None,
    timeout=30,
    description="商户收到终态通知",
)

assert notice["body"]["orderNo"] == db_order.order_no
assert notice["body"]["trxState"] == "SUCCESS"
```

还要检查：

- 金额、币种、通道订单号和商户原订单号。
- 商户通知签名。
- 正常终态只通知一次。
- 商户第一次返回失败时会重试。
- 最终 `NOTIFY_STATE` 与通知结果一致。

## 14. 数据库校验

框架默认只读查询 `FIN_PAY_ORDER`：

```python
order = order_repository.get(db_order.order_no)

assert order.state_name == "SUCCESS"
assert order.transaction_id == expected_transaction_id
assert order.channel_amount == 10000
```

常用状态：

```text
0 INIT
1 PROCESSING
2 SUCCESS
3 FAIL
4 REVERSAL
5 CLOSED
```

不要在公共测试环境自动删除订单。每条测试使用唯一 `msgId`，避免数据互相影响。

## 15. 使用 AI 生成新通道配置初稿

先把通道下单、查询和回调样例脱敏，保存为 JSON 数组：

```json
[
  {
    "merchantOrderId": "ORDER-001",
    "transactionId": "CHANNEL-001",
    "amount": "100.00",
    "status": "pending"
  }
]
```

生成 YAML 初稿：

```powershell
python -m payment_python_tests draft `
  payment_python_tests/ai_samples/newpay_samples.json `
  --channel newpay `
  --output payment_python_tests/contracts/newpay.yaml
```

配置 AI 模型后增加审查：

```dotenv
AI_BASE_URL=https://企业批准的模型网关/v1
AI_API_KEY=模型密钥
AI_MODEL=模型名称
```

```powershell
python -m payment_python_tests draft `
  payment_python_tests/ai_samples/newpay_samples.json `
  --channel newpay `
  --output payment_python_tests/contracts/newpay.yaml `
  --ai
```

AI 生成结果中的 `REVIEW_REQUIRED` 必须人工确认。尤其不能让 AI 猜测：

- 金额单位和精度。
- 签名原文和字段排序。
- 未知状态含义。
- 通道成功 ACK。
- 字段到底来自商户请求、数据库还是通道配置。

## 16. 新通道接入步骤

1. 收集并脱敏通道文档和报文样例。
2. 使用 AI 生成 `contracts/newpay.yaml` 初稿。
3. 开发和测试共同审核字段、状态、签名和出站请求来源。
4. 配置 Java 通道 URL 指向 Mock。
5. 先跑下单处理中主链路。
6. 加入查询成功、失败和处理中。
7. 加入回调成功、失败、重复和错误数据。
8. 加入终态通知、重试和幂等。
9. 执行全部公共准入用例。
10. 使用真实通道做少量成功冒烟测试。

不建议复制 PPP 的整套代码修改字段。正确方式是新增一个通道 YAML 和少量特殊适配逻辑，公共校验继续复用。

## 17. 失败证据和报告

测试证据包括：

```text
商户请求
Java 响应
Java 发给通道的请求
通道回调
Java 回调 ACK
数据库快照
商户通知
```

敏感字段在写入证据前会自动遮盖。生成失败分析：

```powershell
python -m payment_python_tests analyze payment_python_tests/artifacts/evidence.json
```

使用 AI 增强分析：

```powershell
python -m payment_python_tests analyze payment_python_tests/artifacts/evidence.json --ai
```

生成 Markdown 报告：

```powershell
python -m payment_python_tests report `
  payment_python_tests/artifacts/evidence.json `
  --output payment_python_tests/reports/ppp-report.md
```

AI 分析只提供排查方向，原始请求、数据库状态和断言结果才是测试结论依据。

## 18. 通道准入最低标准

新通道至少需要通过：

- 下单成功、处理中、同步失败和超时。
- Java 出站请求所有关键字段取值正确。
- 金额单位、精度和签名正确。
- 外部查询和内部查询状态映射正确。
- 回调签名、金额、平台订单号和通道订单号校验正确。
- 重复回调不会重复更新、重复通知或重复记账。
- 非终态可以进入成功或失败。
- 终态不能被普通回调错误覆盖。
- 成功转失败按系统规则进入人工审核或逆转流程。
- 终态通知内容正确，失败可以重试。
- 测试失败能够提供完整证据链。
- 至少完成一条真实通道冒烟测试。

## 19. 常见问题

### Java 没有请求 Mock PPP

检查：

- Java 通道 URL 是否仍指向真实 PPP。
- 测试商户是否开通 PPP service。
- 路由是否选择了 PPP 通道。
- Mock 地址对 Java 所在环境是否可访问。
- 通道 `pin`、`secretKey`、`payMerchant` 是否齐全。

### Mock 收到请求，但字段校验失败

查看错误代码：

```text
REQUEST_FIELD_MISSING       字段缺失
REQUEST_VALUE_MISMATCH      字段取值或来源错误
FORMAT_MISMATCH             动态字段格式错误
FORBIDDEN_FIELD_PRESENT     发送了禁止字段
HEADER_VALUE_MISMATCH       请求头或鉴权错误
PATH_MISMATCH               查询 URL 或通道订单号错误
```

### 回调成功但数据库不变化

检查签名、金额单位、`merchantOrderId`、`transactionId`、订单当前状态和 Java 日志。

### 数据库成功但商户没收到通知

检查 `notifyUrl`、MQ、通知消费者、`NOTIFY_STATE`、Mock 商户网络可达性和通知重试记录。

### pytest 意外访问其他项目

必须在 `payment_python_tests` 目录执行并指定本目录配置：

```powershell
python -m pytest -q -c payment_python_tests\pytest.ini payment_python_tests\tests
```

本目录使用 `--confcutdir=.`，不会加载上层项目的自动登录 fixture。

### PyCharm 提示找不到 payment_python_tests

先确认 PyCharm 项目根目录是 `D:\PyCharm 2025.2.3\AI`，然后执行：

```powershell
cd "D:\PyCharm 2025.2.3\AI"
python -c "from payment_python_tests.config.contract_loader import load_contract; print('import ok')"
```

如果命令成功但编辑器仍然标红，检查 PyCharm 的项目根目录和 Project Interpreter。推荐解释器为 `D:\PyCharm 2025.2.3\AI\.venv\Scripts\python.exe`。

## 20. 推荐日常命令

只跑框架测试：

```powershell
python -m pytest -q -c payment_python_tests\pytest.ini payment_python_tests\tests -m "not live"
```

运行真实环境测试：

```powershell
$env:RUN_LIVE_TESTS="true"
python -m pytest -q -c payment_python_tests\pytest.ini payment_python_tests\tests -m live
```

运行单个用例并显示详细日志：

```powershell
python -m pytest -vv -s -c payment_python_tests\pytest.ini payment_python_tests/tests/live/test_ppp_real_java.py
```

真实用例执行完成后及时关闭：

```powershell
$env:RUN_LIVE_TESTS="false"
```

## 21. 操作原则

请始终遵守：

```text
真实 Java，Mock 外部依赖
一条用例只验证一个主要风险
每条用例使用唯一订单号
异步结果限时轮询，不写固定 sleep
失败时保留完整且脱敏的证据
AI 负责辅助，Python 断言负责裁决
先测试环境完整回归，再做真实通道少量冒烟
```
