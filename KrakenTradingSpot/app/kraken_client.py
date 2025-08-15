# app/kraken_client.py
import time
import hmac
import hashlib
import base64
import httpx
import json
import redis
import urllib.parse
from typing import Dict, Any, Optional, Tuple

from app.config import settings
import logging

logger = logging.getLogger(__name__)


class KrakenClient:
    """
    Kraken API 异步客户端 + 交易对解析与缓存（基于 /0/public/AssetPairs）。
    """

    def __init__(self):
        self.base_url = settings.KRAKEN_API_URL
        self.api_key = settings.KRAKEN_API_KEY
        self.api_secret = settings.KRAKEN_API_SECRET
        self.async_client = httpx.AsyncClient(timeout=30.0)

        # 交易对缓存（来自 /0/public/AssetPairs）
        # 现在使用 Redis 做共享缓存；本地仍保留一份内存副本减少反序列化
        self._pairs_cache_built_at: float = 0.0
        self._pairs_cache_ttl_sec: int = settings.KRAKEN_PAIRS_CACHE_TTL_SEC
        # altname -> pair_key（返回里用的内部键，比如 XXBTZUSD）
        self._alt_to_pairkey: Dict[str, str] = {}
        # wsname -> pair_key（例如 "XBT/USD"）
        self._ws_to_pairkey: Dict[str, str] = {}
        # pair_key -> altname
        self._pairkey_to_alt: Dict[str, str] = {}
        # 动态已知报价币集合（例如 USD、USDT、EUR...），从 AssetPairs 的 wsname 中提取
        self._known_quote_suffixes: set[str] = set()

        # Redis 共享缓存
        try:
            self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
            # 轻触发，若不可用不在构造期中断（仍可走内存+直连刷新）
            self._redis_key = settings.KRAKEN_PAIRS_REDIS_KEY
        except Exception as e:
            logger.info(f"KrakenClient: Redis init failed, fallback to in-memory cache. Err={e}")
            self._redis = None
            self._redis_key = ""

        # 常见别名修正（主要是基础资产）
        self._base_alias = {
            "BTC": "XBT",
            "DOGE": "XDG",
        }
        # 常见分隔符
        self._seps = {"/", "-", "_", ":"}

    # ---------------------- 签名与私有 POST ----------------------
    def _get_signature(self, uri_path: str, data: Dict[str, Any]) -> str:
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data["nonce"]) + postdata).encode()
        message_hash = hashlib.sha256(encoded).digest()
        hmac_digest = hmac.new(
            base64.b64decode(self.api_secret),
            uri_path.encode() + message_hash,
            hashlib.sha512,
        )
        return base64.b64encode(hmac_digest.digest()).decode()

    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        uri_path = f"/0{endpoint}"
        data["nonce"] = str(int(time.time() * 1000))
        headers = {"API-Key": self.api_key, "API-Sign": self._get_signature(uri_path, data)}
        try:
            resp = await self.async_client.post(
                url=f"{self.base_url}{uri_path}",
                headers=headers,
                data=data,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.info(f"HTTP Error: {e.response.status_code} for {e.request.url} - {e.response.text}")
            return {"error": [f"HTTP Error: {e.response.status_code}"], "result": {}}
        except Exception as e:
            logger.info(f"An unexpected error occurred during API call: {e}")
            return {"error": [str(e)], "result": {}}

    # ---------------------- 交易对解析（AssetPairs） ----------------------
    async def _ensure_pairs_cache(self, force: bool = False) -> None:
        """
        使用 Redis 共享 AssetPairs 缓存：
        - 非强制时优先使用内存副本（若未过期）
        - 否则尝试从 Redis 加载
        - 仍不可用或强制刷新时，请求 Kraken 并写回 Redis（带 TTL）
        """
        now = time.time()

        # 1) 内存副本仍在有效期内
        if (not force) and self._alt_to_pairkey and (now - self._pairs_cache_built_at < self._pairs_cache_ttl_sec):
            return

        # 2) 从 Redis 取（如果可用）
        if not force and await self._load_pairs_cache_from_redis():
            return

        # 3) 远端刷新
        try:
            r = await self.async_client.get(f"{self.base_url}/0/public/AssetPairs")
            r.raise_for_status()
            data = r.json()
            result = data.get("result") or {}
            alt_to_pairkey: Dict[str, str] = {}
            ws_to_pairkey: Dict[str, str] = {}
            pairkey_to_alt: Dict[str, str] = {}
            known_quotes: set[str] = set()

            for pair_key, meta in result.items():
                alt = (meta.get("altname") or "").upper()
                ws = (meta.get("wsname") or "").upper()  # 形如 XBT/USD
                if alt:
                    alt_to_pairkey[alt] = pair_key
                    pairkey_to_alt[pair_key] = alt
                if ws:
                    ws_to_pairkey[ws] = pair_key
                    if "/" in ws:
                        try:
                            quote = ws.split("/")[1]
                            if quote:
                                known_quotes.add(quote.upper())
                        except Exception:
                            pass

            # 替换缓存（内存）
            self._alt_to_pairkey = alt_to_pairkey
            self._ws_to_pairkey = ws_to_pairkey
            self._pairkey_to_alt = pairkey_to_alt
            self._pairs_cache_built_at = now
            self._known_quote_suffixes = known_quotes

            # 落 Redis（共享）
            self._save_pairs_cache_to_redis()
            logger.info(f"[AssetPairs] Cache built (remote) with {len(self._alt_to_pairkey)} items.")
        except Exception as e:
            logger.info(f"Failed to refresh AssetPairs cache: {e}")

    async def _load_pairs_cache_from_redis(self) -> bool:
        """尝试从 Redis 加载缓存到内存副本。成功返回 True。
        若 Redis 不可用或无数据，返回 False。"""
        if not self._redis or not self._redis_key:
            return False
        try:
            raw = self._redis.get(self._redis_key)
            if not raw:
                return False
            payload = json.loads(raw)
            alt_to_pairkey = payload.get("alt_to_pairkey") or {}
            ws_to_pairkey = payload.get("ws_to_pairkey") or {}
            pairkey_to_alt = payload.get("pairkey_to_alt") or {}
            known_quotes = payload.get("known_quote_suffixes") or []

            if not alt_to_pairkey:
                return False

            self._alt_to_pairkey = {str(k): str(v) for k, v in alt_to_pairkey.items()}
            self._ws_to_pairkey = {str(k): str(v) for k, v in ws_to_pairkey.items()}
            self._pairkey_to_alt = {str(k): str(v) for k, v in pairkey_to_alt.items()}
            self._pairs_cache_built_at = float(payload.get("built_at") or time.time())
            self._known_quote_suffixes = {str(q).upper() for q in known_quotes if q}
            logger.info(f"[AssetPairs] Cache loaded from Redis with {len(self._alt_to_pairkey)} items.")
            return True
        except Exception as e:
            logger.info(f"[AssetPairs] Failed to load cache from Redis: {e}")
            return False

    def _save_pairs_cache_to_redis(self) -> None:
        """将内存中的映射保存到 Redis，设置 TTL。"""
        if not self._redis or not self._redis_key:
            return
        try:
            payload = {
                "built_at": self._pairs_cache_built_at or time.time(),
                "alt_to_pairkey": self._alt_to_pairkey,
                "ws_to_pairkey": self._ws_to_pairkey,
                "pairkey_to_alt": self._pairkey_to_alt,
                "known_quote_suffixes": sorted(list(self._known_quote_suffixes)),
            }
            self._redis.set(self._redis_key, json.dumps(payload), ex=self._pairs_cache_ttl_sec)
        except Exception as e:
            logger.info(f"[AssetPairs] Failed to save cache to Redis: {e}")

    def _normalize_user_pair(self, s: str) -> str:
        return "".join(ch for ch in s.upper().strip() if ch.isalnum() or ch in self._seps)

    def _normalize_to_altname_candidates(self, user_pair: str) -> Tuple[str, ...]:
        """
        将用户可能的输入生成若干候选 altname：
        - 直接去掉分隔符的版本
        - 若包含分隔符，抽取 base/quote 做别名修正（BTC->XBT, DOGE->XDG）后再拼接
        - 例如：BTC/USD -> XBTUSD；DOGEUSD -> XDGUSD
        """
        raw = self._normalize_user_pair(user_pair)

        # 直接去分隔符候选
        direct = "".join(ch for ch in raw if ch.isalnum())

        cands = [direct]

        # 分隔符拆分候选
        for sep in self._seps:
            if sep in raw:
                parts = [p for p in raw.split(sep) if p]
                if len(parts) == 2:
                    base, quote = parts[0], parts[1]
                    base = self._base_alias.get(base, base)  # BTC->XBT, DOGE->XDG
                    cands.append(f"{base}{quote}")
                    cands.append(f"{base}/{quote}")  # 用于 wsname 匹配
                break

        # 常见别名修正（无分隔符时的 base 替换）
        if len(direct) >= 6 and self._known_quote_suffixes:
            # 尝试按“已知报价币后缀”拆分，例如 XBTUSD 的 USD
            for q in sorted(self._known_quote_suffixes, key=len, reverse=True):
                if direct.endswith(q) and len(direct) > len(q):
                    base = direct[: len(direct) - len(q)]
                    base = self._base_alias.get(base, base)
                    cands.append(f"{base}{q}")
                    break

        # 去重，保序
        seen, uniq = set(), []
        for c in cands:
            if c not in seen:
                seen.add(c)
                uniq.append(c)
        return tuple(uniq)

    async def resolve_altname(self, user_pair: str) -> Optional[str]:
        """
        将用户输入解析为 Kraken 官方 altname（用于请求参数）。
        若失败，将强制刷新缓存再尝试一次。
        """
        await self._ensure_pairs_cache(force=False)
        for attempt in (0, 1):
            cands = self._normalize_to_altname_candidates(user_pair)
            for c in cands:
                # 直接 altname 命中
                if c in self._alt_to_pairkey:
                    return c
                # wsname 形如 XBT/USD
                if "/" in c and c in self._ws_to_pairkey:
                    pair_key = self._ws_to_pairkey[c]
                    return self._pairkey_to_alt.get(pair_key)
            # 强制刷新后重试一次
            await self._ensure_pairs_cache(force=True)
        return None

    # ---------------------- 私有/公共接口封装 ----------------------
    async def add_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/private/AddOrder", order_data)

    async def amend_order(self, amend_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/private/AmendOrder", amend_data)

    async def cancel_order(self, cancel_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._post("/private/CancelOrder", cancel_data)

    async def query_orders(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        query_data.setdefault("trades", True)
        return await self._post("/private/QueryOrders", query_data)

    async def get_ticker(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取市场价格（公共端点）。
        输入：{"pair": "<任意用户写法>"}
        输出：{"pair_key": "<内部键>", "altname": "<标准名>", "result": <行情对象>}
        """
        pair = ticker_data.get("pair")
        if not pair:
            return {"error": ["Pair is required for get_ticker"], "result": {}}

        alt = await self.resolve_altname(pair)
        if not alt:
            return {"error": [f"Unable to resolve pair: {pair}"], "result": {}}

        try:
            resp = await self.async_client.get(
                f"{self.base_url}/0/public/Ticker?pair={alt}"
            )
            resp.raise_for_status()
            payload = resp.json()
            result = payload.get("result") or {}
            if not result:
                return {"error": ["Empty ticker result"], "result": {}}

            # Kraken 会用内部 key 作为返回键，取第一个即可（我们只请求一个）
            pair_key = next(iter(result.keys()))
            return {
                "error": [],
                "pair_key": pair_key,
                "altname": alt,
                "result": result[pair_key],
            }
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    # ---------------------- WS Token 获取（私有 WS 订阅需要） ----------------------
    async def get_ws_token(self) -> Dict[str, Any]:
        try:
            return await self._post("/private/GetWebSocketsToken", {})
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    # ---------------------- 账户与订单查询（私有接口） ----------------------
    async def get_open_orders(self) -> Dict[str, Any]:
        """OpenOrders: 返回当前未结订单。"""
        try:
            return await self._post("/private/OpenOrders", {"trades": True})
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    async def get_account_balance(self) -> Dict[str, Any]:
        try:
            return await self._post("/private/Balance", {})
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    async def get_trade_balance(self, asset: str = "ZUSD") -> Dict[str, Any]:
        try:
            return await self._post("/private/TradeBalance", {"asset": asset})
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    async def get_trades_history(self, start: Optional[int] = None, end: Optional[int] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"trades": True}
        if start is not None:
            payload["start"] = start
        if end is not None:
            payload["end"] = end
        try:
            return await self._post("/private/TradesHistory", payload)
        except Exception as e:
            return {"error": [str(e)], "result": {}}

    async def get_asset_pairs(self) -> Dict[str, Any]:
        """公共端点获取可交易对。"""
        try:
            r = await self.async_client.get(f"{self.base_url}/0/public/AssetPairs")
            r.raise_for_status()
            return r.json()
        except Exception as e:
            return {"error": [str(e)], "result": {}}
