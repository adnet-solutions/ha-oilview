"""Integrationstest mit echtem Home Assistant und simulierter OilView-API."""

from datetime import date, datetime
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.oilview.api import OilViewAuthError
from custom_components.oilview.const import CONF_LINK_ID, CONF_START_DATE, CONF_TOKEN, DOMAIN

START = date(2026, 11, 1)


def _stand(tag: date) -> float:
    n = (tag - START).days
    stand = 1170 - 9 * n
    if tag >= date(2026, 11, 6):
        stand += 1030
    return float(stand)


def _link(value: float, link_id: int = 37) -> dict:
    return {
        "id": link_id,
        "is": "probe",
        "name": "Heizöl",
        "status": "ok",
        "config": {"type": "tank", "capacity": 3400, "netCapacity": 3128, "unit": "l"},
        "data": {"value": value, "pct": 63, "unit": "l"},
    }


async def _fake_get_links(self, interpolate_at: datetime | None = None):
    if interpolate_at is None:
        return [_link(2140.0)]
    return [_link(_stand(interpolate_at.date()))]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def no_pause():
    with patch("custom_components.oilview.coordinator.BACKFILL_PAUSE", 0):
        yield


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "custom_components.oilview.api.OilViewApi.get_links",
        side_effect=OilViewAuthError("403"),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "falsch", CONF_START_DATE: "2026-11-01"}
        )
    assert result["errors"] == {"base": "invalid_auth"}

    with (
        patch("custom_components.oilview.api.OilViewApi.get_links", _fake_get_links),
        patch("custom_components.oilview.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_TOKEN: "geheim", CONF_START_DATE: "2026-11-01"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Heizöl"
    assert result["data"] == {
        CONF_TOKEN: "geheim",
        CONF_LINK_ID: 37,
        CONF_START_DATE: "2026-11-01",
    }


async def test_sensoren_nach_nachholen(hass: HomeAssistant, freezer) -> None:
    freezer.move_to("2026-11-07 10:00:00+01:00")
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="37",
        title="Heizöl",
        data={CONF_TOKEN: "geheim", CONF_LINK_ID: 37, CONF_START_DATE: "2026-11-01"},
    )
    entry.add_to_hass(hass)
    with patch("custom_components.oilview.api.OilViewApi.get_links", _fake_get_links):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

        registry = er.async_get(hass)

        def entity(key: str):
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, f"37_{key}")
            return hass.states.get(entity_id)

        def state(key: str) -> str:
            return entity(key).state

        assert state("tankstand") == "2140.0"
        assert state("fuellgrad") == "63"
        # 1.–4.11.: 4 x 9 l, 5.11. Tankung, 6.11.: 9 l, heute 2.146 -> 2.140: 6 l
        assert state("verbrauch_monat") == "51"
        assert state("verbrauch_heute") == "6"
        assert state("getankt_monat") == "1021"
        assert state("tageswerte") == "7"

        jahr = entity("verbrauch_jahr")
        assert jahr.attributes["monate"]["2026-11"] == {"verbrauch": 51, "getankt": 1021}

        assert await hass.config_entries.async_unload(entry.entry_id)
