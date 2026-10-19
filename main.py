# This is a sample Python script.
from fastapi import FastAPI, Request
from dataclasses import dataclass

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.

#
# def print_hi(name):
#     # Use a breakpoint in the code line below to debug your script.
#     print(f'Hi, {name}')  # Press Ctrl+F8 to toggle the breakpoint.
#
#
# # Press the green button in the gutter to run the script.
# if __name__ == '__main__':
#     print_hi('PyCharm')

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.post("/ppp")
async def ppp(request: Request):
    return 123



@dataclass
class PppChannel:
    order:str
    amount:int
@app.post("/ppp-router")
async def ppp_router(requestbody: PppChannel):
    body=requestbody.order
    return {"响应body": body}