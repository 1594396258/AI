# Author:HankQueen
# Date:2026/10/16

import json
from  loguru import logger
data={'amount': None, 'create_status': 'pending', 'delay_ms': 0, 'query_status': 'pending', 'response_status_code': 200, 'transaction_id': None}


logger.debug(json.dumps(data))