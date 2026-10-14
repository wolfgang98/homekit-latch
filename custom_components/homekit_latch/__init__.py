"""HomeKit Latch: a HomeKit lock with a second, momentary Latch lock service."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
import logging
import os
from typing import Any

from homeassistant.components import persistent_notification, zeroconf
from homeassistant.components.network import async_get_source_ip
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.storage import STORAGE_DIR
from pyhap.accessory_driver import AccessoryDriver

from .accessory import LatchLockAccessory
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
    MDNS_TARGET_IP,
)

_LOGGER = logging.getLogger(__name__)


class LatchDriver(AccessoryDriver):
    """HAP driver that tells us when a Home app has paired."""

    def __init__(self, *args: Any, on_paired: Any = None, **kwargs: Any) -> None:
        self._on_paired = on_paired
        super().__init__(*args, **kwargs)

    def pair(
        self,
        client_username_bytes: bytes,
        client_public: bytes,
        client_permissions: bytes,
    ) -> bool:
        """Called in the event loop when a client has paired."""
        success = super().pair(client_username_bytes, client_public, client_permissions)
        if success and self._on_paired:
            self._on_paired()
        return success


@dataclass
class RuntimeData:
    """What a running entry needs to be stopped again."""

    driver: LatchDriver
    accessory: LatchLockAccessory


type LatchConfigEntry = ConfigEntry[RuntimeData]


def _notification_id(entry: ConfigEntry) -> str:
    return f"{DOMAIN}_{entry.entry_id}"


def _show_setup_message(
    hass: HomeAssistant, entry: ConfigEntry, accessory: LatchLockAccessory
) -> None:
    """Show the pairing code, with a QR code when HomeKit's helper is there."""
    name = entry.data[CONF_NAME]
    pincode = entry.data[CONF_PINCODE]
    try:
        from homeassistant.components.homekit.util import (  # noqa: PLC0415
            async_show_setup_message,
        )

        async_show_setup_message(
            hass, entry.entry_id, name, pincode.encode(), accessory.xhm_uri()
        )
        return
    except Exception:  # noqa: BLE001 - internals of another integration
        _LOGGER.debug("HomeKit's QR helper is not usable, using plain text")
    persistent_notification.async_create(
        hass,
        f"Open the Home app, tap **+ → Add Accessory → More options**, pick "
        f"**{name}** and enter the code **{pincode}**.",
        title=f"Pair {name} with HomeKit",
        notification_id=_notification_id(entry),
    )


def _dismiss_setup_message(hass: HomeAssistant, entry: ConfigEntry) -> None:
    try:
        from homeassistant.components.homekit.util import (  # noqa: PLC0415
            async_dismiss_setup_message,
        )

        async_dismiss_setup_message(hass, entry.entry_id)
    except Exception:  # noqa: BLE001
        pass
    persistent_notification.async_dismiss(hass, _notification_id(entry))


def _persist_file(hass: HomeAssistant, entry: ConfigEntry) -> str:
    return hass.config.path(STORAGE_DIR, f"{DOMAIN}.{entry.entry_id}.state")


async def async_setup_entry(hass: HomeAssistant, entry: LatchConfigEntry) -> bool:
    """Start the HomeKit accessory for one lock."""
    cfg = {**entry.data, **entry.options}
    address = await async_get_source_ip(hass, MDNS_TARGET_IP)
    zc = await zeroconf.async_get_async_instance(hass)

    @callback
    def paired() -> None:
        _dismiss_setup_message(hass, entry)

    def build() -> tuple[LatchDriver, LatchLockAccessory]:
        # AccessoryDriver reads and writes its state file: not in the loop.
        driver = LatchDriver(
            address=address,
            port=cfg[CONF_PORT],
            persist_file=_persist_file(hass, entry),
            pincode=entry.data[CONF_PINCODE].encode(),
            loop=hass.loop,
            async_zeroconf_instance=zc,
            on_paired=paired,
        )
        accessory = LatchLockAccessory(
            driver,
            hass,
            name=cfg[CONF_NAME],
            entity_id=cfg[CONF_ENTITY_ID],
            latch_name=cfg.get(CONF_LATCH_NAME, DEFAULT_LATCH_NAME),
            latch_action=cfg.get(CONF_LATCH_ACTION, DEFAULT_LATCH_ACTION),
            reset_seconds=float(cfg.get(CONF_RESET_SECONDS, DEFAULT_RESET_SECONDS)),
            expose_lock=cfg.get(CONF_EXPOSE_LOCK, DEFAULT_EXPOSE_LOCK),
        )
        driver.add_accessory(accessory)
        return driver, accessory

    driver, accessory = await hass.async_add_executor_job(build)
    accessory.async_start()
    await driver.async_start()
    entry.runtime_data = RuntimeData(driver, accessory)

    if not driver.state.paired:
        _show_setup_message(hass, entry, accessory)

    async def _stop(_: Event) -> None:
        await _async_shutdown(entry)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _stop)
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: LatchConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_shutdown(entry: LatchConfigEntry) -> None:
    data = entry.runtime_data
    data.accessory.async_stop()
    await data.driver.async_stop()


async def async_unload_entry(hass: HomeAssistant, entry: LatchConfigEntry) -> bool:
    """Stop the accessory."""
    await _async_shutdown(entry)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: LatchConfigEntry) -> None:
    """Forget the pairing state and the pairing message."""
    _dismiss_setup_message(hass, entry)
    await hass.async_add_executor_job(
        partial(_remove_file, _persist_file(hass, entry))
    )


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
