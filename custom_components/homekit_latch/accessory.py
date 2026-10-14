"""One HomeKit accessory with two Lock Mechanism services: Lock and Latch.

The first service mirrors a Home Assistant lock entity (state, lock, unlock).
The second one is momentary: moving it to "unsecured" runs lock.open (or
lock.unlock) on the same entity and, after a few seconds, it falls back to
"secured" on its own. Homebridge's Nuki plugin calls this option `latch`.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from pyhap.accessory import Accessory
from pyhap.const import CATEGORY_DOOR_LOCK, STANDALONE_AID

from .const import LATCH_ACTION_OPEN

_LOGGER = logging.getLogger(__name__)

# HomeKit LockCurrentState / LockTargetState values.
UNSECURED = 0
SECURED = 1
JAMMED = 2
UNKNOWN = 3

# How long to wait for the lock to follow a lock/unlock request from the Home
# app before the tile is set back to what the entity really reports.
RESYNC_SECONDS = 10


def map_state(state: str) -> tuple[int | None, int | None]:
    """Map a Home Assistant lock state to (current, target) HomeKit values.

    None means "leave that characteristic as it is".
    """
    if state == "locked":
        return SECURED, SECURED
    if state in ("unlocked", "open", "opening"):
        return UNSECURED, UNSECURED
    if state == "locking":
        return None, SECURED
    if state == "unlocking":
        return None, UNSECURED
    if state == "jammed":
        return JAMMED, None
    return UNKNOWN, None


class LatchLockAccessory(Accessory):
    """Standalone HomeKit accessory: Lock service plus Latch service."""

    category = CATEGORY_DOOR_LOCK

    def __init__(
        self,
        driver: Any,
        hass: HomeAssistant,
        *,
        name: str,
        entity_id: str,
        latch_name: str,
        latch_action: str,
        reset_seconds: float,
        expose_lock: bool,
    ) -> None:
        super().__init__(driver, name, aid=STANDALONE_AID)
        self._hass = hass
        self._entity_id = entity_id
        self._latch_action = latch_action
        self._reset_seconds = reset_seconds
        self._expose_lock = expose_lock
        self._unsub: CALLBACK_TYPE | None = None
        self._latch_timer: Any = None
        self._resync_timer: Any = None

        self.set_info_service(
            firmware_revision="1.0",
            manufacturer="HomeKit Latch",
            model="Lock + Latch",
            serial_number=entity_id,
        )

        self._lock_current = None
        self._lock_target = None
        lock_service = None
        if expose_lock:
            lock_service = self.add_preload_service(
                "LockMechanism", chars=["Name"], unique_id="lock"
            )
            lock_service.configure_char("Name", value=name)
            self._lock_current = lock_service.get_characteristic("LockCurrentState")
            self._lock_target = lock_service.get_characteristic("LockTargetState")
            self._lock_current.set_value(UNKNOWN)
            self._lock_target.set_value(SECURED)
            self._lock_target.setter_callback = self._on_lock_target

        latch_service = self.add_preload_service(
            "LockMechanism", chars=["Name"], unique_id="latch"
        )
        latch_service.configure_char("Name", value=latch_name)
        self._latch_current = latch_service.get_characteristic("LockCurrentState")
        self._latch_target = latch_service.get_characteristic("LockTargetState")
        self._latch_current.set_value(SECURED)
        self._latch_target.set_value(SECURED)
        self._latch_target.setter_callback = self._on_latch_target

        if lock_service is not None:
            self.set_primary_service(lock_service)

    # -- lifecycle (event loop) ---------------------------------------------

    @callback
    def async_start(self) -> None:
        """Start following the entity."""
        self._unsub = async_track_state_change_event(
            self._hass, [self._entity_id], self._async_state_changed
        )
        self._sync_from_state(self._hass.states.get(self._entity_id))

    @callback
    def async_stop(self) -> None:
        """Stop following the entity and cancel pending timers."""
        if self._unsub:
            self._unsub()
            self._unsub = None
        for timer in (self._latch_timer, self._resync_timer):
            if timer:
                timer.cancel()
        self._latch_timer = None
        self._resync_timer = None

    # -- Home Assistant -> HomeKit ------------------------------------------

    @callback
    def _async_state_changed(self, event: Event) -> None:
        self._sync_from_state(event.data.get("new_state"))

    @callback
    def _sync_from_state(self, state: State | None) -> None:
        if self._lock_current is None:
            return
        if state is None:
            current, target = UNKNOWN, None
        else:
            current, target = map_state(state.state)
        if target is not None:
            self._lock_target.set_value(target)
        if current is not None:
            self._lock_current.set_value(current)

    # -- HomeKit -> Home Assistant ------------------------------------------
    # pyhap calls these from the event loop, but call_soon_threadsafe keeps
    # them correct even if that ever changes.

    def _on_lock_target(self, value: int) -> None:
        self._hass.loop.call_soon_threadsafe(self._start_lock_call, value)

    def _on_latch_target(self, value: int) -> None:
        self._hass.loop.call_soon_threadsafe(self._handle_latch, value)

    @callback
    def _start_lock_call(self, value: int) -> None:
        service = "lock" if value == SECURED else "unlock"
        self._hass.async_create_task(self._async_call(service))
        if self._resync_timer:
            self._resync_timer.cancel()
        self._resync_timer = self._hass.loop.call_later(
            RESYNC_SECONDS,
            lambda: self._sync_from_state(self._hass.states.get(self._entity_id)),
        )

    @callback
    def _handle_latch(self, value: int) -> None:
        if value == SECURED:
            # Moving the latch "back" never does anything but reset the tile.
            self._reset_latch()
            return
        if self._latch_timer is not None:
            return  # already open, a second tap does nothing
        service = "open" if self._latch_action == LATCH_ACTION_OPEN else "unlock"
        self._hass.async_create_task(self._async_open(service))
        self._latch_current.set_value(UNSECURED)
        self._latch_timer = self._hass.loop.call_later(
            self._reset_seconds, self._reset_latch
        )

    @callback
    def _reset_latch(self) -> None:
        if self._latch_timer:
            self._latch_timer.cancel()
            self._latch_timer = None
        self._latch_target.set_value(SECURED)
        self._latch_current.set_value(SECURED)

    async def _async_open(self, service: str) -> None:
        # Blocking, so a lock that cannot open (no "open" support, bridge
        # unreachable) ends up as an error and the tile falls back at once.
        if not await self._async_call(service, blocking=True):
            self._reset_latch()

    async def _async_call(self, service: str, blocking: bool = False) -> bool:
        try:
            await self._hass.services.async_call(
                "lock", service, {"entity_id": self._entity_id}, blocking=blocking
            )
        except HomeAssistantError as err:
            _LOGGER.error("lock.%s on %s failed: %s", service, self._entity_id, err)
            return False
        return True
