"""Sensoren: Tankstand, Füllgrad, Verbrauch und Tankungen."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DAYS_IN_ATTRIBUTE, DOMAIN, MANUFACTURER
from .coordinator import OilViewConfigEntry, OilViewCoordinator, OilViewData


def _monat(d: OilViewData) -> str:
    return d.today.strftime("%Y-%m")


def _vormonat(d: OilViewData) -> str:
    return (d.today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def _jahr(d: OilViewData) -> str:
    return str(d.today.year)


def _letzte_tage(d: OilViewData) -> dict[str, Any]:
    tage = sorted(d.bilanz.tage.items())[-DAYS_IN_ATTRIBUTE:]
    return {"tage": {k: round(v["verbrauch"]) for k, v in tage}}


def _tank_attrs(d: OilViewData) -> dict[str, Any]:
    cfg = d.link.get("config") or {}
    return {
        "kapazitaet": cfg.get("capacity"),
        "nutzbare_kapazitaet": cfg.get("netCapacity"),
        "status": d.link.get("status"),
        "messsonde": d.link.get("name"),
    }


@dataclass(frozen=True, kw_only=True)
class OilViewSensorDescription(SensorEntityDescription):
    """Beschreibung mit Wert- und Attribut-Funktion."""

    value_fn: Callable[[OilViewData], Any]
    attrs_fn: Callable[[OilViewData], dict[str, Any]] | None = None
    # Verbrauchs-/Tankungswerte sind erst nach vollständigem Nachholen gültig;
    # vorher würde die Lücke bis heute als Tankung erscheinen.
    needs_backfill: bool = True


VERBRAUCH = dict(
    device_class=SensorDeviceClass.VOLUME,
    native_unit_of_measurement=UnitOfVolume.LITERS,
    suggested_display_precision=0,
)

SENSORS: tuple[OilViewSensorDescription, ...] = (
    OilViewSensorDescription(
        key="tankstand",
        needs_backfill=False,
        translation_key="tankstand",
        device_class=SensorDeviceClass.VOLUME_STORAGE,
        native_unit_of_measurement=UnitOfVolume.LITERS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda d: d.level,
        attrs_fn=_tank_attrs,
    ),
    OilViewSensorDescription(
        key="fuellgrad",
        needs_backfill=False,
        translation_key="fuellgrad",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.link.get("data") or {}).get("pct"),
    ),
    OilViewSensorDescription(
        key="verbrauch_heute",
        translation_key="verbrauch_heute",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bilanz.wert("tage", d.today.isoformat(), "verbrauch"),
        attrs_fn=_letzte_tage,
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="verbrauch_monat",
        translation_key="verbrauch_monat",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bilanz.wert("monate", _monat(d), "verbrauch"),
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="verbrauch_vormonat",
        translation_key="verbrauch_vormonat",
        value_fn=lambda d: d.bilanz.wert("monate", _vormonat(d), "verbrauch"),
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="verbrauch_jahr",
        translation_key="verbrauch_jahr",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bilanz.wert("jahre", _jahr(d), "verbrauch"),
        attrs_fn=lambda d: {"monate": d.bilanz.monate, "jahre": d.bilanz.jahre},
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="getankt_monat",
        translation_key="getankt_monat",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bilanz.wert("monate", _monat(d), "getankt"),
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="getankt_jahr",
        translation_key="getankt_jahr",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.bilanz.wert("jahre", _jahr(d), "getankt"),
        **VERBRAUCH,
    ),
    OilViewSensorDescription(
        key="tageswerte",
        needs_backfill=False,
        translation_key="tageswerte",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.days_stored,
        attrs_fn=lambda d: {"nachholen_abgeschlossen": d.backfill_done},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OilViewConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(OilViewSensor(coordinator, desc) for desc in SENSORS)


class OilViewSensor(CoordinatorEntity[OilViewCoordinator], SensorEntity):
    """Ein OilView-Sensor."""

    _attr_has_entity_name = True
    entity_description: OilViewSensorDescription

    def __init__(
        self, coordinator: OilViewCoordinator, description: OilViewSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        link_id = coordinator.link_id
        self._attr_unique_id = f"{link_id}_{description.key}"
        link = coordinator.data.link if coordinator.data else {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(link_id))},
            name=f"OilView {link.get('name') or 'Tank'}",
            manufacturer=MANUFACTURER,
            model="OilView",
            configuration_url="https://www.oilview.de",
        )

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self.entity_description.needs_backfill or (
            self.coordinator.data is not None and self.coordinator.data.backfill_done
        )

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
