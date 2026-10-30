# Author:HankQueen
# Date:2026/10/30
import fastapi
from pydantic import BaseModel

class TryPost(BaseModel):
    method: str
app=fastapi.FastAPI()




@app.get("/heath")
async def heath():
    return {'code':'200','status':'OK'}



# 动态路径查询：用于下载资源
@app.get("/try/download/{path}")
async def download(path: str):
    return {'code':'200','status':'下载成功'}

#查询参数
@app.get("/try/search")
async def search(query: str):
    return {'code':'200','status':'查询成功'}

#json请求体，需要结合pydantic模拟的basemodel使用，因为fastapi接收json参数是需要结构化数据
@app.post("/try/post")
async def try_post(method:TryPost):
    return {'code':'200','status':'OK','message':method.method}