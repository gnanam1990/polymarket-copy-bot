"""
Polymarket Copy Trading Bot — Entry Point.

Usage:
    python bot.py                  # start with default config
    python bot.py --config my.toml # custom config file

Dashboard: http://localhost:8080
"""
import os
import sys
import asyncio
import signal
import logging
import threading

try:
    import tomli
except ImportError:
    import tomllib as tomli

from tracker import Tracker
from copier import Copier
from positions import Positions
from prices import Prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("bot")


def load_config(path: str = "config.toml") -> dict:
    if not os.path.exists(path):
        if os.path.exists("config.example.toml"):
            log.warning(f"{path} not found — copying from config.example.toml")
            import shutil
            shutil.copy("config.example.toml", path)
        else:
            log.error(f"No config file found. Create {path}")
            sys.exit(1)

    with open(path, "rb") as f:
        return tomli.load(f)


async def main():
    # Parse args
    config_path = "config.toml"
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_path = sys.argv[idx + 1]

    config = load_config(config_path)
    mode = "PAPER" if config["mode"].get("paper", True) else "LIVE"

    print(f"""
╔══════════════════════════════════════╗
║   🔄 Polymarket Copy Trading Bot    ║
║   Mode: {mode:6s}                      ║
║   Dashboard: http://localhost:{config.get('dashboard',{}).get('port',8080):<5} ║
╚══════════════════════════════════════╝
""")

    # Initialize components
    positions = Positions()
    copier = Copier(config, positions)
    tracker = Tracker(config, copier.handle_trade)
    prices = Prices(positions)

    # Load wallets from config
    for addr in config.get("wallets", {}).get("track", []):
        tracker.add_wallet(addr.strip())

    log.info(f"Tracking {tracker.get_wallet_count()} wallets")
    log.info(f"Mode: {mode} | Balance: ${copier.balance:.2f}")
    log.info(f"Filters: ROI>{config['copy'].get('min_profit_pct',30)}% | Entry {config['copy'].get('min_entry_price',0.03)*100:.0f}¢-{config['copy'].get('max_entry_price',0.70)*100:.0f}¢ | Max {config['copy'].get('max_positions',20)} positions")

    # Start dashboard in background thread
    if config.get("dashboard", {}).get("enabled", True):
        from dashboard import create_app
        app = create_app(tracker, copier, positions)
        port = config["dashboard"].get("port", 8080)

        def run_dash():
            app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

        dash_thread = threading.Thread(target=run_dash, daemon=True)
        dash_thread.start()
        log.info(f"Dashboard: http://localhost:{port}")

    # Start all async services
    copier._log_event("STARTUP", f"Bot started — {mode} mode, {tracker.get_wallet_count()} wallets, ${copier.balance:.2f}")

    shutdown = asyncio.Event()

    def handle_signal(sig, frame):
        log.info("Shutting down...")
        shutdown.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    tasks = [
        asyncio.create_task(tracker.run()),
        asyncio.create_task(copier.run_settlement()),
        asyncio.create_task(prices.run()),
    ]

    log.info("All services running — press Ctrl+C to stop")

    await shutdown.wait()

    tracker.stop()
    copier.stop()
    prices.stop()
    for t in tasks:
        t.cancel()

    log.info("Goodbye")


if __name__ == "__main__":
    asyncio.run(main())
