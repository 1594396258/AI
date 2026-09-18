# Author:HankQueen
# Date:2026/9/18
import hashlib

# 固定密码密钥
USER_PASSWORD_KEY = "3b7bd52387baff9fb4dd8433cce4961c"  #(密文密码由：MD5（用户名+明文密码+固定密钥）)

def md5(text:str)->str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()

def encrypt_password(username:str,plain_password:str)->str:
    """ 密码加密规则：MD5(用户名 + 明文密码 + 固定密钥)"""
    raw=username+plain_password+USER_PASSWORD_KEY
    return md5(raw)


