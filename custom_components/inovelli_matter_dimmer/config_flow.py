"""Config flow for Inovelli Matter Switch-to-Dimmer."""

from __future__ import annotations

from typing import Any

from chip.clusters import Objects as clusters
from matter_server.common.errors import NodeNotExists
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import (
    CONF_ENDPOINT_ID,
    CONF_NODE_ID,
    DEFAULT_ENDPOINT_ID,
    DEFAULT_NAME,
    DOMAIN,
)


class InovelliMatterDimmerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure an Inovelli Matter Switch-to-Dimmer light."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            node_id = user_input[CONF_NODE_ID]
            endpoint_id = user_input[CONF_ENDPOINT_ID]

            try:
                # This intentionally reuses Home Assistant's existing Matter fabric.
                # It is an internal HA API, so future HA releases may require updates.
                from homeassistant.components.matter.helpers import get_matter

                matter_client = get_matter(self.hass).matter_client
                node = matter_client.get_node(node_id)
                endpoint = node.endpoints.get(endpoint_id)
                if endpoint is None:
                    errors["base"] = "endpoint_not_found"
                elif not endpoint.has_attribute(
                    None, clusters.LevelControl.Attributes.CurrentLevel
                ):
                    errors["base"] = "current_level_missing"
                elif not endpoint.has_attribute(None, clusters.OnOff.Attributes.OnOff):
                    errors["base"] = "on_off_missing"
                else:
                    server_info = matter_client.server_info
                    fabric_id = (
                        server_info.compressed_fabric_id if server_info else 0
                    )
                    await self.async_set_unique_id(
                        f"{fabric_id:016x}-{node_id}-{endpoint_id}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input[CONF_NAME], data=user_input
                    )
            except (IndexError, NodeNotExists):
                errors["base"] = "node_not_found"
            except (AttributeError, RuntimeError):
                errors["base"] = "matter_not_ready"

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_NODE_ID): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Required(
                    CONF_ENDPOINT_ID, default=DEFAULT_ENDPOINT_ID
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=65535)),
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )
