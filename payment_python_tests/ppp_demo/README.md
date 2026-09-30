# PPP 通道示例

这是教学用的完整链路，不连接 Java 服务和真实 PPP。先看懂它，再把 `FakePaymentSystem` 换成真实 HTTP 客户端。

| 示例代码 | 真实系统 |
|---|---|
| `PppChannelMock.create_payout` | `PppDisburseImpl` 调 PPP 下单接口 |
| `PppChannelMock.query_payout` | `PppDisburseQueryImpl` 调 PPP 查询接口 |
| `PppChannelMock.build_callback` | PPP 发给 `/disburse/notifyv2` 的回调 |
| `FakePaymentSystem._apply_channel_status` | 状态映射 + 更新订单 |
| `MerchantSink.receive` | 商户 `notifyUrl` |
| `notify_count/notify_success` | `notifyState/notifyCount` |
| `reversal_review_created` | 成功转失败人工审核记录 |

## 阅读顺序

1. `test_full_flow_disburse_query_success_and_notify_once`
2. `test_duplicate_callback_is_idempotent`
3. `test_success_then_failed_is_review_not_automatic_reversal`
4. `test_ppp_status_mapping`

## 运行

```powershell
cd "D:\PyCharm 2025.2.3\AI"
pytest -q payment_python_tests/ppp_demo/test_ppp_flow.py
```

真实接入时，先替换 `FakePaymentSystem.disburse()`，调用 Java 的 `/disburse`；再替换 `query()` 调用 `/disburse/query`；最后把 `build_callback()` 生成的 body POST 到真实回调地址。每一步都保留状态、幂等和通知断言。
