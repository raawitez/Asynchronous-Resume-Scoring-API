import os
import json
import redis
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

def _create_redis_client():
    url = os.getenv("REDIS_URL")
+
    client_kwargs = {
        "decode_responses": True,
        "socket_timeout": 3.0,
        "socket_connect_timeout": 3.0,
        "retry_on_timeout": True,
        "health_check_interval": 30
    }

    if url:
        return redis.from_url(url, **client_kwargs)
    return redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        db=0,
        **client_kwargs
    )

redis_client = _create_redis_client()

def check_redis() -> bool:
    try:
        redis_client.ping()
        logger.info("Redis connected successfully")
        return True
    except Exception as e:
        logger.warning(f"Redis unavailable: {e}")
        return False

def get_cache(key: str):
    try:
        value = redis_client.get(key)
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    except Exception as e:
        logger.warning(f"Redis GET error [{key}]: {e}")
        return None

def set_cache(key: str, value, ttl: int=300) -> bool:
    try:
        serialized_value = value if isinstance(value, str) else json.dumps(value)
        redis_client.setex(key, ttl, serialized_value)
        return True
    except Exception as e:
        logger.warning(f"Redis SET error [{key}]: {e}")
        return False
    
def delete_cache(key: str) -> bool:
    try:
        redis_client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Redis DELETE error [{key}]: {e}")
        return False

check_redis()