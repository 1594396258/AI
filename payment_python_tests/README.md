# Python 支付通道自动化测试

这套测试按黑盒方式调用真实 Java 支付系统。外部通道和商户通知使用可控 Mock，数据库只读验证；公共字段、状态、幂等和通知规则由通道契约复用。

完整框架说明见 `README_FRAMEWORK.md`，新增通道步骤见 `NEW_CHANNEL_GUIDE.md`。`ppp_demo` 仅用于学习状态机，不代表真实系统测试。

## 运行

```powershell
cd payment_python_tests
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 编辑 .env，填写测试环境参数
pytest -q
```

框架自身测试不需要任何环境：

```powershell
pytest -q tests/test_framework_contract.py tests/test_framework_unit.py
```

默认没有配置真实参数时，真实 Java 用例会显示为 skipped，不会误报失败，也不会连接测试环境。

## 第一批要补的内容

1. 在 `.env` 填测试环境地址和商户参数。
2. 在 `.env` 配置商户 RSA 私钥（不要提交到 Git）；模板会自动生成 SHA256withRSA 签名。
3. 确认代付返回处理中后，数据库或管理后台订单为处理中。
4. 使用通道 Mock 或真实通道回调，把订单推进成功/失败。
5. 新通道新增 YAML 契约和少量适配器，不复制整套公共测试。

不要一开始测试所有通道。先把“代付 -> 查询 -> 回调 -> 商户通知”跑通。
