"""Sensor platform for Stadtwerk Haßfurt haStrom Flex integration."""
from __future__ import annotations

import ast
import logging
import operator
from datetime import datetime
from statistics import mean, median
from typing import Any

import homeassistant.helpers.config_validation as cv
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.template import Template
from homeassistant.util import dt as dt_utils

from .const import (
    CONF_ADDITIONAL_COSTS,
    CONF_TARIFF,
    DEFAULT_TEMPLATE,
    DOMAIN,
    EVENT_NEW_DAY,
    EVENT_NEW_HOUR,
    EVENT_NEW_PRICE,
    PRICE_FIELDS,
    SENTINEL,
    TARIFF_NAMES,
    UNIT_CT_PER_KWH,
)

_LOGGER = logging.getLogger(__name__)

# Sichere mathematische Operatoren für safe_eval
_SAFE_OPERATORS: dict[type, Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval_node(node: ast.AST) -> float | int:
    """Evaluiere einen AST-Knoten sicher (nur mathematische Operationen)."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"Ungültiger Konstantentyp: {type(node.value)}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Ungültiger Operator: {op_type.__name__}")
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        return _SAFE_OPERATORS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"Ungültiger unärer Operator: {op_type.__name__}")
        operand = _safe_eval_node(node.operand)
        return _SAFE_OPERATORS[op_type](operand)
    raise ValueError(f"Ungültiger Knotentyp: {type(node).__name__}")


def safe_math_eval(expression: str) -> float | int:
    """Evaluiere einen mathematischen Ausdruck sicher."""
    try:
        tree = ast.parse(expression, mode="eval")
        return _safe_eval_node(tree.body)
    except (SyntaxError, TypeError) as e:
        raise ValueError(f"Ungültiger Ausdruck: {e}") from e


# Sensor-Konfigurationen für weniger Duplikation
SENSOR_TYPES: dict[str, dict[str, Any]] = {
    "current_price": {
        "name_suffix": "Aktueller Preis",
        "icon": "mdi:flash",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "average": {
        "name_suffix": "Durchschnitt",
        "icon": "mdi:chart-line",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "min": {
        "name_suffix": "Minimum",
        "icon": "mdi:arrow-down-bold",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "max": {
        "name_suffix": "Maximum",
        "icon": "mdi:arrow-up-bold",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "median": {
        "name_suffix": "Median",
        "icon": "mdi:chart-bell-curve",
        "device_class": SensorDeviceClass.MONETARY,
        "state_class": SensorStateClass.MEASUREMENT,
    },
    "prices_today": {
        "name_suffix": "Preise Heute",
        "icon": "mdi:calendar-today",
        "device_class": None,
        "state_class": None,
    },
    "prices_tomorrow": {
        "name_suffix": "Preise Morgen",
        "icon": "mdi:calendar-arrow-right",
        "device_class": None,
        "state_class": None,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Set up the sensor platform.

    Args:
        hass: Home Assistant instance
        config_entry: Config entry
        async_add_entities: Callback to add entities

    Returns:
        bool: True if setup was successful
    """
    config = config_entry.data
    tariff: str = config.get(CONF_TARIFF)
    additional_costs: str = config.get(CONF_ADDITIONAL_COSTS, DEFAULT_TEMPLATE)

    api = hass.data[DOMAIN]

    # Create all sensors
    sensors: list[SensorEntity] = [
        HaStromFlexCurrentPriceSensor(tariff, additional_costs, api, hass),
        HaStromFlexAverageSensor(tariff, additional_costs, api, hass),
        HaStromFlexMinSensor(tariff, additional_costs, api, hass),
        HaStromFlexMaxSensor(tariff, additional_costs, api, hass),
        HaStromFlexMedianSensor(tariff, additional_costs, api, hass),
        HaStromFlexTodayPricesSensor(tariff, additional_costs, api, hass),
        HaStromFlexTomorrowPricesSensor(tariff, additional_costs, api, hass),
    ]

    async_add_entities(sensors)
    return True


class HaStromFlexBaseSensor(SensorEntity):
    """Base class for all haStrom Flex sensors."""

    _sensor_type: str = ""  # Wird von Unterklassen überschrieben

    def __init__(
        self, tariff: str, additional_costs: str, api: Any, hass: HomeAssistant
    ) -> None:
        """Initialize the base sensor.

        Args:
            tariff: Tariff type
            additional_costs: Additional costs template or value
            api: API data holder
            hass: Home Assistant instance
        """
        self._tariff = tariff
        self._api = api
        self._hass = hass
        self._attr_force_update = True

        # Price data
        self._current_price: dict | None = None
        self._data_today: dict | object = SENTINEL
        self._data_tomorrow: dict | object = SENTINEL

        # Statistics
        self._average: float | None = None
        self._max: float | None = None
        self._min: float | None = None
        self._median: float | None = None
        self._additional_costs_value: float | None = None

        # Set up additional costs
        self._additional_costs_raw = additional_costs
        if not isinstance(additional_costs, Template):
            if additional_costs in (None, ""):
                additional_costs = DEFAULT_TEMPLATE
            self._ad_template = cv.template(additional_costs)
        else:
            if additional_costs.template in ("", None):
                self._ad_template = cv.template(DEFAULT_TEMPLATE)
            else:
                self._ad_template = additional_costs

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, f"hastrom_flex_{self._tariff}")},
            "name": TARIFF_NAMES.get(self._tariff, "haStrom Flex"),
            "manufacturer": "Stadtwerk Haßfurt",
            "model": TARIFF_NAMES.get(self._tariff, "haStrom Flex"),
        }

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    def _calc_price(
        self, value: dict | None = None, fake_dt: datetime | None = None
    ) -> float | None:
        """Calculate price including additional costs."""
        if value is None:
            value = self._current_price

        if value is None:
            return None

        # Get the appropriate price field
        price_field = PRICE_FIELDS.get(self._tariff, {}).get("total_price")
        if not price_field or price_field not in value:
            _LOGGER.warning("Price field %s not found in data", price_field)
            return None

        price = float(value[price_field])

        # Apply additional costs
        try:
            # First, try simple number
            try:
                template_value = float(self._additional_costs_raw)
            except (ValueError, TypeError):
                # Try safe math expression (keine eval()!)
                try:
                    template_value = safe_math_eval(self._additional_costs_raw)
                    if not isinstance(template_value, (int, float)):
                        raise ValueError("Expression did not return a number")
                except ValueError:
                    # Fall back to template
                    def faker() -> Any:
                        def inner(*_: Any, **__: Any) -> datetime:
                            return fake_dt or dt_utils.now()

                        return inner

                    template_value = self._ad_template.async_render(
                        now=faker(), current_price=price
                    )

                    # Convert to float if necessary
                    if not isinstance(template_value, (int, float)):
                        template_value = float(template_value)

            self._additional_costs_value = float(template_value)
            price += template_value
        except Exception as e:
            _LOGGER.error("Failed to apply additional costs: %s", e)
            self._additional_costs_value = 0.0

        return round(price, 2)

    def _update_current_price(self) -> None:
        """Update the current price based on current time."""
        if self._data_today is SENTINEL or not self._data_today:
            return

        now = dt_utils.now()

        for item in self._data_today.get("values", []):
            if item["start"] <= now < item["end"]:
                self._current_price = item["data"]
                return

    def _update_statistics(self) -> None:
        """Update statistics from today's data."""
        today_prices = self._get_today_prices()

        if not today_prices or len(today_prices) == 0:
            return

        self._average = round(mean(today_prices), 2)
        self._min = round(min(today_prices), 2)
        self._max = round(max(today_prices), 2)
        self._median = round(median(today_prices), 2)

    def _get_today_prices(self) -> list[float]:
        """Get today's prices as a list."""
        if self._data_today is SENTINEL or not self._data_today:
            return []

        prices = []
        for item in sorted(self._data_today.get("values", []), key=lambda x: x["start"]):
            price = self._calc_price(item["data"], fake_dt=item["start"])
            if price is not None:
                prices.append(price)

        return prices

    def _get_tomorrow_prices(self) -> list[float]:
        """Get tomorrow's prices as a list."""
        if self._data_tomorrow is SENTINEL or not self._data_tomorrow:
            return []

        prices: list[float] = []
        for item in sorted(
            self._data_tomorrow.get("values", []), key=lambda x: x["start"]
        ):
            price = self._calc_price(item["data"], fake_dt=item["start"])
            if price is not None:
                prices.append(price)

        return prices

    def _get_raw_today(self) -> list[dict[str, Any]]:
        """Get today's prices with timestamps."""
        if self._data_today is SENTINEL or not self._data_today:
            return []

        result: list[dict[str, Any]] = []
        for item in sorted(
            self._data_today.get("values", []), key=lambda x: x["start"]
        ):
            result.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "value": self._calc_price(item["data"], fake_dt=item["start"]),
                }
            )

        return result

    def _get_raw_tomorrow(self) -> list[dict[str, Any]]:
        """Get tomorrow's prices with timestamps."""
        if self._data_tomorrow is SENTINEL or not self._data_tomorrow:
            return []

        result: list[dict[str, Any]] = []
        for item in sorted(
            self._data_tomorrow.get("values", []), key=lambda x: x["start"]
        ):
            result.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "value": self._calc_price(item["data"], fake_dt=item["start"]),
                }
            )

        return result

    async def handle_new_hour(self) -> None:
        """Handle new hour event."""
        # Fetch today's data
        today = await self._api.get_today(self._tariff)
        if today:
            self._data_today = today

        # Check if we should fetch tomorrow's data
        now = dt_utils.now()
        if self._data_tomorrow is SENTINEL and now.hour >= 13:
            tomorrow = await self._api.get_tomorrow(self._tariff)
            if tomorrow:
                self._data_tomorrow = tomorrow

        # Update current price and statistics
        self._update_current_price()
        self._update_statistics()
        self.async_write_ha_state()

    async def handle_new_day(self) -> None:
        """Handle new day event."""
        self._data_tomorrow = SENTINEL
        await self.handle_new_hour()

    async def handle_new_price(self) -> None:
        """Handle new price event (tomorrow's prices available)."""
        tomorrow = await self._api.get_tomorrow(self._tariff)
        if tomorrow:
            self._data_tomorrow = tomorrow

        await self.handle_new_hour()

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher and fetch initial data."""
        await super().async_added_to_hass()

        # Connect to events und speichere Unsubscribe-Handler für Cleanup
        self.async_on_remove(
            async_dispatcher_connect(self._hass, EVENT_NEW_DAY, self.handle_new_day)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass, EVENT_NEW_PRICE, self.handle_new_price
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(self._hass, EVENT_NEW_HOUR, self.handle_new_hour)
        )

        # Initial data fetch
        await self.handle_new_hour()


class HaStromFlexCurrentPriceSensor(HaStromFlexBaseSensor):
    """Sensor for current electricity price."""

    _sensor_type = "current_price"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_current_price"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UNIT_CT_PER_KWH

    @property
    def native_value(self) -> float | None:
        """Return the current price."""
        return self._calc_price()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes."""
        return {
            "tariff": TARIFF_NAMES.get(self._tariff, self._tariff),
            "tariff_type": self._tariff,
            "average": self._average,
            "min": self._min,
            "max": self._max,
            "median": self._median,
            "today": self._get_today_prices(),
            "tomorrow": self._get_tomorrow_prices(),
            "tomorrow_valid": len(self._get_tomorrow_prices()) >= 23,
            "raw_today": self._get_raw_today(),
            "raw_tomorrow": self._get_raw_tomorrow(),
            "additional_costs_current_hour": self._additional_costs_value,
            "unit": UNIT_CT_PER_KWH,
        }


class HaStromFlexAverageSensor(HaStromFlexBaseSensor):
    """Sensor for average electricity price today."""

    _sensor_type = "average"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_average"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UNIT_CT_PER_KWH

    @property
    def native_value(self) -> float | None:
        """Return the average price."""
        return self._average


class HaStromFlexMinSensor(HaStromFlexBaseSensor):
    """Sensor for minimum electricity price today."""

    _sensor_type = "min"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_min"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UNIT_CT_PER_KWH

    @property
    def native_value(self) -> float | None:
        """Return the minimum price."""
        return self._min


class HaStromFlexMaxSensor(HaStromFlexBaseSensor):
    """Sensor for maximum electricity price today."""

    _sensor_type = "max"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_max"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UNIT_CT_PER_KWH

    @property
    def native_value(self) -> float | None:
        """Return the maximum price."""
        return self._max


class HaStromFlexMedianSensor(HaStromFlexBaseSensor):
    """Sensor for median electricity price today."""

    _sensor_type = "median"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_median"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return UNIT_CT_PER_KWH

    @property
    def native_value(self) -> float | None:
        """Return the median price."""
        return self._median


class HaStromFlexTodayPricesSensor(HaStromFlexBaseSensor):
    """Sensor containing all today's prices."""

    _sensor_type = "prices_today"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_prices_today"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_value(self) -> str:
        """Return the state."""
        prices = self._get_today_prices()
        return f"{len(prices)} Stunden" if prices else "Keine Daten"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all today's prices as attributes."""
        return {
            "prices": self._get_today_prices(),
            "raw_data": self._get_raw_today(),
            "tariff": TARIFF_NAMES.get(self._tariff, self._tariff),
            "unit": UNIT_CT_PER_KWH,
        }


class HaStromFlexTomorrowPricesSensor(HaStromFlexBaseSensor):
    """Sensor containing all tomorrow's prices."""

    _sensor_type = "prices_tomorrow"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        tariff_name = TARIFF_NAMES.get(self._tariff, self._tariff)
        return f"{tariff_name} {SENSOR_TYPES[self._sensor_type]['name_suffix']}"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"hastrom_flex_{self._tariff}_prices_tomorrow"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def native_value(self) -> str:
        """Return the state."""
        prices = self._get_tomorrow_prices()
        if len(prices) >= 23:
            return f"{len(prices)} Stunden"
        elif len(prices) > 0:
            return f"{len(prices)} Stunden (unvollständig)"
        else:
            return "Noch nicht verfügbar"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return all tomorrow's prices as attributes."""
        return {
            "prices": self._get_tomorrow_prices(),
            "raw_data": self._get_raw_tomorrow(),
            "tariff": TARIFF_NAMES.get(self._tariff, self._tariff),
            "valid": len(self._get_tomorrow_prices()) >= 23,
            "unit": UNIT_CT_PER_KWH,
        }
