from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from numbers import Real
from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from spritter import FuelStationRequest, get_fuel_prices

from .const import (
    CONF_PROVIDER,
    CONF_SCAN_INTERVAL_MINUTES,
    CONF_SOURCES,
    CONF_STATION_ID,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

PRICE_UNIT = "€"
REQUEST_TIMEOUT_SECONDS = 30

CONF_USER_AGENT = "user_agent"
CONF_KEYS = "keys"

SOURCE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PROVIDER): cv.string,
        vol.Required(CONF_STATION_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_USER_AGENT): cv.string,
        vol.Optional(CONF_KEYS): vol.All(cv.ensure_list, [cv.string]),
    }
)

PLATFORM_SCHEMA = cv.PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_SOURCES): vol.All(cv.ensure_list, [SOURCE_SCHEMA]),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.time_period,
    }
)


@dataclass(frozen=True, slots=True)
class SourceConfig:
    provider: str
    station_id: str
    name: str
    user_agent: str | None
    keys: tuple[str, ...] | None

    @property
    def unique_id(self) -> str:
        return f"{self.provider.strip().lower()}_{self.station_id.strip()}"


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    scan_interval = config[CONF_SCAN_INTERVAL]
    raw_sources = config[CONF_SOURCES]

    await _async_setup_sources(
        hass=hass,
        async_add_entities=async_add_entities,
        raw_sources=raw_sources,
        scan_interval=scan_interval,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entry_config = dict(entry.data)
    entry_config.update(entry.options)

    scan_interval = timedelta(
        minutes=int(entry_config.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES))
    )
    raw_sources = entry_config.get(CONF_SOURCES, [])

    await _async_setup_sources(
        hass=hass,
        async_add_entities=async_add_entities,
        raw_sources=raw_sources,
        scan_interval=scan_interval,
    )


async def _async_setup_sources(
    hass: HomeAssistant,
    async_add_entities: AddEntitiesCallback,
    raw_sources: list[dict[str, Any]],
    scan_interval: timedelta,
) -> None:
    sources = [_parse_source_config(raw_source) for raw_source in raw_sources]

    coordinators: list[tuple[SourceConfig, SpritterStationCoordinator]] = []
    for source in sources:
        coordinators.append(
            (
                source,
                SpritterStationCoordinator(
                    hass=hass,
                    source=source,
                    update_interval=scan_interval,
                ),
            )
        )

    refresh_results = await asyncio.gather(
        *(coordinator.async_refresh() for _, coordinator in coordinators),
        return_exceptions=True,
    )

    entities: list[SpritterFuelPriceSensor] = []
    for (source, coordinator), refresh_result in zip(coordinators, refresh_results):
        if isinstance(refresh_result, Exception):
            _LOGGER.warning(
                "Initial refresh failed for source %s/%s: %s",
                source.provider,
                source.station_id,
                refresh_result,
            )

        fuel_types = sorted(
            source.keys if source.keys else (coordinator.data or {}).keys()
        )
        if not fuel_types:
            _LOGGER.warning(
                "No fuel types available for source %s/%s; skipping entity creation",
                source.provider,
                source.station_id,
            )
            continue

        for fuel_type in fuel_types:
            entities.append(
                SpritterFuelPriceSensor(
                    coordinator=coordinator,
                    source=source,
                    fuel_type=fuel_type,
                )
            )

    async_add_entities(entities)


def _parse_source_config(raw_source: dict[str, Any]) -> SourceConfig:
    provider = raw_source[CONF_PROVIDER]
    station_id = raw_source[CONF_STATION_ID]
    name = raw_source.get(CONF_NAME) or f"{provider.upper()} {station_id}"
    user_agent = raw_source.get(CONF_USER_AGENT)

    keys_raw = raw_source.get(CONF_KEYS)
    keys = tuple(keys_raw) if keys_raw else None

    return SourceConfig(
        provider=provider,
        station_id=station_id,
        name=name,
        user_agent=user_agent,
        keys=keys,
    )


class SpritterStationCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self,
        hass: HomeAssistant,
        source: SourceConfig,
        update_interval: timedelta,
    ) -> None:
        self._source = source
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{source.unique_id}",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            request = FuelStationRequest(
                provider=self._source.provider,
                station_id=self._source.station_id,
                user_agent=self._source.user_agent,
                keys=self._source.keys,
            )

            def _fetch_prices() -> dict[str, Any]:
                result = get_fuel_prices(request)
                price_map = result.to_price_map(keys=self._source.keys)
                return {
                    fuel_type: float(price) if isinstance(price, Real) else price
                    for fuel_type, price in price_map.items()
                }

            return await asyncio.wait_for(
                self.hass.async_add_executor_job(_fetch_prices),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as err:
            raise UpdateFailed(
                f"Timed out fetching fuel prices after {REQUEST_TIMEOUT_SECONDS} seconds"
            ) from err
        except Exception as err:
            raise UpdateFailed(str(err)) from err


class SpritterFuelPriceSensor(SensorEntity):
    _attr_icon = "mdi:gas-station"
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PRICE_UNIT
    _attr_suggested_display_precision = 3

    def __init__(
        self,
        coordinator: SpritterStationCoordinator,
        source: SourceConfig,
        fuel_type: str,
    ) -> None:
        self.coordinator = coordinator
        self._source = source
        self._fuel_type = fuel_type
        self._attr_unique_id = f"{source.unique_id}_{fuel_type.strip().lower()}"
        self._attr_name = fuel_type
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._source.unique_id)},
            name=self._source.name,
            manufacturer="Spritter",
            model=self._source.provider,
        )
        self._update_attributes()
        self._update_native_value()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_native_value()
        self._update_attributes()
        self.async_write_ha_state()

    def _update_native_value(self) -> None:
        value = (self.coordinator.data or {}).get(self._fuel_type)
        if isinstance(value, Real):
            self._attr_native_value = float(value)
        else:
            self._attr_native_value = None

        self._attr_available = self.coordinator.last_update_success

    def _update_attributes(self) -> None:
        attributes: dict[str, Any] = {
            "provider": self._source.provider,
            "station_id": self._source.station_id,
            "fuel_type": self._fuel_type,
        }

        if self.coordinator.last_update_success_time is not None:
            attributes["last_refresh"] = (
                self.coordinator.last_update_success_time.isoformat()
            )

        if self._source.keys:
            attributes["keys"] = list(self._source.keys)

        self._attr_extra_state_attributes = attributes