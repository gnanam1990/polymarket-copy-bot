"""
Position manager — tracks open/closed positions with live PnL.
"""
import threading
import logging
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "positions.json")


class Positions:
    """Thread-safe position tracking with persistence."""

    def __init__(self):
        self._positions: Dict[str, dict] = {}
        self._trades: List[dict] = []
        self._counter = 0
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        """Load positions from disk."""
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, "r") as f:
                    data = json.load(f)
                self._positions = {p["id"]: p for p in data.get("positions", []) if p.get("status") == "OPEN"}
                self._trades = data.get("trades", [])[-1000:]  # keep last 1000
                log.info(f"Loaded {len(self._positions)} open positions, {len(self._trades)} trades")
        except Exception as e:
            log.warning(f"Load positions: {e}")

    def _save(self):
        """Save positions to disk."""
        try:
            os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
            all_pos = list(self._positions.values())
            with open(DATA_FILE, "w") as f:
                json.dump({"positions": all_pos, "trades": self._trades[-1000:]}, f, indent=2)
        except Exception as e:
            log.warning(f"Save positions: {e}")

    def open(self, wallet: str, market_id: str, asset_id: str, condition_id: str,
             side: str, size: float, entry_price: float, title: str = "",
             fees: float = 0) -> str:
        """Open a new position. Returns position ID."""
        with self._lock:
            self._counter += 1
            pid = f"p-{int(datetime.now(timezone.utc).timestamp() * 1000)}-{self._counter}"

            pos = {
                "id": pid,
                "wallet": wallet,
                "market_id": market_id,
                "asset_id": asset_id,
                "condition_id": condition_id,
                "side": side,
                "size": round(size, 2),
                "entry_price": round(entry_price, 6),
                "bid": 0.0,
                "ask": 0.0,
                "mid": 0.0,
                "pnl": 0.0,
                "status": "OPEN",
                "title": title,
                "opened_at": datetime.now(timezone.utc).isoformat(),
                "settled_at": "",
            }
            self._positions[pid] = pos

            self._trades.append({
                "action": "BUY",
                "wallet": wallet,
                "side": side,
                "price": round(entry_price, 4),
                "size": round(size, 2),
                "fees": round(fees, 2),
                "title": title[:50],
                "time": datetime.now(timezone.utc).isoformat(),
            })

            self._save()
            return pid

    def update_prices(self, asset_id: str, bid: float, ask: float, mid: float):
        """Update live prices for positions with matching asset_id."""
        with self._lock:
            for pos in self._positions.values():
                if pos["asset_id"] == asset_id and pos["status"] == "OPEN":
                    pos["bid"] = round(bid, 4)
                    pos["ask"] = round(ask, 4)
                    pos["mid"] = round(mid, 4)
                    if pos["entry_price"] > 0 and mid > 0:
                        shares = pos["size"] / pos["entry_price"]
                        pos["pnl"] = round(shares * (mid - pos["entry_price"]), 4)

    def settle(self, pid: str, is_win: bool) -> Optional[dict]:
        """Settle a position. Returns settled position with realized PnL."""
        with self._lock:
            pos = self._positions.get(pid)
            if not pos:
                return None

            entry = pos["entry_price"]
            size = pos["size"]

            if is_win:
                payout = size / entry if entry > 0 else size
                pos["pnl"] = round(payout - size, 4)
                pos["status"] = "WON"
            else:
                pos["pnl"] = round(-size, 4)
                pos["status"] = "LOST"

            pos["settled_at"] = datetime.now(timezone.utc).isoformat()

            self._trades.append({
                "action": "WON" if is_win else "LOST",
                "wallet": pos["wallet"],
                "side": pos["side"],
                "price": 1.0 if is_win else 0.0,
                "size": size,
                "pnl": pos["pnl"],
                "title": pos["title"][:50],
                "time": pos["settled_at"],
            })

            result = dict(pos)
            del self._positions[pid]
            self._save()
            return result

    def close(self, pid: str, sell_price: float) -> Optional[dict]:
        """Close position by selling (before resolution)."""
        with self._lock:
            pos = self._positions.get(pid)
            if not pos:
                return None

            entry = pos["entry_price"]
            size = pos["size"]
            proceeds = size * (sell_price / entry) if entry > 0 else size
            pos["pnl"] = round(proceeds - size, 4)
            pos["status"] = "SOLD"
            pos["settled_at"] = datetime.now(timezone.utc).isoformat()

            self._trades.append({
                "action": "SOLD",
                "wallet": pos["wallet"],
                "side": pos["side"],
                "price": sell_price,
                "size": size,
                "pnl": pos["pnl"],
                "title": pos["title"][:50],
                "time": pos["settled_at"],
            })

            result = dict(pos)
            del self._positions[pid]
            self._save()
            return result

    def find(self, market_id: str, side: str) -> Optional[dict]:
        """Find an open position by market+side."""
        with self._lock:
            for pos in self._positions.values():
                if pos["market_id"] == market_id and pos["side"] == side and pos["status"] == "OPEN":
                    return dict(pos)
        return None

    def get_open(self) -> List[dict]:
        with self._lock:
            return [dict(p) for p in self._positions.values() if p["status"] == "OPEN"]

    def get_open_count(self) -> int:
        with self._lock:
            return sum(1 for p in self._positions.values() if p["status"] == "OPEN")

    def get_total_unrealized(self) -> float:
        with self._lock:
            return sum(p.get("pnl", 0) for p in self._positions.values() if p["status"] == "OPEN")

    def get_trades(self, limit: int = 50) -> List[dict]:
        return self._trades[-limit:][::-1]
