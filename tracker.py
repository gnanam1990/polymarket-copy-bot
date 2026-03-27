"""
Wallet tracker — polls Polymarket activity API for tracked wallets.
Detects new BUY and SELL trades, pushes events to the copier.
"""
import asyncio
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Set, Dict, List, Callable

import aiohttp

log = logging.getLogger(__name__)


@dataclass
class TradeEvent:
    wallet: str
    market_id: str
    condition_id: str
    asset_id: str
    side: str       # "YES" or "NO"
    action: str     # "BUY" or "SELL"
    price: float
    size: float
    tx_hash: str
    timestamp: int
    title: str = ""


class Tracker:
    """Polls Polymarket activity API for new trades from tracked wallets."""

    def __init__(self, config: dict, on_trade: Callable):
        self.config = config
        self.on_trade = on_trade
        self._wallets: Dict[str, dict] = {}  # address → {name, added_at}
        self._seen: Set[str] = set()
        self._first_run = True
        self._paused = False
        self._running = False

    def add_wallet(self, address: str, name: str = "") -> bool:
        """Add a wallet to track. Returns True if new."""
        addr = address.lower().strip()
        if addr in self._wallets:
            return False
        self._wallets[addr] = {"name": name, "added_at": time.time()}
        log.info(f"Tracking: {name or addr[:14]}")
        return True

    def remove_wallet(self, address: str) -> bool:
        """Remove a wallet from tracking."""
        addr = address.lower().strip()
        if addr in self._wallets:
            del self._wallets[addr]
            log.info(f"Removed: {addr[:14]}")
            return True
        return False

    def get_wallets(self) -> Dict[str, dict]:
        return dict(self._wallets)

    def get_wallet_count(self) -> int:
        return len(self._wallets)

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    @property
    def is_paused(self):
        return self._paused

    async def run(self):
        """Main polling loop."""
        self._running = True
        interval = self.config.get("poll", {}).get("interval_secs", 2)
        limit = self.config.get("poll", {}).get("trades_per_wallet", 20)

        log.info(f"Tracker started — polling every {interval}s")

        async with aiohttp.ClientSession(
            headers={"User-Agent": "PolymarketCopyBot/1.0"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as session:
            while self._running:
                if not self._paused and self._wallets:
                    tasks = [
                        self._poll_wallet(session, addr, limit)
                        for addr in list(self._wallets.keys())
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)

                    if self._first_run:
                        self._first_run = False
                        log.info(f"Seed complete — {len(self._wallets)} wallets, {len(self._seen)} trades cached")

                    # Evict old hashes
                    if len(self._seen) > 50000:
                        self._seen = set(list(self._seen)[-25000:])

                await asyncio.sleep(interval)

    async def _poll_wallet(self, session: aiohttp.ClientSession, wallet: str, limit: int):
        url = f"https://data-api.polymarket.com/activity?user={wallet}&limit={limit}&offset=0"

        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()

            if not isinstance(data, list):
                return

            for trade in data:
                tx = trade.get("tx_hash") or trade.get("transactionHash") or ""
                if not tx:
                    continue

                h = hashlib.md5(tx.encode()).hexdigest()
                if h in self._seen:
                    continue
                self._seen.add(h)

                if self._first_run:
                    continue

                if trade.get("type") != "TRADE":
                    continue

                side_raw = (trade.get("side") or "").upper()
                if side_raw not in ("BUY", "SELL"):
                    continue

                price = _float(trade.get("price"))
                size = _float(trade.get("size"))
                if price <= 0 or size <= 0:
                    continue

                # Normalize price to 0-1 range
                if price > 1:
                    price = price / 100.0  # API sometimes returns cents

                event = TradeEvent(
                    wallet=wallet,
                    market_id=trade.get("conditionId") or trade.get("condition_id") or "",
                    condition_id=trade.get("conditionId") or trade.get("condition_id") or "",
                    asset_id=trade.get("asset") or trade.get("asset_id") or "",
                    side=(trade.get("outcome") or "YES").upper(),
                    action=side_raw,
                    price=price,
                    size=size * price,
                    tx_hash=tx,
                    timestamp=int(trade.get("timestamp") or time.time()),
                    title=trade.get("title") or trade.get("market_slug") or "",
                )

                await self.on_trade(event)

        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log.debug(f"Poll {wallet[:10]}: {e}")

    def stop(self):
        self._running = False


def _float(v, default=0.0):
    try:
        return float(v) if v is not None else default
    except (ValueError, TypeError):
        return default
