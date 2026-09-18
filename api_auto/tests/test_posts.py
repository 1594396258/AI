# Author:HankQueen
# Date:2026/9/18

from api_auto.utils.data_loader import load_test_data
import pytest
import allure
# 读取测试数据
# ids 参数让 pytest 用用例名作为标识
test_data = load_test_data("test_posts.yaml")
@allure.feature("文章模块")
class TestPosts:

    @allure.story("数据驱动测试")
    @pytest.mark.parametrize("case_name,case", test_data,ids=[d[0] for d in test_data])
    def test_posts(self, base_api, case_name, case):
        """数据驱动：根据 yaml 里的数据自动生成用例"""
        method=case["method"]
        path=case["path"]
        body = case.get("body")
        expected_status = case["expected_status"]
        expected_body = case.get("expected_body")
        with allure.step(f"发送 {method.upper()} 请求：{path}"):
            if method == "get":
                resp = base_api.get(path)
            elif method == "post":
                resp = base_api.post(path, json=body)
            elif method == "put":
                resp = base_api.put(path, json=body)
            elif method == "delete":
                resp = base_api.delete(path)
            else:
                pytest.fail(f"不支持的请求方法: {method}")

        with allure.step(f"断言状态码为 {expected_status}"):
            assert resp.status_code == expected_status, \
                f"用例【{case['case']}】状态码不符，期望 {expected_status}，实际 {resp.status_code}"

        if expected_body:
            with allure.step("断言响应体字段"):
                resp_json = resp.json()
                for key, value in expected_body.items():
                    assert resp_json.get(key) == value, \
                        f"用例【{case['case']}】字段【{key}】不符，期望 {value}，实际 {resp_json.get(key)}"
        # 把响应内容附加到报告里，方便排查问题
        allure.attach(
                    resp.text,
                    name="响应内容",
                    attachment_type=allure.attachment_type.TEXT
                )



    """没有数据驱动的"""
    # def test_get_post_success(self, base_api):
    #     """
    #     正常获取一篇文章
    #     预期：状态码 200，返回 id=1
    #     """
    #     resp = base_api.get("/posts/1")
    #     assert resp.status_code == 200
    #     assert resp.json()["id"] == 1
    #
    # def test_get_post_not_found(self, base_api):
    #     """
    #     获取不存在的文章
    #     预期：状态码 404
    #     """
    #     resp = base_api.get("/posts/99999")
    #     assert resp.status_code == 404
    #
    # def test_create_post(self, base_api):
    #     """
    #     创建一篇文章
    #     预期：状态码 201，返回创建的内容
    #     """
    #     body = {
    #         "title": "测试文章",
    #         "body": "这是内容",
    #         "userId": 1
    #     }
    #     resp = base_api.post("/posts", json=body)
    #     assert resp.status_code == 201
    #     assert resp.json()["title"] == "测试文章"