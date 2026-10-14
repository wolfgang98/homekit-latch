# HomeKit Latch

A Home Assistant integration that shows a lock in Apple Home **as one accessory with two lock services**: the lock itself and a momentary **Latch**. It does what the `latch` option of Homebridge's Nuki plugin does, but inside Home Assistant.

- **Lock service:** mirrors your lock entity (locked / unlocked, tap to lock or unlock).
- **Latch service:** moving it to *unsecured* calls `lock.open` on the same entity (for a Nuki: unlatch, or the electric strike of an Opener). After a few seconds it falls back to *secured* on its own. Moving it back does nothing.

Apple Home normally shows the accessory as one tile; the second lock sits behind a long press (or use **Show as Separate Tiles** in the accessory settings).

> Status: 0.1.0, written against HAP-python's API and tested with a stubbed Home Assistant only. Not yet run on a real Home Assistant, so expect to report problems.

## Install (HACS)

1. HACS → ⋮ → **Custom repositories** → add `https://github.com/wolfgang98/homekit-latch`, category **Integration**.
2. Download **HomeKit Latch**, restart Home Assistant.
3. **Settings → Devices & services → Add integration → HomeKit Latch**.

## Add a lock

| Field | Meaning |
| --- | --- |
| Lock | A `lock` entity, e.g. your Nuki Smart Lock |
| Name in Apple Home | Name of the accessory and of its lock service |
| Name of the latch | Name of the second lock, e.g. "Eingangstüre öffnen" |
| Latch action | `open` = `lock.open` (unlatch / strike), `unlock` = `lock.unlock` |
| Fall back after | Seconds until the latch is back to secured (default 3) |
| Also show the lock itself | Turn **off** for a Nuki Opener: its lock state is Ring to Open, so only the latch is exposed |

Home Assistant then shows a notification with a QR code and the setup code. In the Home app: **+ → Add Accessory**, scan the code. Each lock is its own HomeKit accessory with its own code, like locks in HA's HomeKit Bridge accessory mode.

Do **not** also expose the same lock through HA's HomeKit Bridge, or it shows up twice.

## How it works

Each entry runs its own HAP accessory (HAP-python, the library HA's HomeKit integration uses) on a port from 21100 to 21199, advertised through Home Assistant's zeroconf instance. The accessory builds two `LockMechanism` services and listens to the entity's state. The integration depends on `homekit`, `zeroconf` and `network`, so HAP-python is installed by Home Assistant itself.

Allow the ports above from your phone's VLAN if the server sits on another network, and make sure mDNS reaches it (UniFi: mDNS reflector).

## Notes and limits

- Pairing state lives in `.storage/homekit_latch.<entry id>.state`. Removing the entry removes it; also remove the accessory in the Home app.
- The latch only fires when the Home app moves it to *unsecured*. Do not put it in automations or scenes that run on their own.
- If `lock.open` fails (the entity does not support it), the latch falls back at once and the error is in the log.
- It relies on HAP-python and Home Assistant internals that can change between releases.

## Development

`custom_components/homekit_latch/accessory.py` only needs HAP-python plus a handful of Home Assistant helpers, so the accessory can be exercised with a stub of `hass`. CI runs hassfest and the HACS validation.
