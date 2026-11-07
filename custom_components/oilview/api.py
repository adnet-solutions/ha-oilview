"""Schlanker Client für die OilView-API (https://api.oilview.de/apidoc/)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from .const import API_BASE


class OilViewError(Exception):
    """Allgemeiner Fehler beim Zugriff auf die OilView-API."""


class OilViewAuthError(OilViewError):
    """Token ungültig oder ohne Berechtigung."""


class OilViewApi:
    """Zugriff auf die OilView-API mit dem Header X-AUTH-TOKEN."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        url = f"{API_BASE}/{path}"
        headers = {"X-AUTH-TOKEN": self._token, "Accept": "application/json"}
        try:
            async with self._session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status in (401, 403):
                    raise OilViewAuthError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    text = await resp.text()
                    raise OilViewError(f"HTTP {resp.status}: {text[:200]}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise OilViewError(str(err)) from err

    async def get_links(self, interpolate_at: datetime | None = None) -> list[dict]:
        """Alle Messsonden (Links) mit aktuellem oder interpoliertem Stand."""
        params = None
        if interpolate_at is not None:
            params = {
                "interpolateAt": interpolate_at.strftime("%Y-%m-%dT%H:%M:%S"),
                "interpolationMode": "interpolate",
            }
        data = await self._get("links/", params)
        return data.get("links", []) or []

    async def get_level_at(self, link_id: int, when: datetime) -> float | None:
        """Stand einer Messsonde zu einem Zeitpunkt (Ortszeit des Portals)."""
        for link in await self.get_links(when):
            if link.get("id") == link_id:
                return level_of(link)
        return None


def level_of(link: dict) -> float | None:
    """Literwert aus einem Link-Objekt lesen."""
    value = (link.get("data") or {}).get("value")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def tank_links(links: list[dict]) -> list[dict]:
    """Nur Tanks; wenn keiner als Tank markiert ist, alle Links."""
    tanks = [l for l in links if (l.get("config") or {}).get("type") == "tank"]
    return tanks or links
