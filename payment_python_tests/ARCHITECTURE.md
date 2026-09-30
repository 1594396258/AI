# 支付自动化框架分层规范

更新日期：2026-09-30

## 依赖方向

```text
tests
  -> services
  -> api / database / cache / mocks
  -> config / models / utils
```

下层不能反向依赖测试用例。通用工具不能依赖具体通道，具体通道差异必须放在 `contracts/*.yaml` 或通道 Mock 中。

## 各层职责

| 目录 | 职责 | 典型对象 |
|---|---|---|
| `api/` | HTTP 请求和业务接口客户端 | `BaseApi`, `PaymentApi` |
| `config/` | YAML、`.env`、通道契约加载 | `AppSettings`, `load_contract` |
| `database/` | 数据库连接和数据访问 | `MysqlClient`, `OrderRepository` |
| `cache/` | Redis 连接和缓存操作 | `RedisClient` |
| `models/` | 无外部副作用的数据模型 | `ChannelContract`, `OrderSnapshot` |
| `utils/` | 无业务状态的公共工具 | 签名、轮询、脱敏 |
| `mocks/` | 外部通道和商户模拟 | `MockPppServer`, `MockMerchantServer` |
| `services/` | 组合多个基础层完成业务测试 | 校验、场景、证据 |
| `ai/` | 配置草稿和失败分析 | `AiAssistant` |
| `reports/` | 报告构建 | Markdown 报告 |
| `tests/` | 测试场景和断言 | 单元、契约、真实环境测试 |

## 新代码导包规范

```python
from payment_python_tests.api.payment_api import PaymentApi
from payment_python_tests.config.settings import AppSettings
from payment_python_tests.database.mysql_client import MysqlClient
from payment_python_tests.database.order_repository import OrderRepository
from payment_python_tests.cache.redis_client import RedisClient
from payment_python_tests.utils.sign_utils import hmac_sha256_sorted_values
```

`payment_auto_framework/` 仅用于兼容之前已经生成的代码。新测试不得从该目录导包。

## HTTP 客户端规范

- 所有 HTTP 客户端继承 `BaseApi`。
- `BaseApi` 只处理 URL、Session、Headers、超时、日志和 HTTP 方法。
- 业务路径和报文构造放在子类，例如 `PaymentApi`。
- 业务断言不能写进 `BaseApi`。
- 日志必须经过脱敏，不能打印密钥、签名、卡号和 Token。

## 数据访问规范

- `MysqlClient` 负责连接和执行 SQL，不处理订单业务。
- `OrderRepository` 负责 `FIN_PAY_ORDER` 数据映射。
- 数据库默认只读；写操作必须显式设置 `allow_write=True`。
- 测试不得使用“最新一条订单”，必须使用唯一订单号查询。

## Redis 规范

- 统一使用 `RedisClient`，禁止测试文件自行创建 `redis.Redis`。
- 测试 key 必须配置 `REDIS_KEY_PREFIX`。
- JSON 数据使用 `get_json/set_json`。
- 删除 Redis 数据前必须确认 key 属于当前自动化用例。

## 配置规范

- 无密钥默认值放在 `config/config.yaml`。
- 密钥、账号和环境地址覆盖放在 `.env`。
- 通道协议差异放在 `contracts/{channel}.yaml`。
- 测试代码中禁止硬编码数据库密码、Redis 密码和通道密钥。
