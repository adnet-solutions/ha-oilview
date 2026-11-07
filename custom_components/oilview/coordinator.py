"""DataUpdateCoordinator: aktueller Stand + nachgeholte Tageswerte."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OilViewApi, OilViewAuthError, OilViewError, level_of
from .const import (
    BACKFILL_PAUSE,
    CONF_CONSUMPTION_THRESHOLD,
    CONF_LINK_ID,
    CONF_REFILL_THRESHOLD,
    CONF_START_DATE,
    DEFAULT_CONSUMPTION_THRESHOLD,
    DEFAULT_REFILL_THRESHOLD,
    DOMAIN,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .evaluation import Bilanz, build_points, evaluate

_LOGGER = logging.getLogger(__name__)

type OilViewConfigEntry = ConfigEntry["OilViewCoordinator"]


@dataclass
class OilViewData:
    """Was die Sensoren lesen."""

    link: dict[str, Any]
    level: float | None
    bilanz: Bilanz
    today: date
    backfill_done: bool
    days_stored: int


class OilViewCoordinator(DataUpdateCoordinator[OilViewData]):
    """Holt alle 30 Minuten den Stand und rechnet die Bilanz neu."""

    config_entry: OilViewConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: OilViewConfigEntry, api: OilViewApi
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.link_id: int = entry.data[CONF_LINK_ID]
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._levels: dict[str, float] = {}
        self._backfill_lock = asyncio.Lock()
        self._backfill_done = False

    # --- Einstellungen -------------------------------------------------
    def _opt(self, key: str, default: Any) -> Any:
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    @property
    def start_date(self) -> date:
        value = self._opt(CONF_START_DATE, None)
        if value:
            return date.fromisoformat(str(value))
        return date(dt_util.now().year, 1, 1)

    # --- Speicher ------------------------------------------------------
    async def async_load(self) -> None:
        stored = await self._store.async_load() or {}
        if stored.get("link_id") == self.link_id:
            self._levels = {k: float(v) for k, v in stored.get("tage", {}).items()}

    async def _async_save(self) -> None:
        await self._store.async_save({"link_id": self.link_id, "tage": self._levels})

    # --- Abruf ---------------------------------------------------------
    async def _async_update_data(self) -> OilViewData:
        try:
            links = await self.api.get_links()
        except OilViewAuthError as err:
            raise ConfigEntryAuthFailed("OilView-Token ungültig") from err
        except OilViewError as err:
            raise UpdateFailed(f"OilView nicht erreichbar: {err}") from err

        link = next((l for l in links if l.get("id") == self.link_id), None)
        if link is None:
            raise UpdateFailed(f"Messsonde {self.link_id} nicht mehr im Konto")

        return self._build(link, level_of(link))

    def _build(self, link: dict[str, Any], level: float | None) -> OilViewData:
        today = dt_util.now().date()
        punkte = build_points(self._levels, self.start_date, today, level)
        bilanz = evaluate(
            punkte,
            float(self._opt(CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD)),
            float(self._opt(CONF_REFILL_THRESHOLD, DEFAULT_REFILL_THRESHOLD)),
        )
        return OilViewData(
            link=link,
            level=level,
            bilanz=bilanz,
            today=today,
            backfill_done=self._backfill_done,
            days_stored=len(self._levels),
        )

    async def async_backfill(self) -> None:
        """Fehlende Mitternachtswerte ab Startdatum nachholen (läuft im Hintergrund)."""
        if self._backfill_lock.locked():
            return
        async with self._backfill_lock:
            today = dt_util.now().date()
            day = self.start_date
            fetched = 0
            while day <= today:
                key = day.isoformat()
                if key not in self._levels:
                    try:
                        value = await self.api.get_level_at(
                            self.link_id, datetime.combine(day, time(0, 0))
                        )
                    except OilViewAuthError:
                        _LOGGER.error("OilView-Token ungültig, Nachholen abgebrochen")
                        return
                    except OilViewError as err:
                        _LOGGER.warning(
                            "Nachholen bei %s abgebrochen: %s (nächster Versuch beim nächsten Lauf)",
                            key,
                            err,
                        )
                        break
                    if value is not None:
                        self._levels[key] = value
                    fetched += 1
                    if fetched % 20 == 0:
                        await self._async_save()
                        _LOGGER.debug("OilView: %s Tage nachgeholt", fetched)
                    await asyncio.sleep(BACKFILL_PAUSE)
                day += timedelta(days=1)
            else:
                self._backfill_done = True
            await self._async_save()
            if fetched:
                _LOGGER.info("OilView: %s Tageswerte nachgeholt", fetched)
        await self.async_request_refresh()
