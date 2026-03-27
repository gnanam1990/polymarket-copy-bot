"""
Web dashboard — real-time positions, PnL, trade feed.
"""
import os
import json
import time
import threading
import logging

from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

log = logging.getLogger(__name__)

# Set by bot.py before starting
_tracker = None
_copier = None
_positions = None

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Polymarket Copy Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#09090b;--card:#18181b;--border:#27272a;--text:#fafafa;--muted:#71717a;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6;--purple:#a855f7;--mono:'Courier New',monospace}
body{background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,sans-serif;padding:16px;max-width:1200px;margin:0 auto}
h1{font-size:20px;font-weight:800;margin-bottom:4px}
.sub{font-size:11px;color:var(--muted);font-family:var(--mono);margin-bottom:16px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:8px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px}
.stat .label{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase}
.stat .val{font-family:var(--mono);font-size:20px;font-weight:700;margin-top:2px}
.row{display:grid;grid-template-columns:1.5fr 1fr;gap:12px;margin-bottom:12px}
@media(max-width:768px){.row{grid-template-columns:1fr}}
.panel{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.panel-hdr{padding:10px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600}
.panel-body{padding:8px;max-height:400px;overflow-y:auto}
table{width:100%;border-collapse:collapse}
th{font-family:var(--mono);font-size:10px;color:var(--muted);text-transform:uppercase;text-align:left;padding:6px 8px;border-bottom:1px solid var(--border)}
td{font-family:var(--mono);font-size:11px;padding:5px 8px;border-bottom:1px solid rgba(39,39,42,.5)}
tr:hover{background:rgba(255,255,255,.02)}
.g{color:var(--green)}.r{color:var(--red)}.a{color:var(--amber)}.b{color:var(--blue)}.p{color:var(--purple)}.d{color:var(--muted)}
.feed-item{padding:4px 10px;border-bottom:1px solid rgba(39,39,42,.3);font-family:var(--mono);font-size:10px;border-left:3px solid transparent}
.feed-item .time{color:var(--muted);margin-right:6px}
.feed-item .type{font-weight:700;margin-right:6px;min-width:45px;display:inline-block}
.feed-item[data-t="DETECT"]{border-left-color:var(--muted)}.feed-item[data-t="COPY"]{border-left-color:var(--green)}
.feed-item[data-t="FILL"]{border-left-color:var(--amber)}.feed-item[data-t="WIN"]{border-left-color:var(--green);background:rgba(34,197,94,.04)}
.feed-item[data-t="LOSS"]{border-left-color:var(--red);background:rgba(239,68,68,.04)}
.feed-item[data-t="WHALE_EXIT"]{border-left-color:var(--purple)}
.feed-item[data-t="REJECT"]{border-left-color:var(--muted)}
.actions{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.btn{font-family:var(--mono);font-size:11px;padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--card);color:var(--muted);cursor:pointer}
.btn:hover{border-color:var(--green);color:var(--green)}
.btn.active{background:rgba(34,197,94,.1);border-color:var(--green);color:var(--green)}
.btn.red{border-color:var(--red);color:var(--red)}
input[type=text]{font-family:var(--mono);font-size:11px;padding:6px 10px;background:var(--card);border:1px solid var(--border);border-radius:6px;color:var(--text);outline:0;width:240px}
input:focus{border-color:var(--green)}
.badge{font-size:9px;font-weight:700;padding:2px 8px;border-radius:10px;font-family:var(--mono)}
.badge.paper{background:rgba(245,158,11,.1);color:var(--amber);border:1px solid rgba(245,158,11,.3)}
.badge.live{background:rgba(34,197,94,.1);color:var(--green);border:1px solid rgba(34,197,94,.3)}
.badge.run{background:rgba(34,197,94,.1);color:var(--green)}.badge.pause{background:rgba(245,158,11,.1);color:var(--amber)}
.toast{position:fixed;bottom:16px;right:16px;padding:8px 16px;border-radius:8px;font-family:var(--mono);font-size:11px;display:none;z-index:99;background:var(--card);border:1px solid var(--green);color:var(--green)}
.toast.show{display:block}
.wallet-item{display:flex;align-items:center;gap:8px;padding:5px 10px;border-bottom:1px solid rgba(39,39,42,.3);font-family:var(--mono);font-size:10px}
.wallet-item .name{color:var(--text);font-weight:600;min-width:100px}
.wallet-item .addr{color:var(--muted);font-size:9px;cursor:pointer}
.wallet-item .addr:hover{color:var(--blue)}
.wallet-item .rm{cursor:pointer;color:var(--muted);margin-left:auto}.wallet-item .rm:hover{color:var(--red)}
.empty{text-align:center;padding:30px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<h1>🔄 Polymarket Copy Bot</h1>
<div class="sub" id="status">Connecting...</div>
<div class="stats" id="stats"></div>
<div class="actions">
  <button class="btn active" id="pauseBtn" onclick="togglePause()">▶ Running</button>
  <input type="text" id="addInput" placeholder="Add: URL / username / 0x..." onkeydown="if(event.key==='Enter')addWallet()">
  <button class="btn" onclick="addWallet()">+ Add</button>
</div>
<div class="row">
  <div class="panel">
    <div class="panel-hdr">📊 Positions <span class="d" style="margin-left:auto" id="posCount">0</span></div>
    <div class="panel-body" id="posBody"><div class="empty">No positions</div></div>
  </div>
  <div class="panel">
    <div class="panel-hdr">📡 Live Feed</div>
    <div class="panel-body" id="feedBody"></div>
  </div>
</div>
<div class="panel" style="margin-bottom:12px">
  <div class="panel-hdr">🐋 Tracked Wallets <span class="d" style="margin-left:auto" id="wCount">0</span></div>
  <div class="panel-body" id="walletBody"><div class="empty">No wallets — add one above</div></div>
</div>
<div class="toast" id="toast"></div>
<script>
const $=id=>document.getElementById(id);let paused=false;

// SSE
const sse=new EventSource('/api/feed');
sse.onmessage=e=>{try{update(JSON.parse(e.data))}catch(e){}};

function update(d){
  $('status').innerHTML=`<span class="badge ${d.mode==='PAPER'?'paper':'live'}">${d.mode}</span> | ${d.wallets} wallets | ${d.positions} positions | ${d.paused?'⏸ Paused':'● Running'}`;
  paused=d.paused;
  $('pauseBtn').textContent=paused?'▶ Resume':'⏸ Pause';
  $('pauseBtn').className='btn '+(paused?'':'active');
  const total=d.realized+d.unrealized;
  $('stats').innerHTML=`
    <div class="stat"><div class="label">Balance</div><div class="val g">$${d.balance.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Unrealized</div><div class="val ${d.unrealized>=0?'g':'r'}">${d.unrealized>=0?'+':''}$${d.unrealized.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Realized</div><div class="val ${d.realized>=0?'g':'r'}">${d.realized>=0?'+':''}$${d.realized.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Total PnL</div><div class="val ${total>=0?'g':'r'}">${total>=0?'+':''}$${total.toFixed(2)}</div></div>
    <div class="stat"><div class="label">Positions</div><div class="val b">${d.positions}</div></div>
    <div class="stat"><div class="label">Wallets</div><div class="val p">${d.wallets}</div></div>`;

  // Positions
  $('posCount').textContent=d.pos_data.length;
  if(!d.pos_data.length){$('posBody').innerHTML='<div class="empty">No positions</div>';return}
  let h='<table><tr><th>Market</th><th>Side</th><th>Size</th><th>Entry</th><th>Bid</th><th>Ask</th><th>PnL</th></tr>';
  d.pos_data.forEach(p=>{
    const sc=p.side==='YES'?'g':'r';
    const bid=p.bid>0?(p.bid*100).toFixed(1)+'¢':'—';
    const ask=p.ask>0?(p.ask*100).toFixed(1)+'¢':'—';
    const pc=p.pnl>=0?'g':'r';
    h+=`<tr><td>${(p.title||p.market_id).substring(0,25)}</td><td class="${sc}">${p.side}</td><td>$${p.size.toFixed(2)}</td><td>${(p.entry_price*100).toFixed(1)}¢</td><td>${bid}</td><td>${ask}</td><td class="${pc}" style="font-weight:700">${p.pnl>=0?'+':''}$${p.pnl.toFixed(2)}</td></tr>`;
  });
  $('posBody').innerHTML=h+'</table>';

  // Feed
  if(d.events&&d.events.length){
    const cur=$('feedBody').innerHTML;
    let n='';d.events.forEach(e=>{n+=`<div class="feed-item" data-t="${e.type}"><span class="time">${e.time}</span><span class="type">${e.type}</span>${e.message}</div>`});
    $('feedBody').innerHTML=n+cur;
    const items=$('feedBody').children;if(items.length>200)for(let i=200;i<items.length;i++)items[i].remove();
  }
}

// Wallets
async function loadWallets(){
  const r=await fetch('/api/wallets');const d=await r.json();
  $('wCount').textContent=Object.keys(d.wallets).length;
  const entries=Object.entries(d.wallets);
  if(!entries.length){$('walletBody').innerHTML='<div class="empty">No wallets — add one above</div>';return}
  $('walletBody').innerHTML=entries.map(([addr,info])=>`<div class="wallet-item"><span class="name">${info.name||addr.substring(0,14)}</span><span class="addr" onclick="navigator.clipboard.writeText('${addr}')">${addr.substring(0,8)}…${addr.substring(38)}</span><span class="rm" onclick="removeWallet('${addr}')">✕</span></div>`).join('');
}
async function addWallet(){
  const v=$('addInput').value.trim();if(!v)return;$('addInput').value='';
  toast('Resolving...');
  const r=await fetch('/api/wallet/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input:v})});
  const d=await r.json();
  toast(d.ok?'✅ Added: '+(d.username||d.wallet.substring(0,14)):'❌ '+d.error);
  loadWallets();
}
async function removeWallet(addr){
  await fetch('/api/wallet/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({wallet:addr})});
  toast('Removed');loadWallets();
}
async function togglePause(){
  await fetch(paused?'/api/resume':'/api/pause',{method:'POST'});
}
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),3000)}

loadWallets();setInterval(loadWallets,30000);
</script>
</body>
</html>"""


def create_app(tracker, copier, positions):
    global _tracker, _copier, _positions
    _tracker, _copier, _positions = tracker, copier, positions

    app = Flask(__name__)
    CORS(app)

    @app.route("/")
    def index():
        return HTML

    @app.route("/api/status")
    def api_status():
        return jsonify({
            "mode": "PAPER" if _copier.is_paper else "LIVE",
            "balance": round(_copier.balance, 2),
            "positions": _positions.get_open_count(),
            "wallets": _tracker.get_wallet_count(),
            "paused": _tracker.is_paused,
            "unrealized": round(_positions.get_total_unrealized(), 2),
            "realized": round(_copier.realized_today, 2),
        })

    @app.route("/api/positions")
    def api_positions():
        return jsonify({"positions": _positions.get_open()})

    @app.route("/api/wallets")
    def api_wallets():
        return jsonify({"wallets": _tracker.get_wallets()})

    @app.route("/api/wallet/add", methods=["POST"])
    def api_wallet_add():
        data = request.get_json() or {}
        inp = data.get("input", "").strip()
        if not inp:
            return jsonify({"ok": False, "error": "No input"})
        try:
            from resolver import resolve
            profile = resolve(inp)
            is_new = _tracker.add_wallet(profile["wallet"], profile["username"])
            return jsonify({
                "ok": True,
                "is_new": is_new,
                "wallet": profile["wallet"],
                "username": profile["username"],
            })
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)})

    @app.route("/api/wallet/remove", methods=["POST"])
    def api_wallet_remove():
        data = request.get_json() or {}
        wallet = data.get("wallet", "")
        return jsonify({"ok": _tracker.remove_wallet(wallet)})

    @app.route("/api/trades")
    def api_trades():
        return jsonify({"trades": _positions.get_trades()})

    @app.route("/api/pause", methods=["POST"])
    def api_pause():
        _tracker.pause()
        _copier.pause()
        return jsonify({"ok": True})

    @app.route("/api/resume", methods=["POST"])
    def api_resume():
        _tracker.resume()
        _copier.resume()
        return jsonify({"ok": True})

    @app.route("/api/feed")
    def api_feed():
        """SSE stream — pushes all data every second."""
        def generate():
            last_event_count = 0
            while True:
                time.sleep(1)
                events = _copier.get_events(20)
                new_events = events[:max(0, len(events) - last_event_count)] if last_event_count else events[:5]
                last_event_count = len(_copier._events)

                data = json.dumps({
                    "mode": "PAPER" if _copier.is_paper else "LIVE",
                    "balance": round(_copier.balance, 2),
                    "unrealized": round(_positions.get_total_unrealized(), 2),
                    "realized": round(_copier.realized_today, 2),
                    "positions": _positions.get_open_count(),
                    "wallets": _tracker.get_wallet_count(),
                    "paused": _tracker.is_paused,
                    "pos_data": _positions.get_open(),
                    "events": new_events,
                })
                yield f"data: {data}\n\n"

        return Response(generate(), mimetype="text/event-stream",
                       headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app
