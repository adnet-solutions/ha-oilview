"""Einrichtungsdialog: Token eingeben, Tank wählen, Startdatum festlegen."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    DateSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import OilViewApi, OilViewAuthError, OilViewError, tank_links
from .const import (
    CONF_CONSUMPTION_THRESHOLD,
    CONF_LINK_ID,
    CONF_REFILL_THRESHOLD,
    CONF_START_DATE,
    CONF_TOKEN,
    DEFAULT_CONSUMPTION_THRESHOLD,
    DEFAULT_REFILL_THRESHOLD,
    DOMAIN,
)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _link_title(link: dict[str, Any]) -> str:
    name = link.get("name") or f"Tank {link.get('id')}"
    cap = (link.get("config") or {}).get("capacity")
    return f"{name} ({cap} l)" if cap else name


async def _validate(hass, token: str) -> list[dict[str, Any]]:
    api = OilViewApi(async_get_clientsession(hass), token)
    return tank_links(await api.get_links())


class OilViewConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config Flow für OilView."""

    VERSION = 1

    def __init__(self) -> None:
        self._token: str | None = None
        self._start: str | None = None
        self._links: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                links = await _validate(self.hass, user_input[CONF_TOKEN])
            except OilViewAuthError:
                errors["base"] = "invalid_auth"
            except OilViewError:
                errors["base"] = "cannot_connect"
            else:
                if not links:
                    errors["base"] = "no_tanks"
                else:
                    self._token = user_input[CONF_TOKEN]
                    self._start = user_input[CONF_START_DATE]
                    self._links = links
                    if len(links) == 1:
                        return await self._async_create(links[0])
                    return await self.async_step_link()

        default_start = date(dt_util.now().year, 1, 1).isoformat()
        schema = vol.Schema(
            {
                vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
                vol.Required(CONF_START_DATE, default=default_start): DateSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_link(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            link_id = int(user_input[CONF_LINK_ID])
            link = next(l for l in self._links if l.get("id") == link_id)
            return await self._async_create(link)

        options = [
            SelectOptionDict(value=str(l["id"]), label=_link_title(l))
            for l in self._links
        ]
        schema = vol.Schema(
            {vol.Required(CONF_LINK_ID): SelectSelector(SelectSelectorConfig(options=options))}
        )
        return self.async_show_form(step_id="link", data_schema=schema)

    async def _async_create(self, link: dict[str, Any]) -> ConfigFlowResult:
        await self.async_set_unique_id(str(link["id"]))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=link.get("name") or "OilView",
            data={
                CONF_TOKEN: self._token,
                CONF_LINK_ID: int(link["id"]),
                CONF_START_DATE: self._start,
            },
        )

    # --- Token erneuern ------------------------------------------------
    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            try:
                links = await _validate(self.hass, user_input[CONF_TOKEN])
            except OilViewAuthError:
                errors["base"] = "invalid_auth"
            except OilViewError:
                errors["base"] = "cannot_connect"
            else:
                if not any(l.get("id") == entry.data[CONF_LINK_ID] for l in links):
                    errors["base"] = "no_tanks"
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN]}
                    )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN_SELECTOR}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return OilViewOptionsFlow()


class OilViewOptionsFlow(OptionsFlow):
    """Startdatum und Schwellen nachträglich ändern."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        entry = self.config_entry

        def current(key: str, default: Any) -> Any:
            return entry.options.get(key, entry.data.get(key, default))

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_START_DATE,
                    default=current(CONF_START_DATE, date(dt_util.now().year, 1, 1).isoformat()),
                ): DateSelector(),
                vol.Required(
                    CONF_CONSUMPTION_THRESHOLD,
                    default=current(CONF_CONSUMPTION_THRESHOLD, DEFAULT_CONSUMPTION_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1, max=50, step=1, unit_of_measurement="L",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_REFILL_THRESHOLD,
                    default=current(CONF_REFILL_THRESHOLD, DEFAULT_REFILL_THRESHOLD),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=10, max=1000, step=1, unit_of_measurement="L",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
