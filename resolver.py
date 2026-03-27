"""
Resolve Polymarket profile URLs, usernames, and addresses to proxy wallets.

Accepts:
    - https://polymarket.com/profile/scottilicious
    - scottilicious
    - 0x000d257d2dc7616feaef4ae0f14600fdf50a758e
"""
import requests
import logging

log = logging.getLogger(__name__)

HEADERS = {"User-Agent": "PolymarketCopyBot/1.0"}


def resolve(input_str: str) -> dict:
    """
    Resolve any input to a proxy wallet address.
    Returns: {"wallet": "0x...", "username": "...", "win_rate": 0.0}
    """
    inp = input_str.strip()

    # Extract identifier from URL
    if "polymarket.com/profile/" in inp:
        inp = inp.split("polymarket.com/profile/")[-1].strip("/").split("?")[0]

    if not inp:
        raise ValueError("Empty input")

    is_address = inp.startswith("0x") and len(inp) == 42

    # Call Polymarket profiles API
    if is_address:
        url = f"https://data-api.polymarket.com/profiles?address={inp.lower()}"
    else:
        url = f"https://data-api.polymarket.com/profiles?username={inp}"

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        data = resp.json()
        if isinstance(data, list):
            data = data[0] if data else {}

        proxy = (data.get("proxyWallet") or data.get("proxy_wallet") or "").lower()
        username = data.get("username") or data.get("userName") or ""

        if not proxy and is_address:
            proxy = inp.lower()

        if not proxy:
            raise ValueError(f"Could not resolve: {input_str}")

        return {"wallet": proxy, "username": username, "win_rate": 0.0}

    except requests.RequestException as e:
        raise ValueError(f"API error: {e}")
