# Author:HankQueen
# Date:2026/9/22
#
# from pathlib import Path
# WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
# print(WORKSPACE_ROOT)
import  requests
workspace_id='49904404'
story_id='1149904404001120409'
token='77c0b8254745c083a1aa3a1db740b77a5d63dbf8'
headers = {"Authorization": f"Bearer {token}"}
res=requests.get(url=f'https://api.tapd.cn/stories?workspace_id={workspace_id}&id={story_id}',headers=headers)
print(res.text)