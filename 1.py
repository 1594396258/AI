# Author:HankQueen
# Date:2026/9/22
#
# from pathlib import Path
from requests import Session


# WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
# print(WORKSPACE_ROOT)
# import  requests
# workspace_id='49904404'
# story_id='1149904404001120409'
# token='77c0b8254745c083a1aa3a1db740b77a5d63dbf8'
# headers = {"Authorization": f"Bearer {token}"}
# res=requests.get(url=f'https://api.tapd.cn/stories?workspace_id={workspace_id}&id={story_id}',headers=headers)
# print(res.text)



#
session = Session()
# base_url = "http://127.0.0.1:8000"
# re=session.request(method='POST',url='http://127.0.0.1:8000/try/post',json={'method':"try post"})
# print(re.text)
# #
# re1=session.request(method='get',url=base_url+'/try/download/image')
# print(re1.text)
#
#
# re2=session.request(method='get',url=base_url+'/try/search',params={'query':'python'})
# print(re2.text
#
#
#
data={
  "request": {
    "code": "string",
    "message": "string",
    "trxDate": "string",
    "trxAmount": "string",
    "tradeAmount": "string",
    "trxState": "string",
    "originalMsgId": "string",
    "orderNo": "string",
    "attach": "string",
    "mchId": "string",
    "receiveBankAcct": "string",
    "receiveBankCardNo": "string",
    "transactionId": "string",
    "reversal": "string",
    "bankId": "string",
    "bankName": "string",
    "aaa":"string",
  },
  "signature": "111111"}

re=session.request(method='POST',url='http://127.0.0.1:1920/receive_notify',json=data)
print(re.text)




#
# url='https://api.sandbox.telex.money/v1/remitters/requirements'
#
# headers={"Authorization": "Bearer tlx_test_3rAuC6P9mNAb0f5eZ8myAMBGY0gSJtzlaqITmXbt"}
#
# response=session.request(method='get',url=url,params=data,headers=headers)