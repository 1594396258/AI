# Author:HankQueen
# Date:2026/9/21
# Redis 连接配置
REDIS_CONFIG = {
    "host": "192.168.1.65",
    "port": 6379,
    "password": "jrg_market.123",
    "db": 8,
    "decode_responses": True,
    # The test Redis/proxy does not support the RESP3 HELLO handshake.
    "protocol": 2  # 兼容低版本 Redis
}
