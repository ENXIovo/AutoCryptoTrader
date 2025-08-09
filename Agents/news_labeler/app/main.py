from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
import logging
from .config import settings
from .redis_utils import new_redis

app = FastAPI(title="News Labeler API")

logger = logging.getLogger(__name__)
r = new_redis()


@app.get("/health")
def health():
    try:
        pong = r.ping()
        return {"status": "ok", "redis": pong}
    except Exception as e:
        return {"status": "degraded", "error": str(e)}


@app.get("/top-news")
def get_top_news(limit: int = 20) -> List[Dict[str, Any]]:
    try:
        keys = r.zrevrange(settings.redis_zset_key, 0, max(0, limit - 1))
        results = []
        for key in keys:
            k = key.decode()
            h = r.hgetall(f"{settings.redis_hash_prefix}{k}")
            entry = {kk.decode(): vv.decode() for kk, vv in h.items()}
            entry["key"] = k
            results.append(entry)
        return results
    except Exception as e:
        logger.exception("top-news failed: %s", e)
        raise HTTPException(status_code=503, detail="service unavailable")


@app.get("/news/{key}")
def get_news_detail(key: str):
    try:
        hkey = f"{settings.redis_hash_prefix}{key}"
        if not r.exists(hkey):
            raise HTTPException(status_code=404, detail="Not found")
        h = r.hgetall(hkey)
        return {k.decode(): v.decode() for k, v in h.items()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("get-news failed: %s", e)
        raise HTTPException(status_code=503, detail="service unavailable")
