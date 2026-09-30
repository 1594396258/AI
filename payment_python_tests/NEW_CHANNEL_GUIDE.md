# 新通道接入清单

## 1. 准备脱敏材料

- 通道下单、查询、回调、心跳文档。
- 每类至少一个成功、处理中、失败样例。
- 签名原文说明、金额单位、回调 ACK 和重试规则。
- 删除密钥、卡号、姓名、手机号、邮箱和生产订单。

## 2. 生成并审核配置

```powershell
python -m payment_python_tests draft payment_python_tests/ai_samples/newpay.json --channel newpay --output payment_python_tests/contracts/newpay.yaml --ai
```

必须人工确认 `service`、`query_service`、订单字段、通道订单字段、金额单位、状态映射、签名算法、回调路由，以及 `outbound_request` 中每个请求参数的来源和转换。所有 `REVIEW_REQUIRED` 清零后才能进入自动回归。

## 3. 配置可控边界

- Java 是真实被测系统，不能 Fake。
- 通道 URL 指向 Python Mock。PPP 对应 Java 配置是 `pay.gateway.third.pppDisburseUrl` 和 `pppDisburseQueryUrl`，具体配置中心键名以部署环境为准。
- 商户 `notifyUrl` 指向 `MockMerchantServer`。
- 测试数据库只读，禁止自动化修改或清理其他订单。
- 每个用例使用唯一 `msgId/orderNo`，Mock 行为按订单隔离。

## 4. 通用准入矩阵

1. 下单：处理中、同步失败、未知状态、超时、HTTP 异常。
2. 查询：内部查询、外部查询、成功、失败、处理中、404、缺字段。
3. 一致性：平台订单号、通道订单号、金额、币种、手续费。
4. 回调：正确签名、错误签名、金额不一致、订单号不一致、通道单号不一致。
5. 状态机：INIT->PROCESSING、PROCESSING->SUCCESS/FAIL、终态幂等、成功转失败保护。
6. 商户通知：终态触发、内容正确、一次性、失败重试、最终 `notifyState`。
7. 稳定性：不使用固定 sleep；所有异步结果限时轮询；失败保存证据链。
8. 出站请求：字段来源、固定值、金额转换、动态格式、请求头、签名和禁止上送字段。

## 5. AI 的职责边界

- AI：提取字段候选、生成 YAML 初稿、补充测试组合、汇总失败证据。
- Python 断言：决定测试通过或失败。
- 测试人员：确认协议事实、环境、风险和准入结论。

AI 不能猜测签名规则、金额单位或未知状态含义，也不能接收未脱敏的生产数据和密钥。
