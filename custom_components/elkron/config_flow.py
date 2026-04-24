from homeassistant import config_entries
from homeassistant.components.alarm_control_panel import PLATFORM_SCHEMA
from homeassistant.data_entry_flow import FlowResult
from typing import Any

import logging
import voluptuous as vol
from homeassistant.data_entry_flow import section

from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME, CONF_HOST
from .const import DOMAIN, DEFAULT_NAME
from homeassistant.components.alarm_control_panel import AlarmControlPanelState

_LOGGER = logging.getLogger(__name__)


class ElkronConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Elkron config flow."""

    # The schema version of the entries that it creates
    # Home Assistant will call your migrate method if the version changes
    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle a flow initialized by the user."""
        _LOGGER.info("async_step_user: %s", user_input)
        data_schema = {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_HOST): str,
            vol.Required(str(AlarmControlPanelState.ARMED_AWAY), default="1,2,3,4,5"): str,
            vol.Required(str(AlarmControlPanelState.ARMED_HOME), default="1"): str,
        }

        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=vol.Schema(data_schema)
            )
        return await self.async_step_progress()

    async def async_step_progress(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Displaying rogress for two tasks"""
        _LOGGER.info("async_step_progress")
        _LOGGER.info("async_step_progress - all tasks done")
        return self.async_show_progress_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        _LOGGER.info("async_step_finish")
        return self.async_create_entry(
            title=user_input.get(CONF_NAME, DEFAULT_NAME),
            data=user_input,
        )
