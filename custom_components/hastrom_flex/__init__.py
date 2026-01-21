"""The Stadtwerk Haßfurt haStrom Flex integration."""
from __future__ import annotations

import logging
import random
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_utils

from .aio_price import ApiError, HaStromFlexApi
from .const import (
    CONF_TARIFF,
    DOMAIN,
    EVENT_NEW_DAY,
    EVENT_NEW_HOUR,
    EVENT_NEW_PRICE,
    NAME,
    RANDOM_MINUTE_MAX,
    RANDOM_MINUTE_MIN,
    TIMEZONE,
    VERSION,
)
from .events import async_track_time_change_in_tz

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

STARTUP_MESSAGE = f"""
-------------------------------------------------------------------
{NAME}
Version: {VERSION}
This is a custom integration for Home Assistant
If you have any issues, please report them at:
https://github.com/f2daz/ha-integration_hastrom_flex/issues
-------------------------------------------------------------------
"""


class HaStromFlexData:
    """Class to hold data for the integration."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the data holder.

        Args:
            hass: Home Assistant instance
        """
        self._hass = hass
        self._data: dict[str, dict[str, Any]] = defaultdict(dict)
        self.listeners: list[CALLBACK_TYPE] = []
        self.tariffs: list[str] = []

    async def _update(self, tariff: str, type_: str = "today") -> None:
        """Update price data.

        Args:
            tariff: Tariff type
            type_: Data type (today or tomorrow)
        """
        _LOGGER.debug("Updating %s data for tariff %s", type_, tariff)

        client = async_get_clientsession(self._hass)
        api = HaStromFlexApi(tariff, client)

        try:
            if type_ == "today":
                data = await api.fetch_today()
            else:
                data = await api.fetch_tomorrow()

            if data:
                self._data[tariff][type_] = data
                _LOGGER.debug("Successfully updated %s data for %s", type_, tariff)
            else:
                _LOGGER.debug("No data available for %s (%s)", tariff, type_)
        except ApiError as e:
            _LOGGER.error("Failed to update %s data for %s: %s", type_, tariff, e)

    async def update_today(self, tariff: str) -> None:
        """Update today's prices for a tariff.

        Args:
            tariff: Tariff type
        """
        if tariff not in self.tariffs:
            self.tariffs.append(tariff)
        await self._update(tariff, "today")

    async def update_tomorrow(self, tariff: str) -> None:
        """Update tomorrow's prices for a tariff.

        Args:
            tariff: Tariff type
        """
        if tariff not in self.tariffs:
            self.tariffs.append(tariff)
        await self._update(tariff, "tomorrow")

    async def get_today(self, tariff: str) -> dict[str, Any] | None:
        """Get today's price data.

        Args:
            tariff: Tariff type

        Returns:
            dict: Today's price data
        """
        if tariff not in self.tariffs:
            self.tariffs.append(tariff)
            await self.update_today(tariff)

        return self._data.get(tariff, {}).get("today")

    async def get_tomorrow(self, tariff: str) -> dict[str, Any] | None:
        """Get tomorrow's price data.

        Args:
            tariff: Tariff type

        Returns:
            dict: Tomorrow's price data
        """
        if tariff not in self.tariffs:
            self.tariffs.append(tariff)
            await self.update_tomorrow(tariff)

        return self._data.get(tariff, {}).get("tomorrow")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Stadtwerk Haßfurt haStrom Flex from a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        bool: True if setup was successful
    """
    _LOGGER.info(STARTUP_MESSAGE)

    # Initialize data holder
    if DOMAIN not in hass.data:
        api = HaStromFlexData(hass)
        hass.data[DOMAIN] = api

        # Generiere zufällige Minute/Sekunde bei Setup (nicht bei Import)
        random_minute = random.randint(RANDOM_MINUTE_MIN, RANDOM_MINUTE_MAX)
        random_second = random.randint(0, 59)
        _LOGGER.debug(
            "Scheduled price update at 13:%02d:%02d", random_minute, random_second
        )

        # Set up callbacks for periodic updates
        async def new_day_callback(_: datetime) -> None:
            """Callback for new day."""
            _LOGGER.debug("New day callback triggered")

            # Move tomorrow's data to today
            for tariff in api.tariffs:
                if api._data.get(tariff, {}).get("tomorrow"):
                    api._data[tariff]["today"] = api._data[tariff]["tomorrow"]
                else:
                    await api.update_today(tariff)

                api._data[tariff]["tomorrow"] = {}

            async_dispatcher_send(hass, EVENT_NEW_DAY)

        async def new_hour_callback(_: datetime) -> None:
            """Callback for new hour."""
            _LOGGER.debug("New hour callback triggered")
            async_dispatcher_send(hass, EVENT_NEW_HOUR)

        async def new_price_callback(_: datetime) -> None:
            """Callback to fetch tomorrow's prices at 13:00 CET."""
            _LOGGER.debug("Fetching tomorrow's prices")

            for tariff in api.tariffs:
                await api.update_tomorrow(tariff)

            async_dispatcher_send(hass, EVENT_NEW_PRICE)

        # Schedule callbacks
        # Fetch tomorrow's prices at 13:00 CET with random minute/second
        timezone = await dt_utils.async_get_time_zone(TIMEZONE)
        cb_new_price = async_track_time_change_in_tz(
            hass,
            new_price_callback,
            hour=13,
            minute=random_minute,
            second=random_second,
            tz=timezone,
        )

        # New day at midnight
        cb_new_day = async_track_time_change(
            hass, new_day_callback, hour=0, minute=0, second=0
        )

        # New hour every 15 minutes (for updates)
        cb_new_hour = async_track_time_change(
            hass, new_hour_callback, minute=[0, 15, 30, 45], second=0
        )

        api.listeners.append(cb_new_price)
        api.listeners.append(cb_new_day)
        api.listeners.append(cb_new_hour)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.add_update_listener(async_reload_entry)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry

    Returns:
        bool: True if unload was successful
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        if DOMAIN in hass.data:
            # Cancel all listeners
            for unsub in hass.data[DOMAIN].listeners:
                unsub()
            hass.data.pop(DOMAIN)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry.

    Args:
        hass: Home Assistant instance
        entry: Config entry
    """
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
