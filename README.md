<div align="center">

# Polymarket Copy Trading Bot

**Automatically copy trades from top Polymarket wallets with smart filtering, paper trading, and a real-time dashboard.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge)](LICENSE)
[![Polymarket](https://img.shields.io/badge/Polymarket-CLOB-6366f1?style=for-the-badge)](https://polymarket.com)
[![Flask](https://img.shields.io/badge/Flask-Dashboard-000000?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![asyncio](https://img.shields.io/badge/asyncio-Async%20Engine-f59e0b?style=for-the-badge)](https://docs.python.org/3/library/asyncio.html)

</div>

---

## Architecture Overview

```mermaid
graph TB
    subgraph Input["🎯 Wallet Sources"]
        A1[Config File]
        A2[Dashboard UI]
        A3[REST API]
    end

    subgraph Core["⚙️ Core Engine"]
        B[Tracker] -->|Trade Events| C[Copier]
        C -->|Open Position| D[Positions]
        E[Prices] -->|Bid/Ask/Mid| D
    end

    subgraph External["🌐 Polymarket APIs"]
        F1[Activity API]
        F2[CLOB REST]
        F3[CLOB WebSocket]
    end

    subgraph Output["📊 Output"]
        G[Flask Dashboard]
        H[SSE Live Feed]
        I[Position Persistence]
    end

    A1 & A2 & A3 --> B
    F1 -->|Poll every 2s| B
    F2 -->|Order Book| E
    F3 -->|Price Stream| E
    C -->|Paper / Live| F2
    D --> G
    D --> H
    D --> I

    style Input fill:#1e1b4b,stroke:#6366f1,color:#e0e7ff
    style Core fill:#042f2e,stroke:#22c55e,color:#d1fae5
    style External fill:#451a03,stroke:#f59e0b,color:#fef3c7
    style Output fill:#1c1917,stroke:#a855f7,color:#f3e8ff
```

## Trade Execution Flow

```mermaid
flowchart LR
    A["🔍 Detect Trade"] --> B{"Action?"}
    B -->|BUY| C{"Price\n3¢ – 70¢?"}
    B -->|SELL| W["⚠️ Whale Exit Alert"]
    C -->|No| X["Skip"]
    C -->|Yes| D{"ROI\n≥ 30%?"}
    D -->|No| X
    D -->|Yes| E{"Max\nPositions?"}
    E -->|Full| X
    E -->|OK| F{"Duplicate\nCheck"}
    F -->|Dup| X
    F -->|New| G{"Mode?"}
    G -->|Paper| H["📝 Simulate Fill\n+ Slippage & Gas"]
    G -->|Live| I["💰 CLOB FOK Order"]
    H & I --> J["📊 Track Position\n+ Live PnL"]

    style A fill:#3b82f6,stroke:#1d4ed8,color:#fff
    style W fill:#a855f7,stroke:#7c3aed,color:#fff
    style X fill:#ef4444,stroke:#dc2626,color:#fff
    style H fill:#f59e0b,stroke:#d97706,color:#fff
    style I fill:#22c55e,stroke:#16a34a,color:#fff
    style J fill:#6366f1,stroke:#4f46e5,color:#fff
```

## Features

| Feature | Description |
|---------|-------------|
| **Multi-Wallet Tracking** | Monitor unlimited Polymarket wallets simultaneously |
| **Smart Copy Engine** | Filters by entry price range, ROI threshold, dedup window |
| **Paper Trading** | Full simulation with slippage, gas fees, and FOK rejection |
| **Live Trading** | Real CLOB orders via Polymarket API (FOK) |
| **Web Dashboard** | Real-time positions, PnL, trade feed at `localhost:8080` |
| **Profile Resolver** | Add wallets by URL, username, or `0x` address |
| **Whale Exit Alerts** | Detects when tracked wallets sell positions you hold |
| **Live Prices** | WebSocket + REST fallback for bid/ask/mid |
| **Auto Settlement** | Detects market resolution, credits wins, debits losses |
| **Hot-Reload Config** | Change settings without restart |

## Quick Start

```bash
# Clone
git clone https://github.com/gnaneshwarvasala/polymarket-copy-bot.git
cd polymarket-copy-bot

# Install
pip install -r requirements.txt

# Configure
cp config.example.toml config.toml
# Edit config.toml — add wallet addresses to track

# Run (paper mode by default)
python bot.py

# Dashboard → http://localhost:8080
```

## Configuration

```toml
[mode]
paper = true                    # true = simulation, false = real USDC
paper_balance = 1000.0

[copy]
min_profit_pct = 30.0           # Min ROI% to copy (30 = max entry ~77¢)
max_entry_price = 0.70          # Max entry price (0.70 = 70¢)
min_entry_price = 0.03          # Skip dust trades below 3¢
position_size = 10.0            # USDC per trade
max_positions = 20              # Max concurrent positions
dedup_window_secs = 60          # Block same market+side within N seconds

[wallets]
track = [
    "0xed107a85a4585a381e48c7f7ca4144909e7dd2e5",
]

[poll]
interval_secs = 2
trades_per_wallet = 20

[dashboard]
enabled = true
port = 8080
```

## Adding Wallets

Three ways to add wallets — all formats auto-resolve:

```
https://polymarket.com/profile/scottilicious   →  profile URL
scottilicious                                   →  username
0x000d257d2dc7616feaef4ae0f14600fdf50a758e      →  direct address
```

| Method | How |
|--------|-----|
| **Config** | Add to `[wallets] track` in `config.toml` |
| **Dashboard** | Type in the "Add wallet" field |
| **API** | `POST /api/wallet/add {"input": "scottilicious"}` |

## System Architecture

```mermaid
graph LR
    subgraph bot.py["🚀 bot.py — Entry Point"]
        direction TB
        LOAD[Load Config] --> INIT[Init Components]
        INIT --> START[Start Async Tasks]
    end

    subgraph tracker.py["🔍 tracker.py"]
        POLL[Poll Activity API] --> DETECT[Detect New Trades]
        DETECT --> EMIT[Emit TradeEvent]
    end

    subgraph copier.py["📋 copier.py"]
        FILTER[Filter Signal] --> EXEC[Execute Trade]
        EXEC --> SETTLE[Settlement Loop]
    end

    subgraph positions.py["📊 positions.py"]
        OPEN[Open Position] --> TRACK[Track PnL]
        TRACK --> CLOSE[Settle / Close]
    end

    subgraph prices.py["💹 prices.py"]
        WS[WebSocket Stream] --> CACHE[Price Cache]
        REST[REST Fallback] --> CACHE
        CACHE --> PUSH[Push to Positions]
    end

    subgraph dashboard.py["🖥️ dashboard.py"]
        FLASK[Flask Server] --> SSE[SSE Live Feed]
        FLASK --> API[REST API]
        FLASK --> UI[Web UI]
    end

    subgraph resolver.py["🔗 resolver.py"]
        RESOLVE[URL / Username / Address → Proxy Wallet]
    end

    bot.py --> tracker.py --> copier.py --> positions.py
    prices.py --> positions.py
    dashboard.py --> positions.py
    dashboard.py --> resolver.py

    style bot.py fill:#1e3a5f,stroke:#3b82f6,color:#bfdbfe
    style tracker.py fill:#1a2e1a,stroke:#22c55e,color:#bbf7d0
    style copier.py fill:#3b1f0b,stroke:#f59e0b,color:#fef3c7
    style positions.py fill:#2d1b4e,stroke:#a855f7,color:#e9d5ff
    style prices.py fill:#1e3a5f,stroke:#3b82f6,color:#bfdbfe
    style dashboard.py fill:#1c1917,stroke:#71717a,color:#e4e4e7
    style resolver.py fill:#3b0a1e,stroke:#ec4899,color:#fce7f3
```

## Dashboard

Open `http://localhost:8080` after starting the bot:

| Panel | Shows |
|-------|-------|
| **Stats Bar** | Balance, Unrealized PnL, Realized PnL, Total PnL |
| **Positions Table** | Market, Side, Size, Entry, Bid, Ask, Spread, PnL |
| **Live Feed** | Real-time stream of detections, copies, fills, settlements |
| **Wallet List** | All tracked wallets with add/remove controls |

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | `GET` | Bot status, balance, position count |
| `/api/positions` | `GET` | All open positions with live prices |
| `/api/wallets` | `GET` | Tracked wallets list |
| `/api/wallet/add` | `POST` | Add wallet — `{"input": "0x..."}` |
| `/api/wallet/remove` | `POST` | Remove wallet — `{"wallet": "0x..."}` |
| `/api/trades` | `GET` | Trade history |
| `/api/feed` | `GET` | SSE live event stream |
| `/api/pause` | `POST` | Pause trading |
| `/api/resume` | `POST` | Resume trading |

## Settlement Flow

```mermaid
sequenceDiagram
    participant S as Settlement Loop
    participant C as CLOB API
    participant P as Positions
    participant B as Balance

    loop Every 30s
        S->>P: Get open positions
        loop Each position
            S->>C: Check market resolution
            alt Market resolved — WIN
                S->>P: Settle (WON)
                P->>B: Credit payout (size / entry_price)
                Note right of B: ✅ Balance increases
            else Market resolved — LOSS
                S->>P: Settle (LOST)
                Note right of B: ❌ Size already deducted
            else Still open
                Note right of S: Skip — check next cycle
            end
        end
    end
```

## Live Trading

> **Use at your own risk. Always start with paper mode.**

Set environment variables:

```bash
export POLY_KEY="your-api-key"
export POLY_SECRET="your-api-secret"
export POLY_PASSPHRASE="your-passphrase"
export POLY_PRIVATE_KEY="your-private-key"
```

Then in `config.toml`:

```toml
[mode]
paper = false
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Runtime** | Python 3.10+ / asyncio |
| **HTTP Client** | aiohttp |
| **WebSocket** | websockets |
| **Dashboard** | Flask + Server-Sent Events |
| **Config** | TOML (tomli) |
| **Persistence** | JSON file storage |

## License

[MIT](LICENSE)

---

<div align="center">

`#polymarket` `#copy-trading` `#trading-bot` `#python` `#prediction-markets` `#crypto` `#defi` `#asyncio` `#flask` `#websocket` `#paper-trading` `#clob` `#automated-trading`

</div>
