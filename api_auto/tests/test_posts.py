# Author:HankQueen
# Date:2026/9/18
class TestPosts:

    def test_get_post_success(self, base_api):
        """
        正常获取一篇文章
        预期：状态码 200，返回 id=1
        """
        resp = base_api.get("/posts/1")
        assert resp.status_code == 200
        assert resp.json()["id"] == 1

    def test_get_post_not_found(self, base_api):
        """
        获取不存在的文章
        预期：状态码 404
        """
        resp = base_api.get("/posts/99999")
        assert resp.status_code == 404

    def test_create_post(self, base_api):
        """
        创建一篇文章
        预期：状态码 201，返回创建的内容
        """
        body = {
            "title": "测试文章",
            "body": "这是内容",
            "userId": 1
        }
        resp = base_api.post("/posts", json=body)
        assert resp.status_code == 201
        assert resp.json()["title"] == "测试文章"