# Python 支付自动化测试起步模板

这套测试按黑盒方式调用支付系统，不需要阅读或修改 Java。

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

默认没有配置真实参数时，用例会显示为 skipped，不会误报失败。

## 第一批要补的内容

1. 在 `.env` 填测试环境地址和商户参数。
2. 在 `.env` 配置商户 RSA 私钥（不要提交到 Git）；模板会自动生成 SHA256withRSA 签名。
3. 确认代付返回处理中后，数据库或管理后台订单为处理中。
4. 使用通道 Mock 或真实通道回调，把订单推进成功/失败。
5. 再复制一份测试文件改成 FMP、HM 等通道。

不要一开始测试所有通道。先把“代付 -> 查询 -> 回调 -> 商户通知”跑通。
