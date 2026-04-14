from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SOURCES,
    CONF_STATION_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)


class SpritterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._scan_interval_minutes = DEFAULT_SCAN_INTERVAL_MINUTES
        self._sources: list[dict[str, str]] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            self._scan_interval_minutes = int(user_input[CONF_SCAN_INTERVAL_MINUTES])
            return await self.async_step_source()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_MINUTES,
                        default=DEFAULT_SCAN_INTERVAL_MINUTES,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=3600,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )

    async def async_step_source(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            provider = user_input[CONF_PROVIDER].strip()
            station_id = user_input[CONF_STATION_ID].strip()

            if not provider or not station_id:
                errors["base"] = "empty_value"
            else:
                self._sources.append(
                    {
                        CONF_PROVIDER: provider,
                        CONF_STATION_ID: station_id,
                    }
                )

                if user_input.get("add_another", False):
                    return await self.async_step_source()

                return self.async_create_entry(
                    title="Spritter",
                    data={
                        CONF_SCAN_INTERVAL_MINUTES: self._scan_interval_minutes,
                        CONF_SOURCES: self._sources,
                    },
                )

        return self.async_show_form(
            step_id="source",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): str,
                    vol.Required(CONF_STATION_ID): str,
                    vol.Optional("add_another", default=False): bool,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return SpritterOptionsFlow(config_entry)


class SpritterOptionsFlow(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        effective = dict(config_entry.data)
        effective.update(config_entry.options)

        self._scan_interval_minutes = int(
            effective.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
        )
        self._sources: list[dict[str, str]] = [
            {
                CONF_PROVIDER: str(source[CONF_PROVIDER]),
                CONF_STATION_ID: str(source[CONF_STATION_ID]),
            }
            for source in effective.get(CONF_SOURCES, [])
        ]

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        menu_options = ["edit_base", "add_source", "finish"]
        if self._sources:
            menu_options.insert(2, "remove_source")

        return self.async_show_menu(step_id="init", menu_options=menu_options)

    async def async_step_edit_base(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._scan_interval_minutes = int(user_input[CONF_SCAN_INTERVAL_MINUTES])
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_base",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL_MINUTES,
                        default=self._scan_interval_minutes,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1,
                            max=3600,
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )

    async def async_step_add_source(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            provider = user_input[CONF_PROVIDER].strip()
            station_id = user_input[CONF_STATION_ID].strip()

            if not provider or not station_id:
                errors["base"] = "empty_value"
            else:
                self._sources.append(
                    {
                        CONF_PROVIDER: provider,
                        CONF_STATION_ID: station_id,
                    }
                )
                return await self.async_step_init()

        return self.async_show_form(
            step_id="add_source",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PROVIDER): str,
                    vol.Required(CONF_STATION_ID): str,
                }
            ),
            errors=errors,
        )

    async def async_step_remove_source(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            remove_index = int(user_input["source_index"])
            if 0 <= remove_index < len(self._sources):
                self._sources.pop(remove_index)
            return await self.async_step_init()

        options = {
            str(index): f"{source[CONF_PROVIDER]} / {source[CONF_STATION_ID]}"
            for index, source in enumerate(self._sources)
        }

        return self.async_show_form(
            step_id="remove_source",
            data_schema=vol.Schema(
                {
                    vol.Required("source_index"): vol.In(options)
                }
            ),
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None):
        if not self._sources:
            return self.async_abort(reason="no_sources")

        return self.async_create_entry(
            title="",
            data={
                CONF_SCAN_INTERVAL_MINUTES: self._scan_interval_minutes,
                CONF_SOURCES: self._sources,
            },
        )
