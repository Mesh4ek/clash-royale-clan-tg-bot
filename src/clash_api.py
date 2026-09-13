from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from config import config

logger = logging.getLogger(__name__)

API_BASE = "https://api.clashroyale.com/v1"
DECKS_PER_DAY = config.decks_per_day

TIMEOUT = httpx.Timeout(config.clash_request_timeout, connect=5.0)
NETWORK_ERROR = 0

CLAN_TTL_SECONDS = 60.0
LOCATION_TTL_SECONDS = 3600.0
RIVER_RACE_TTL_SECONDS = 30.0
RIVER_RACE_LOG_TTL_SECONDS = 300.0
RIVER_RACE_LOG_LIMIT = 5

_client: httpx.AsyncClient | None = None
_cache: dict[str, tuple[float, Any]] = {}


@dataclass(frozen=True)
class ClanRank:
    position: int | None
    location: str
    country_code: str | None


def _encode_tag(tag: str) -> str:
    return quote(tag, safe="")


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {config.clash_api_token}"},
            timeout=TIMEOUT,
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
    _client = None


async def _get(path: str) -> tuple[Any | None, int]:
    try:
        response = await _get_client().get(path)
    except httpx.HTTPError as exc:
        logger.warning("clash api: %s failed: %s", path, exc)
        return None, NETWORK_ERROR
    if response.status_code != 200:
        logger.warning("clash api: %s -> %s %s", path, response.status_code, response.text[:200])
        return None, response.status_code
    return response.json(), 200


async def _get_cached(path: str, ttl_seconds: float, force_refresh: bool = False) -> tuple[Any | None, int]:
    now = time.monotonic()
    cached = _cache.get(path)
    if not force_refresh and cached is not None and now - cached[0] < ttl_seconds:
        return cached[1], 200

    data, status_code = await _get(path)
    if data is not None:
        _cache[path] = (now, data)
    return data, status_code


async def get_player(tag: str) -> tuple[dict | None, int]:
    return await _get(f"/players/{_encode_tag(tag)}")


def player_in_clan(player: dict) -> bool:
    clan = player.get("clan") or {}
    return (clan.get("tag") or "").upper() == config.clan_tag


async def get_clan_members() -> tuple[list[tuple[str, str]] | None, int]:
    data, status_code = await _get_cached(f"/clans/{_encode_tag(config.clan_tag)}", CLAN_TTL_SECONDS)
    if data is None:
        return None, status_code
    members = data.get("memberList", [])
    return [(m.get("tag"), m.get("name")) for m in members], 200


async def get_current_river_race(force_refresh: bool = False) -> tuple[dict | None, int]:
    path = f"/clans/{_encode_tag(config.clan_tag)}/currentriverrace"
    return await _get_cached(path, RIVER_RACE_TTL_SECONDS, force_refresh)


async def get_river_race_log() -> tuple[dict | None, int]:
    path = f"/clans/{_encode_tag(config.clan_tag)}/riverracelog?limit={RIVER_RACE_LOG_LIMIT}"
    return await _get_cached(path, RIVER_RACE_LOG_TTL_SECONDS)


async def _ranking_location() -> tuple[dict | None, int]:
    if config.clash_location_id is not None:
        return await _get_cached(f"/locations/{config.clash_location_id}", LOCATION_TTL_SECONDS)
    # Without an override, rank the clan in the region set on its own Clash Royale profile.
    clan, status_code = await _get_cached(f"/clans/{_encode_tag(config.clan_tag)}", CLAN_TTL_SECONDS)
    if clan is None:
        return None, status_code
    location = clan.get("location") or {}
    return (location if location.get("id") else None), 200


async def get_clan_rank() -> tuple[ClanRank | None, int]:
    location, status_code = await _ranking_location()
    if location is None:
        return None, status_code
    data, status_code = await _get(f"/locations/{location['id']}/rankings/clans")
    if data is None:
        return None, status_code

    wanted = config.clan_tag.lstrip("#")
    position = next(
        (
            index
            for index, clan in enumerate(data.get("items", []), start=1)
            if (clan.get("tag") or "").lstrip("#").upper() == wanted
        ),
        None,
    )
    country_code = location.get("countryCode") if location.get("isCountry") else None
    return ClanRank(position, location.get("name", ""), country_code), 200


async def get_war_status_for_tags(
    player_tags: list[tuple[str, str | None, str | None]],
) -> tuple[list[tuple[str | None, int, str | None]] | None, int]:
    data, status_code = await get_current_river_race()
    if data is None:
        return None, status_code

    participants = {p.get("tag"): p for p in data.get("clan", {}).get("participants", [])}
    result = []
    for tag, clash_name, telegram_username in player_tags:
        participant = participants.get(tag) or {}
        decks_used = participant.get("decksUsedToday") or 0
        result.append((clash_name, DECKS_PER_DAY - decks_used, telegram_username))
    return result, 200
