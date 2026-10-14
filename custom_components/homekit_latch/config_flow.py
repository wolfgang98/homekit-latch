"""Config flow for HomeKit Latch."""

from __future__ import annotations

import random
import socket
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_ENTITY_ID,
    CONF_EXPOSE_LOCK,
    CONF_LATCH_ACTION,
    CONF_LATCH_NAME,
    CONF_NAME,
    CONF_PINCODE,
    CONF_PORT,
    CONF_RESET_SECONDS,
    DEFAULT_EXPOSE_LOCK,
    DEFAULT_LATCH_ACTION,
    DEFAULT_LATCH_NAME,
    DEFAULT_RESET_SECONDS,
    DOMAIN,
    FIRST_PORT,
    INVALID_PINCODES,
    LAST_PORT,
    LATCH_ACTION_OPEN,
    LATCH_ACTION_UNLOCK,
)


def _generate_pincode() -> str:
    """A random setup code in the form 123-45-678 that HomeKit accepts."""
    while True:
        digits = f"{random.SystemRandom().randrange(10**8):08d}"
        code = f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
        if code not in INVALID_PINCODES:
            return code


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("", port))
        except OSError:
            return False
    return True


def _pick_port(used: set[int]) -> int | None:
    for port in range(FIRST_PORT, LAST_PORT + 1):
        if port not in used and _port_is_free(port):
            return port
    return None


def _settings_schema(defaults: dict[str, Any]) -> dict[Any, Any]:
    """Fields that can be changed later in the options."""
    return {
        vol.Required(
            CONF_LATCH_NAME, default=defaults.get(CONF_LATCH_NAME, DEFAULT_LATCH_NAME)
        ): str,
        vol.Required(
            CONF_LATCH_ACTION,
            default=defaults.get(CONF_LATCH_ACTION, DEFAULT_LATCH_ACTION),
        ): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[LATCH_ACTION_OPEN, LATCH_ACTION_UNLOCK],
                translation_key="latch_action",
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Required(
            CONF_RESET_SECONDS,
            default=defaults.get(CONF_RESET_SECONDS, DEFAULT_RESET_SECONDS),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=30,
                step=1,
                unit_of_measurement="s",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_EXPOSE_LOCK,
            default=defaults.get(CONF_EXPOSE_LOCK, DEFAULT_EXPOSE_LOCK),
        ): bool,
    }


class HomeKitLatchConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one lock as a HomeKit accessory with a latch."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ENTITY_ID])
            self._abort_if_unique_id_configured()
            used = {
                entry.data[CONF_PORT]
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            }
            port = await self.hass.async_add_executor_job(_pick_port, used)
            if port is None:
                errors["base"] = "no_free_port"
            else:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        **user_input,
                        CONF_PORT: port,
                        CONF_PINCODE: _generate_pincode(),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="lock")
                ),
                vol.Required(CONF_NAME): str,
                **_settings_schema(user_input or {}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        return HomeKitLatchOptionsFlow()


class HomeKitLatchOptionsFlow(OptionsFlow):
    """Change latch name, action, reset time or whether the lock is shown."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(_settings_schema(current))
        )
