"""
Live price engine — WebSocket bid/ask + REST fallback for open positions.
"""
import asyncio
import json
import logging
from typing import Dict, Set

import aiohttp

from positions import Positions

log = logging.getLogger(__name__)


class Prices:
    """Streams live bid/ask/mid for open positions."""

    def __init__(self, positions: Positions):
        self.pos = positions
        self._cache: Dict[str, dict] = {}
        self._running = False

    async def run(self):
        self._running = True
        await asyncio.gather(
            self._run_ws(),
            self._run_rest(),
            self._apply_loop(),
        )

    async def _run_ws(self):
        """WebSocket price stream."""
        while self._running:
            try:
                import websockets
                url = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
                async with websockets.connect(url, ping_interval=30) as ws:
                    log.info("Price WebSocket connected")
                    subscribed: Set[str] = set()

                    while self._running:
                        # Subscribe to new position assets
                        assets, markets = [], []
                        for p in self.pos.get_open():
                            aid = p.get("asset_id", "")
                            cid = p.get("condition_id", "")
                            if aid and aid not in subscribed:
                                assets.append(aid)
                                if cid:
                                    markets.append(cid)
                                subscribed.add(aid)

                        if assets:
                            await ws.send(json.dumps({
                                "auth": {},
                                "type": "subscribe",
                                "markets": list(set(markets)),
                                "assets_ids": assets,
                            }))

                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                            self._parse(msg)
                        except asyncio.TimeoutError:
                            pass

            except Exception as e:
                log.debug(f"Price WS: {e}")
                await asyncio.sleep(5)

    def _parse(self, text: str):
        try:
            data = json.loads(text)
            items = data if isinstance(data, list) else [data]
            for item in items:
                aid = item.get("asset_id") or item.get("token_id")
                if not aid:
                    continue
                bid = _num(item.get("best_bid"))
                ask = _num(item.get("best_ask"))
                mid = _num(item.get("mid") or item.get("price"))
                if mid is None and bid and ask:
                    mid = (bid + ask) / 2
                entry = self._cache.get(aid, {})
                if bid:
                    entry["bid"] = bid
                if ask:
                    entry["ask"] = ask
                if mid:
                    entry["mid"] = mid
                self._cache[aid] = entry
        except:
            pass

    async def _run_rest(self):
        """REST fallback for stale assets."""
        await asyncio.sleep(5)
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            while self._running:
                await asyncio.sleep(5)
                for p in self.pos.get_open():
                    aid = p.get("asset_id", "")
                    if not aid or aid in self._cache:
                        continue
                    try:
                        url = f"https://clob.polymarket.com/book?token_id={aid}"
                        async with session.get(url) as resp:
                            if resp.status != 200:
                                continue
                            data = await resp.json()
                        bid = _num(data.get("bids", [{}])[0].get("price")) if data.get("bids") else None
                        ask = _num(data.get("asks", [{}])[0].get("price")) if data.get("asks") else None
                        mid = (bid + ask) / 2 if bid and ask else None
                        entry = {}
                        if bid:
                            entry["bid"] = bid
                        if ask:
                            entry["ask"] = ask
                        if mid:
                            entry["mid"] = mid
                        if entry:
                            self._cache[aid] = entry
                    except:
                        pass
                    await asyncio.sleep(0.5)

    async def _apply_loop(self):
        """Push cached prices to positions every 500ms."""
        while self._running:
            await asyncio.sleep(0.5)
            for aid, prices in self._cache.items():
                bid = prices.get("bid", 0)
                ask = prices.get("ask", 0)
                mid = prices.get("mid", 0)
                if any(v > 0 for v in (bid, ask, mid)):
                    self.pos.update_prices(aid, bid, ask, mid)

    def stop(self):
        self._running = False


def _num(v):
    if v is None:
        return None
    try:
        f = float(v) if not isinstance(v, (int, float)) else v
        return f if 0 < f <= 1 else None
    except:
        return None
