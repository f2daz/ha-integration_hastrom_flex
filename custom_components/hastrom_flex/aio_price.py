"""Asynchronous API client for Stadtwerk Haßfurt haStrom Flex."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_utils

from .const import (
    API_BASE_URL,
    API_ENDPOINT_FLEX,
    API_ENDPOINT_FLEX_PRO,
    API_ENDPOINT_RAW,
    API_TIMEOUT_SECONDS,
    TARIFF_FLEX,
    TARIFF_FLEX_PRO,
    TARIFF_RAW,
)

_LOGGER = logging.getLogger(__name__)


class InvalidValueException(ValueError):
    """Exception raised when API returns invalid data."""

    pass


class ApiError(Exception):
    """Exception raised when API request fails."""

    pass


class ApiConnectionError(ApiError):
    """Exception raised when API connection fails."""

    pass


class ApiTimeoutError(ApiError):
    """Exception raised when API request times out."""

    pass


class HaStromFlexApi:
    """API client for Stadtwerk Haßfurt haStrom Flex."""

    def __init__(self, tariff: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client.

        Args:
            tariff: Tariff type (flex, flex_pro, or raw)
            session: aiohttp ClientSession
        """
        self.tariff = tariff
        self.session = session
        self._base_url = API_BASE_URL
        self._timeout = aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS)

        # Set endpoint based on tariff
        endpoint_map = {
            TARIFF_FLEX: API_ENDPOINT_FLEX,
            TARIFF_FLEX_PRO: API_ENDPOINT_FLEX_PRO,
            TARIFF_RAW: API_ENDPOINT_RAW,
        }
        self._endpoint = endpoint_map.get(tariff, API_ENDPOINT_FLEX)

    async def _fetch(self, start_date: str | None = None) -> dict[str, Any] | None:
        """Fetch data from API.

        Args:
            start_date: Optional date in YYYYMMDD format

        Returns:
            dict: API response data or None if not available

        Raises:
            ApiConnectionError: If network connection fails
            ApiTimeoutError: If request times out
            ApiError: If API returns an error
        """
        url = f"{self._base_url}{self._endpoint}"
        params: dict[str, str] = {}

        if start_date:
            params["start_date"] = start_date

        _LOGGER.debug("Fetching data from %s with params %s", url, params)

        try:
            async with self.session.get(
                url, params=params, timeout=self._timeout
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    _LOGGER.debug(
                        "Successfully fetched data for tariff %s", self.tariff
                    )
                    return data
                elif response.status == 500:
                    # Data not available yet (e.g., tomorrow's prices)
                    _LOGGER.debug(
                        "Data not yet available (HTTP 500) for date %s", start_date
                    )
                    return None
                else:
                    error_text = await response.text()
                    _LOGGER.error(
                        "API request failed with status %s: %s",
                        response.status,
                        error_text,
                    )
                    raise ApiError(
                        f"API request failed with status {response.status}"
                    )

        except asyncio.TimeoutError as e:
            _LOGGER.error("API request timed out after %ss", API_TIMEOUT_SECONDS)
            raise ApiTimeoutError(
                f"API request timed out after {API_TIMEOUT_SECONDS}s"
            ) from e

        except aiohttp.ClientConnectionError as e:
            _LOGGER.error("Failed to connect to API: %s", e)
            raise ApiConnectionError(f"Failed to connect to API: {e}") from e

        except aiohttp.ClientError as e:
            _LOGGER.error("Network error during API request: %s", e)
            raise ApiConnectionError(f"Network error: {e}") from e

        except ApiError:
            # Re-raise our own exceptions
            raise

        except Exception as e:
            _LOGGER.error("Unexpected error during API request: %s", e)
            raise ApiError(f"Unexpected error: {e}") from e

    def _parse_response(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Parse API response and convert to internal format.

        Args:
            data: Raw API response

        Returns:
            dict: Parsed data with values in standard format
        """
        if not data:
            return None

        result: dict[str, Any] = {
            "tariff_info": data.get("tariff_info")
            or data.get("tariff_info_flex_pro")
            or data.get("info"),
            "values": [],
        }

        for item in data.get("data", []):
            try:
                # Parse timestamps
                start_time = dt_utils.parse_datetime(item["start_timestamp"])
                end_time = dt_utils.parse_datetime(item["end_timestamp"])

                if start_time is None or end_time is None:
                    _LOGGER.warning("Could not parse timestamps for item: %s", item)
                    continue

                # Convert to UTC if not already
                if start_time.tzinfo is None:
                    local_tz = dt_utils.get_default_time_zone()
                    # Use replace() for ZoneInfo objects (modern Python)
                    start_time = start_time.replace(tzinfo=local_tz).astimezone(
                        dt_utils.UTC
                    )
                    end_time = end_time.replace(tzinfo=local_tz).astimezone(
                        dt_utils.UTC
                    )

                value_entry: dict[str, Any] = {
                    "start": start_time,
                    "end": end_time,
                    "data": item,
                }

                result["values"].append(value_entry)
            except KeyError as e:
                _LOGGER.warning("Missing key in item %s: %s", item, e)
                continue
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Failed to parse item %s: %s", item, e)
                continue

        return result

    async def fetch_prices(self, date: datetime | None = None) -> dict[str, Any] | None:
        """Fetch prices for a specific date.

        Args:
            date: Date to fetch prices for (defaults to today)

        Returns:
            dict: Parsed price data or None if not available

        Raises:
            ApiError: If API request fails
        """
        if date is None:
            date = dt_utils.now()

        # Format date as YYYYMMDD
        date_str = date.strftime("%Y%m%d")

        data = await self._fetch(date_str)
        if not data:
            return None

        return self._parse_response(data)

    async def fetch_today(self) -> dict[str, Any] | None:
        """Fetch today's prices.

        Returns:
            dict: Today's price data or None if not available
        """
        return await self.fetch_prices()

    async def fetch_tomorrow(self) -> dict[str, Any] | None:
        """Fetch tomorrow's prices.

        Returns:
            dict: Tomorrow's price data (None if not yet available)
        """
        tomorrow = dt_utils.now() + timedelta(days=1)
        try:
            return await self.fetch_prices(tomorrow)
        except ApiError:
            _LOGGER.debug("Tomorrow's prices not yet available")
            return None
