# Inovelli Matter Switch-to-Dimmer

Inovelli Matter Switch-to-Dimmer is a Home Assistant custom integration that
creates a virtual brightness light for an existing Matter endpoint, even when
Home Assistant normally exposes that endpoint only as an on/off switch.

It uses Home Assistant's existing Matter connection. It does not create a new
Matter endpoint and does not alter the device firmware, QR code, DCL record, or
certification.

## Tested target

The initial target is the Inovelli VTM30-SN shown in the supplied diagnostics:

- Matter node ID: `101`
- Endpoint ID: `1`
- On/Off server: cluster `0x0006`
- Level Control server: cluster `0x0008`
- CurrentLevel path: `1/8/0`

The integration is configurable and can be used with another node or endpoint
that exposes both `OnOff.OnOff` and `LevelControl.CurrentLevel`.

## Installation

1. Copy `custom_components/inovelli_matter_dimmer` into Home Assistant's
   `/config/custom_components/` directory.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration**.
4. Search for **Inovelli Matter Switch-to-Dimmer**.
5. Enter a name, Matter node ID, and endpoint ID. For the supplied diagnostics,
   use node `101` and endpoint `1`.

The integration creates a Home Assistant `light` entity with brightness control.
The original Matter `switch` entity remains available and can be hidden.

## Behavior

- Turning the virtual light on sends the standard Matter `On` command.
- Turning it off sends the standard Matter `Off` command.
- Changing brightness sends `MoveToLevelWithOnOff` to the configured endpoint.
- State follows Matter subscription updates for `OnOff` and `CurrentLevel`.
- Matter levels `0–254` are converted to Home Assistant brightness `0–255`.

The physical VTM30 output may remain binary even when `CurrentLevel` stores an
intermediate value. This integration does not automatically forward commands
through the switch's binding endpoint; that behavior would require firmware
support or separate control of the bound target.

## Compatibility note

This integration imports Home Assistant's internal Matter helper to share the
existing Matter client. It is designed for Home Assistant 2026.8.x and may need
minor updates if Home Assistant changes its internal Matter API.

## Why not a blueprint or template helper?

Home Assistant does not currently expose a generic Matter cluster-command action.
A blueprint can only call actions that already exist, and a template light cannot
read a raw Matter attribute unless another integration first exposes it. A custom
integration is therefore required to turn this raw endpoint into an entity.
