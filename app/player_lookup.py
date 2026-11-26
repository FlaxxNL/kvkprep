"""Player lookup (nickname, avatar, alliance) via the MightPulse API.

Needs MIGHTPULSE_API_KEY. Without it the lookup is disabled and players
type their name themselves, exactly as before.
"""

import logging
import threading
import time

import requests

from config import Config

log = logging.getLogger("audit")

# Small in-memory cache so repeated blur/change events and the admin refresh
# do not burn the MightPulse quota (60/min, 5000/day on the free tier).
_CACHE_TTL = 600
_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()


def _safe_https(url):
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if url.startswith("/"):
        url = f"https://mightpulse.com{url}"
    return url if url.startswith("https://") else None


def lookup_enabled() -> bool:
    return bool(Config.MIGHTPULSE_API_KEY)


def fetch_player_info(fid) -> dict | None:
    """Return {"nickname", "avatar_url", "alliance"} or None if unknown/unavailable."""
    if not Config.MIGHTPULSE_API_KEY:
        return None
    fid = str(fid or "").strip()
    if not fid.isdigit() or len(fid) > 20:
        return None

    now = time.time()
    with _cache_lock:
        hit = _cache.get(fid)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    base = (Config.MIGHTPULSE_BASE_URL or "https://api.mightpulse.com/v1").rstrip("/")
    try:
        resp = requests.get(
            f"{base}/players/{fid}",
            params={"include": "base"},
            headers={"X-Api-Key": Config.MIGHTPULSE_API_KEY},
            timeout=12,
        )
    except requests.RequestException as e:
        log.warning(f"MightPulse lookup failed for {fid}: {e}")
        return None

    if resp.status_code != 200:
        # 404 = unknown player, 202 = still being looked up, 429 = rate limit
        log.info(f"MightPulse returned {resp.status_code} for player {fid}")
        return None

    try:
        data = resp.json()
    except ValueError:
        return None
    if not data.get("ok"):
        return None

    player = data.get("player") or {}
    alliance = player.get("alliance")
    info = {
        "nickname": (player.get("nick_name") or "").strip() or None,
        "avatar_url": _safe_https(player.get("avatar_url")),
        "alliance": (alliance.get("abbr") or "") if isinstance(alliance, dict) else "",
    }
    if not info["nickname"]:
        return None

    with _cache_lock:
        if len(_cache) > 2000:
            _cache.clear()
        _cache[fid] = (now, info)
    return info
