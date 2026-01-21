"""Config flow for Stadtwerk Haßfurt haStrom Flex integration."""
from __future__ import annotations

import ast
import logging
import operator
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.template import Template

from .const import (
    CONF_ADDITIONAL_COSTS,
    CONF_TARIFF,
    DEFAULT_TARIFF,
    DEFAULT_TEMPLATE,
    DOMAIN,
    TARIFF_LIST,
    TARIFF_NAMES,
)

_LOGGER = logging.getLogger(__name__)

# Sichere mathematische Operatoren für safe_eval
_SAFE_OPERATORS = {
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
    """Evaluiere einen AST-Knoten sicher (nur mathematische Operationen).

    Args:
        node: AST-Knoten zum Evaluieren

    Returns:
        Numerisches Ergebnis

    Raises:
        ValueError: Bei ungültigen Operationen
    """
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
    """Evaluiere einen mathematischen Ausdruck sicher.

    Args:
        expression: Mathematischer Ausdruck als String

    Returns:
        Numerisches Ergebnis

    Raises:
        ValueError: Bei ungültigen Ausdrücken
    """
    try:
        tree = ast.parse(expression, mode="eval")
        return _safe_eval_node(tree.body)
    except (SyntaxError, TypeError) as e:
        raise ValueError(f"Ungültiger Ausdruck: {e}") from e


class HaStromFlexConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Stadtwerk Haßfurt haStrom Flex."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        self._errors = {}

        if user_input is not None:
            # Validate template
            template_ok = False
            if user_input[CONF_ADDITIONAL_COSTS] in (None, ""):
                user_input[CONF_ADDITIONAL_COSTS] = DEFAULT_TEMPLATE
                template_ok = True
            else:
                # Remove excessive whitespace
                user_input[CONF_ADDITIONAL_COSTS] = re.sub(
                    r"\s{2,}", "", user_input[CONF_ADDITIONAL_COSTS]
                )
                template_ok = await self._valid_template(
                    user_input[CONF_ADDITIONAL_COSTS]
                )

            if template_ok:
                # Create unique ID based on tariff
                await self.async_set_unique_id(
                    f"{DOMAIN}_{user_input[CONF_TARIFF]}"
                )
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=TARIFF_NAMES.get(
                        user_input[CONF_TARIFF], "Stadtwerk Haßfurt haStrom Flex"
                    ),
                    data=user_input,
                )
            else:
                self._errors["base"] = "invalid_template"

        # Build the configuration schema
        data_schema = vol.Schema(
            {
                vol.Required(CONF_TARIFF, default=DEFAULT_TARIFF): vol.In(
                    {tariff: TARIFF_NAMES[tariff] for tariff in TARIFF_LIST}
                ),
                vol.Optional(CONF_ADDITIONAL_COSTS, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=self._errors,
            description_placeholders={
                "tariff": ", ".join([TARIFF_NAMES[t] for t in TARIFF_LIST]),
                "additional_costs": "{{0.0|float}}",
            },
        )

    async def _valid_template(self, user_template: str) -> bool:
        """Validate the additional costs template.

        Args:
            user_template: Template string to validate

        Returns:
            bool: True if template is valid
        """
        try:
            # First, try to parse as a simple number
            try:
                float(user_template)
                _LOGGER.debug("Valid simple number: %s", user_template)
                return True
            except ValueError:
                pass

            # Try to evaluate as a safe math expression (keine eval()!)
            try:
                result = safe_math_eval(user_template)
                if isinstance(result, (int, float)):
                    _LOGGER.debug(
                        "Valid math expression: %s = %s", user_template, result
                    )
                    return True
            except ValueError:
                pass

            # Finally, try as a Jinja2 template
            ut = Template(user_template, self.hass).async_render(
                current_price=0,
            )
            _LOGGER.debug("Template validation: %s -> %s", user_template, ut)

            # Check if result is a float
            return isinstance(ut, (int, float))
        except Exception as e:
            _LOGGER.error("Template validation failed: %s", e)
            return False
