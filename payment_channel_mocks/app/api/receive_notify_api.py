# Author:HankQueen
# Date:2026/10/30
import fastapi
from pydantic import BaseModel
from loguru import logger
import json
from payment_channel_mocks.utils.sign import rsa_256_verify
from payment_channel_mocks.config.channel_config import MERCHANT_PUBLIC_KEY

app=fastapi.FastAPI()  #创建对象

class Request(BaseModel):
    code: str
    message: str
    trxDate: str
    trxAmount: str
    tradeAmount: str
    trxState: str
    originalMsgId: str
    orderNo: str
    attach: str
    mchId: str
    receiveBankAcct: str
    receiveBankCardNo: str
    transactionId: str
    reversal: str
    bankId: str
    bankName: str


class NotifyRequest(BaseModel):# 数据模型，用于fastapi解析
    request:Request
    signature:str



@app.post("/receive_notify")
async def receive_notify(body: NotifyRequest):
    logger.debug(f"接收到通知信息{body}")
    try:
        signature=body.signature
        body=body.request.model_dump()  # 转字典
        logger.info(f"解析签名信息和请求体{signature},{body}")
        sign=rsa_256_verify(signature,body,MERCHANT_PUBLIC_KEY)
    except json.decoder.JSONDecodeError as e:
        pass



