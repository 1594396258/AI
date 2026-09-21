# Author:HankQueen
# Date:2026/9/21
import redis
import logging
import json
from api_auto.config.redis_config import REDIS_CONFIG

logger = logging.getLogger(__name__)

# 验证码 key 前缀
CAPTCHA_KEY_PREFIX = "userService:login:verifyCode:comm:"


def get_captcha_from_redis(request_id: str) -> str:
    """
    从 Redis 获取验证码
    key = userService:login:verifyCode:comm:{requestId}
    """
    client = redis.Redis(**REDIS_CONFIG)
    key = f"{CAPTCHA_KEY_PREFIX}{request_id}"
    captcha = client.get(key)
    # The service stores the captcha as a JSON string, so Redis returns
    # values such as ``"6p8a"``. Return the actual captcha text to callers.
    if isinstance(captcha, str):
        try:
            decoded = json.loads(captcha)
        except json.JSONDecodeError:
            decoded = captcha
        if isinstance(decoded, str):
            captcha = decoded
    if captcha:
        logger.info(f"从 Redis 获取验证码成功: {captcha}")
    else:
        logger.warning(f"Redis 中未找到验证码, key={key}")
    client.close()
    return captcha
