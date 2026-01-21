"""Constants for the Stadtwerk Haßfurt haStrom Flex integration."""
from __future__ import annotations

DOMAIN = "hastrom_flex"
NAME = "Stadtwerk Haßfurt haStrom Flex"
VERSION = "1.1.0"

# API Configuration
API_BASE_URL = "http://eex.stwhas.de/api"
API_ENDPOINT_FLEX = "/spotprices"
API_ENDPOINT_FLEX_PRO = "/spotprices/flexpro"
API_ENDPOINT_RAW = "/spotprices/raw"
API_TIMEOUT_SECONDS = 30

# Events
EVENT_NEW_HOUR = "hastrom_flex_update_hour"
EVENT_NEW_DAY = "hastrom_flex_update_day"
EVENT_NEW_PRICE = "hastrom_flex_update_new_price"

# Random time range for updates to avoid server overload
# Actual random value wird in __init__.py generiert
RANDOM_MINUTE_MIN = 10
RANDOM_MINUTE_MAX = 30

# Tariff types
TARIFF_FLEX = "flex"
TARIFF_FLEX_PRO = "flex_pro"
TARIFF_RAW = "raw"

TARIFF_LIST = [TARIFF_FLEX, TARIFF_FLEX_PRO, TARIFF_RAW]

TARIFF_NAMES = {
    TARIFF_FLEX: "haStrom Flex",
    TARIFF_FLEX_PRO: "haStrom Flex Pro",
    TARIFF_RAW: "EPEX Spot (Raw)",
}

# Price fields by tariff
PRICE_FIELDS = {
    TARIFF_FLEX: {
        "energy_price": "e_price_has_incl_vat",
        "total_price": "t_price_has_incl_vat",
        "epex_price": "e_price_epex_excl_vat",
    },
    TARIFF_FLEX_PRO: {
        "energy_price": "e_price_has_pro_incl_vat",
        "total_price": "t_price_has_pro_incl_vat",
        "epex_price": "e_price_epex_excl_vat",
    },
    TARIFF_RAW: {
        "energy_price": "epex_spot_price",
        "total_price": "epex_spot_price",
        "epex_price": "epex_spot_price",
    },
}

# Configuration
CONF_TARIFF = "tariff"
CONF_ADDITIONAL_COSTS = "additional_costs"

# Defaults
DEFAULT_TARIFF = TARIFF_FLEX
DEFAULT_NAME = "haStrom Flex"
DEFAULT_TEMPLATE = "{{0.0|float}}"

# Units
UNIT_CT_PER_KWH = "ct/kWh"
CURRENCY = "EUR"

# Timezone
TIMEZONE = "Europe/Berlin"

# Sentinel object
SENTINEL = object()
