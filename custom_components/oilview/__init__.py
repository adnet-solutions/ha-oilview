"""OilView (TECSON) – Tankstand, Verbrauch und Tankungen aus der OilView-API."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change

from .api import OilViewApi
from .const import BACKFILL_HOUR, BACKFILL_MINUTE, CONF_TOKEN
from .coordinator import OilViewConfigEntry, OilViewCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: OilViewConfigEntry) -> bool:
    """Integration einrichten."""
    api = OilViewApi(async_get_clientsession(hass), entry.data[CONF_TOKEN])
    coordinator = OilViewCoordinator(hass, entry, api)
    await coordinator.async_load()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    @callback
    def _start_backfill(_now=None) -> None:
        entry.async_create_background_task(
            hass, coordinator.async_backfill(), "oilview_backfill"
        )

    # Sofort fehlende Tage nachholen, danach jede Nacht den neuen Tag.
    _start_backfill()
    entry.async_on_unload(
        async_track_time_change(
            hass, _start_backfill, hour=BACKFILL_HOUR, minute=BACKFILL_MINUTE, second=0
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: OilViewConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: OilViewConfigEntry) -> bool:
    """Integration entladen."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
