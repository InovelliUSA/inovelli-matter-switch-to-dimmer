"""Virtual dimmer light backed by a raw Matter Level Control endpoint."""

from __future__ import annotations

from typing import Any

from chip.clusters import Objects as clusters
from chip.clusters.Objects import NullValue
from matter_server.common.errors import MatterError, NodeNotExists
from matter_server.common.models import EventType

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ENDPOINT_ID, CONF_NODE_ID, DOMAIN

MATTER_LEVEL_MAX = 254
HA_BRIGHTNESS_MAX = 255


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the virtual Matter level light."""
    try:
        from homeassistant.components.matter.helpers import get_matter

        matter_client = get_matter(hass).matter_client
        node_id = entry.data[CONF_NODE_ID]
        endpoint_id = entry.data[CONF_ENDPOINT_ID]
        node = matter_client.get_node(node_id)
        endpoint = node.endpoints.get(endpoint_id)
    except (AttributeError, IndexError, NodeNotExists, RuntimeError) as err:
        raise ConfigEntryNotReady("Matter integration is not ready") from err

    if endpoint is None:
        raise ConfigEntryNotReady(
            f"Matter endpoint {node_id}/{endpoint_id} is unavailable"
        )

    async_add_entities(
        [InovelliMatterDimmerLight(entry, matter_client, node_id, endpoint_id)]
    )


class InovelliMatterDimmerLight(LightEntity):
    """Represent a Matter Level Control server as a Home Assistant light."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}
    _attr_color_mode = ColorMode.BRIGHTNESS

    def __init__(self, entry: ConfigEntry, matter_client, node_id: int, endpoint_id: int):
        """Initialize the proxy light."""
        self._client = matter_client
        self._node_id = node_id
        self._endpoint_id = endpoint_id
        self._current_level_path = f"{endpoint_id}/8/0"
        self._on_off_path = f"{endpoint_id}/6/0"

        server_info = matter_client.server_info
        fabric_id = server_info.compressed_fabric_id if server_info else 0
        identity = f"{fabric_id:016x}-{node_id}-{endpoint_id}"

        self._attr_unique_id = f"inovelli-matter-dimmer-{identity}"
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=entry.title,
            manufacturer="Inovelli",
            model=f"Node {node_id}, endpoint {endpoint_id}",
        )
        self._update_from_cache()

    @callback
    def _get_endpoint(self):
        """Return the current endpoint model from the shared Matter client."""
        node = self._client.get_node(self._node_id)
        return node, node.endpoints.get(self._endpoint_id)

    @callback
    def _update_from_cache(self) -> None:
        """Update entity state from the Matter client's subscription cache."""
        try:
            node, endpoint = self._get_endpoint()
        except NodeNotExists:
            self._attr_available = False
            return

        self._attr_available = bool(node.available and endpoint is not None)
        if endpoint is None:
            return

        level = endpoint.get_attribute_value(
            None, clusters.LevelControl.Attributes.CurrentLevel
        )
        on_off = endpoint.get_attribute_value(None, clusters.OnOff.Attributes.OnOff)

        if level == NullValue or level is None:
            self._attr_brightness = None
            raw_level = None
        else:
            raw_level = max(0, min(MATTER_LEVEL_MAX, int(level)))
            self._attr_brightness = round(
                raw_level * HA_BRIGHTNESS_MAX / MATTER_LEVEL_MAX
            )

        if on_off == NullValue or on_off is None:
            self._attr_is_on = bool(raw_level)
        else:
            self._attr_is_on = bool(on_off)

        self._attr_extra_state_attributes = {
            "matter_node_id": self._node_id,
            "matter_endpoint_id": self._endpoint_id,
            "matter_current_level": raw_level,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to Matter attribute and availability updates."""
        await super().async_added_to_hass()

        for event_filter, attr_path in (
            (EventType.ATTRIBUTE_UPDATED, self._current_level_path),
            (EventType.ATTRIBUTE_UPDATED, self._on_off_path),
            (EventType.NODE_UPDATED, None),
        ):
            unsubscribe = self._client.subscribe_events(
                callback=self._handle_matter_update,
                event_filter=event_filter,
                node_filter=self._node_id,
                attr_path_filter=attr_path,
            )
            self.async_on_remove(unsubscribe)

        # Force one fresh read. Failure is non-fatal because the subscription cache
        # obtained during the Matter interview is still usable.
        try:
            await self._refresh_state()
        except MatterError:
            pass
        self._update_from_cache()
        self.async_write_ha_state()

    @callback
    def _handle_matter_update(self, event: EventType, data: Any = None) -> None:
        """Handle a Matter subscription update."""
        self._update_from_cache()
        self.async_write_ha_state()

    async def _refresh_state(self) -> None:
        """Refresh OnOff and CurrentLevel in the shared Matter cache."""
        await self._client.refresh_attribute(
            self._node_id, self._current_level_path
        )
        await self._client.refresh_attribute(self._node_id, self._on_off_path)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on or set the endpoint level."""
        try:
            if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is None:
                command = clusters.OnOff.Commands.On()
            else:
                level = max(
                    1,
                    min(
                        MATTER_LEVEL_MAX,
                        round(int(brightness) * MATTER_LEVEL_MAX / HA_BRIGHTNESS_MAX),
                    ),
                )
                transition = float(kwargs.get(ATTR_TRANSITION, 0))
                command = clusters.LevelControl.Commands.MoveToLevelWithOnOff(
                    level=level,
                    transitionTime=max(0, round(transition * 10)),
                )

            await self._client.send_device_command(
                node_id=self._node_id,
                endpoint_id=self._endpoint_id,
                command=command,
            )
            await self._refresh_state()
        except MatterError as err:
            raise HomeAssistantError(str(err) or err.__class__.__name__) from err

        self._update_from_cache()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the endpoint."""
        try:
            await self._client.send_device_command(
                node_id=self._node_id,
                endpoint_id=self._endpoint_id,
                command=clusters.OnOff.Commands.Off(),
            )
            await self._refresh_state()
        except MatterError as err:
            raise HomeAssistantError(str(err) or err.__class__.__name__) from err

        self._update_from_cache()
        self.async_write_ha_state()
