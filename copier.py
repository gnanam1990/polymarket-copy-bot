"""
Trade copier — filters signals, executes paper or live trades, handles settlement.
"""
import asyncio
import random
import hashlib
import time
import logging
import os
from typing import Dict

import aiohttp

from tracker import TradeEvent
from positions import Positions

log = logging.getLogger(__name__)


class Copier:
    """Filters trade signals and executes copies."""

    def __init__(self, config: dict, positions: Positions):
        self.config = config
        self.pos = positions
        self._balance = config["mode"].get("paper_balance", 1000.0)
        self._paused = False
        self._events: list = []  # feed for dashboard
        self._market_dedup: Dict[str, float] = {}  # market+side → last copy time
        self._realized_today = 0.0
        self._running = False

        # Load balance from existing positions
        if os.path.exists("data/balance.txt"):
            try:
                self._balance = float(open("data/balance.txt").read().strip())
            except:
                pass

    @property
    def balance(self):
        return self._balance

    @property
    def is_paper(self):
        return self.config["mode"].get("paper", True)

    def _save_balance(self):
        os.makedirs("data", exist_ok=True)
        with open("data/balance.txt", "w") as f:
            f.write(f"{self._balance:.2f}")

    def _log_event(self, event_type: str, message: str):
        entry = {
            "time": time.strftime("%H:%M:%S"),
            "type": event_type,
            "message": message,
        }
        self._events.append(entry)
        if len(self._events) > 500:
            self._events = self._events[-500:]

    def get_events(self, limit: int = 100) -> list:
        return self._events[-limit:][::-1]

    async def handle_trade(self, event: TradeEvent):
        """Called by tracker when a new trade is detected."""
        if self._paused:
            return

        self._log_event("DETECT", f"{event.wallet[:10]} {event.action} {event.side} @{event.price*100:.1f}c ${event.size:.2f} {event.title[:30]}")

        if event.action == "SELL":
            await self._handle_sell(event)
            return

        if event.action == "BUY":
            await self._handle_buy(event)

    async def _handle_buy(self, event: TradeEvent):
        """Filter and execute a BUY copy."""
        price = event.price
        cfg = self.config["copy"]

        # Filter: price range
        min_price = cfg.get("min_entry_price", 0.03)
        max_price = cfg.get("max_entry_price", 0.70)
        if price < min_price or price > max_price:
            return

        # Filter: profit margin
        roi = (1.0 - price) / price * 100.0
        min_profit = cfg.get("min_profit_pct", 30.0)
        if roi < min_profit:
            return

        # Filter: max positions
        max_pos = cfg.get("max_positions", 20)
        if self.pos.get_open_count() >= max_pos:
            return

        # Filter: already hold this market+side
        if self.pos.find(event.market_id, event.side):
            return

        # Filter: market+side time dedup (prevent duplicate fills from partial orders)
        dedup_key = f"{event.market_id}|{event.side}"
        dedup_window = cfg.get("dedup_window_secs", 60)
        now = time.time()
        if now - self._market_dedup.get(dedup_key, 0) < dedup_window:
            return
        self._market_dedup[dedup_key] = now

        # Clean old dedup entries
        if len(self._market_dedup) > 5000:
            cutoff = now - dedup_window * 2
            self._market_dedup = {k: v for k, v in self._market_dedup.items() if v > cutoff}

        size = cfg.get("position_size", 10.0)
        ev = roi  # simplified — in production use wallet WR for proper EV calc

        self._log_event("COPY", f"{event.side} @{price*100:.1f}c ${size:.2f} ROI=+{roi:.0f}% {event.title[:30]}")

        if self.is_paper:
            await self._paper_fill(event, price, size)
        else:
            await self._live_fill(event, price, size)

    async def _paper_fill(self, event: TradeEvent, price: float, size: float):
        """Simulate a paper fill."""
        await asyncio.sleep(random.uniform(0.05, 0.15))  # simulate latency

        # 5% FOK rejection
        if random.random() < 0.05:
            self._log_event("REJECT", f"FOK failed: {event.title[:30]}")
            return

        # Slippage
        slip = random.uniform(0.005, 0.02)
        fill_price = min(0.99, price * (1 + slip))
        gas = random.uniform(0.05, 0.20)
        cost = size + gas

        if cost > self._balance:
            self._log_event("SKIP", f"Insufficient balance: ${self._balance:.2f}")
            return

        self._balance -= cost
        self._save_balance()

        self.pos.open(
            wallet=event.wallet,
            market_id=event.market_id,
            asset_id=event.asset_id,
            condition_id=event.condition_id,
            side=event.side,
            size=size,
            entry_price=fill_price,
            title=event.title,
            fees=gas,
        )

        self._log_event("FILL", f"{event.side} @{fill_price*100:.1f}c ${size:.2f} bal=${self._balance:.2f}")

    async def _live_fill(self, event: TradeEvent, price: float, size: float):
        """Execute a real CLOB order."""
        self._log_event("LIVE", f"Would execute: {event.side} @{price*100:.1f}c ${size:.2f}")
        # TODO: Implement py-clob-client FOK order
        # from py_clob_client.client import ClobClient
        # client = ClobClient(...)
        # order = client.create_and_post_order(...)
        log.warning("Live trading not yet implemented")

    async def _handle_sell(self, event: TradeEvent):
        """Detect whale exits — alert if we hold the same position."""
        pos = self.pos.find(event.market_id, event.side)
        if pos:
            self._log_event("WHALE_EXIT", f"⚠️ {event.wallet[:10]} sold {event.side} {event.title[:30]} — you hold ${pos['size']:.2f}")

    async def run_settlement(self):
        """Check for market resolution every 30 seconds."""
        self._running = True
        await asyncio.sleep(10)
        log.info("Settlement loop started")

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            while self._running:
                await asyncio.sleep(30)
                positions = self.pos.get_open()
                for p in positions:
                    try:
                        result = await self._check_resolution(session, p)
                        if result == "win":
                            settled = self.pos.settle(p["id"], True)
                            if settled:
                                payout = settled["size"] / settled["entry_price"] if settled["entry_price"] > 0 else settled["size"]
                                self._balance += payout
                                self._realized_today += settled["pnl"]
                                self._save_balance()
                                self._log_event("WIN", f"✅ {p['side']} {p['title'][:25]} +${settled['pnl']:.2f} bal=${self._balance:.2f}")
                        elif result == "loss":
                            settled = self.pos.settle(p["id"], False)
                            if settled:
                                self._realized_today += settled["pnl"]
                                self._log_event("LOSS", f"❌ {p['side']} {p['title'][:25]} -${abs(settled['pnl']):.2f} bal=${self._balance:.2f}")
                    except Exception as e:
                        log.debug(f"Settlement check: {e}")
                    await asyncio.sleep(0.5)

    async def _check_resolution(self, session, pos) -> str:
        """Check if a market has resolved. Returns 'win', 'loss', or 'open'."""
        cid = pos.get("condition_id") or pos.get("market_id")
        if not cid:
            return "open"

        url = f"https://clob.polymarket.com/markets/{cid}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return "open"
                data = await resp.json()

            if not data.get("closed"):
                return "open"

            for token in data.get("tokens", []):
                if token.get("winner"):
                    outcome = (token.get("outcome") or "").upper()
                    our_side = pos["side"].upper()
                    return "win" if outcome == our_side else "loss"

            return "open"
        except:
            return "open"

    @property
    def realized_today(self):
        return self._realized_today

    def pause(self):
        self._paused = True
        self._log_event("CONTROL", "⏸ Trading paused")

    def resume(self):
        self._paused = False
        self._log_event("CONTROL", "▶️ Trading resumed")

    def stop(self):
        self._running = False
