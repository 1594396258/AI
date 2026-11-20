# Author:HankQueen
# Date:2026/10/30
from cryptography.hazmat.primitives import hashes, serialization, padding
from cryptography.hazmat.primitives.asymmetric import rsa
import base64
from cryptography.hazmat.primitives.asymmetric import padding
from loguru import logger
import json


def rsa_256_verify(sign, data, public_key):
    public_key = serialization.load_pem_public_key(public_key.encode("utf-8"))  # 转字节
    try:
        signed_data = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        public_key.verify(base64.b64decode(sign), signed_data, padding.PKCS1v15(),
                          hashes.SHA256())  # base64.b64decode(sign)对签名值进行解码
        return True
    except Exception as e:
        logger.error(f"回调验签失败: {e}")
        return False


def rsa_256_sign(data,private_key):
    try:
        private_key_bytes = serialization.load_pem_private_key(private_key.encode("utf-8"))  # 转字节
        sign_data =  json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

        private_key_bytes.sign(sign_data, padding.PKCS1v15(),hashes.SHA256())
    except Exception as e:
        logger.error(f"回调签名异常: {e}")
        return False


