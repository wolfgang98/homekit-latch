"""Constants for HomeKit Latch."""

DOMAIN = "homekit_latch"

CONF_NAME = "name"
CONF_ENTITY_ID = "entity_id"
CONF_LATCH_NAME = "latch_name"
CONF_LATCH_ACTION = "latch_action"
CONF_RESET_SECONDS = "reset_seconds"
CONF_EXPOSE_LOCK = "expose_lock"
CONF_PORT = "port"
CONF_PINCODE = "pincode"

# What the latch service does when it is moved to "unsecured".
LATCH_ACTION_OPEN = "open"  # lock.open (unlatch / electric strike)
LATCH_ACTION_UNLOCK = "unlock"  # lock.unlock

DEFAULT_LATCH_NAME = "Open"
DEFAULT_LATCH_ACTION = LATCH_ACTION_OPEN
DEFAULT_RESET_SECONDS = 3
DEFAULT_EXPOSE_LOCK = True

FIRST_PORT = 21100
LAST_PORT = 21199

MDNS_TARGET_IP = "224.0.0.251"

# Pincodes HomeKit refuses.
INVALID_PINCODES = {
    "000-00-000",
    "111-11-111",
    "222-22-222",
    "333-33-333",
    "444-44-444",
    "555-55-555",
    "666-66-666",
    "777-77-777",
    "888-88-888",
    "999-99-999",
    "123-45-678",
    "876-54-321",
}
