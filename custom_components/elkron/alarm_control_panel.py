"""Interfaces with Elkron alarm control panels."""

import logging
import re

from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME, CONF_HOST
from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelState,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from pylkron.elkron_client import ElkronClient
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    CONF_ZONES,
)

_LOGGER = logging.getLogger(__name__)

from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from typing import Any, Mapping
from propcache.api import cached_property
import homeassistant.helpers.config_validation as cv


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a Elkron control panel."""
    config = config_entry.data
    name = config.get(CONF_NAME)
    host = config.get(CONF_HOST)
    username = config.get(CONF_USERNAME)
    password = config.get(CONF_PASSWORD)

    away_zones = [
        int(x)
        for x in cv.ensure_list_csv(config.get(AlarmControlPanelState.ARMED_AWAY, ""))
    ]
    home_zones = [
        int(x)
        for x in cv.ensure_list_csv(config.get(AlarmControlPanelState.ARMED_HOME, ""))
    ]
    states = [
        {"name": AlarmControlPanelState.ARMED_AWAY, "zones": away_zones},
        {"name": AlarmControlPanelState.ARMED_HOME, "zones": home_zones},
    ]

    elkronalarm = ElkronAlarm(hass, name, username, password, host, states)
    async_add_entities([elkronalarm], update_before_add=True)


class ElkronState:
    def __init__(self, name: AlarmControlPanelState, zones):
        self._name: AlarmControlPanelState = name
        self._zones = zones
        self._zones.sort()

    @property
    def name(self) -> AlarmControlPanelState:
        return self._name

    @property
    def zones(self):
        return self._zones


class ElkronAlarm(AlarmControlPanelEntity):
    """Representation of an Elkron status."""

    def __init__(self, hass, name, username, password, host, states):
        """Initialize the Elkron status."""
        _LOGGER.debug("Setting up ElkronClient...")
        self._hass = hass
        self._name = name
        self._username = username
        self._password = password
        self._hostname = host
        self._state = None

        # Setup States
        self._states = []
        for custom_state in states:
            name = custom_state.get(CONF_NAME)
            zones = custom_state.get(CONF_ZONES)
            if name is None or zones is None:
                _LOGGER.warning(
                    "Invalid state configuration, missing name or zones: "
                    + str(custom_state)
                )
                continue
            new_state = ElkronState(name, zones)
            self._states.append(new_state)

            if name == AlarmControlPanelState.ARMED_HOME:
                self._armed_home_state = new_state

            if name == AlarmControlPanelState.ARMED_AWAY:
                self._armed_away_state = new_state

        self._alarm: ElkronClient = ElkronClient(username, password, host)

    async def async_update(self):
        """Fetch the latest state."""
        _LOGGER.debug("Updating Elkron alarm state...")
        await self._hass.async_add_executor_job(self._alarm.doLogin)
        _LOGGER.debug("Logged in to Elkron alarm")
        sysState = await self._hass.async_add_executor_job(
            self._alarm.getDetailedStates
        )
        _LOGGER.debug("Fetched alarm state: " + str(sysState))
        sysInfo = await self._hass.async_add_executor_job(self._alarm.getSysInfo)
        _LOGGER.debug("Fetched alarm info: " + str(sysInfo))

        plantStructure = await self._hass.async_add_executor_job(
            self._alarm.getPlantStructure
        )
        _LOGGER.debug("Fetched alarm structure: " + str(plantStructure))
        zones = plantStructure["cfgzone"]
        structure = []
        for zone in zones:
            structure.append({"name": zone["NAME"], "zoneId": zone["NID"]})

        self._state = {"state": sysState, "info": sysInfo, "structure": structure}
        _LOGGER.debug("Updated alarm state: " + str(self._state))
        _LOGGER.debug("Elkron alarm state update complete")
        self._attr_alarm_state = self._calculate_alarm_state(self._state)

    @property
    def name(self):
        """Return the name of the alarm."""
        return self._name

    @property
    def code_format(self) -> CodeFormat | None:
        """Return one or more digits/characters."""
        return CodeFormat.NUMBER

    def _calculate_alarm_state(self, remote_state) -> AlarmControlPanelState | None:
        """Calculate the alarm state."""
        if (
            remote_state is None
            or "state" not in remote_state
            or remote_state["state"] is None
            or "activezone" not in remote_state["state"]
        ):
            return None
        active_zones = remote_state["state"]["activezone"]
        active_zones.sort()

        for state in self._states:
            if state.zones == active_zones:
                return state.name

        if active_zones.__len__() == 0:
            return AlarmControlPanelState.DISARMED

        if active_zones.__len__() > 0:
            return AlarmControlPanelState.ARMED_CUSTOM_BYPASS

        return None

    @cached_property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        return self._state

    async def async_alarm_disarm(self, code=None):
        """Send disarm command."""
        if (
            self._state == None
            or "state" not in self._state
            or self._state["state"] == None
            or "activezone" not in self._state["state"]
        ):
            _LOGGER.warning("Alarm not connected")
            return None

        try:
            await self._hass.async_add_executor_job(
                self._alarm.doDeactivate, code, self._state["state"]["activezone"]
            )
        except Exception as e:
            _LOGGER.warning("Failed to disarm alarm: " + str(e))

        self.schedule_update_ha_state()

    async def async_alarm_arm_home(self, code=None):
        """Send arm hom command."""
        if (
            self._state == None
            or "state" not in self._state
            or self._state["state"] == None
            or "activezone" not in self._state["state"]
        ):
            _LOGGER.warning("Alarm not connected")
            return None

        if self._armed_home_state == None:
            _LOGGER.error(
                "No home state ( "
                + AlarmControlPanelState.ARMED_HOME
                + " ) declared for this alarm"
            )

        try:
            await self._hass.async_add_executor_job(
                self._alarm.doActivate, code, self._armed_home_state.zones
            )
        except Exception as e:
            _LOGGER.warning("Failed to arm alarm: " + str(e))

        self.schedule_update_ha_state()

    async def async_alarm_arm_away(self, code=None):
        """Send arm away command."""
        if (
            self._state == None
            or "state" not in self._state
            or self._state["state"] == None
            or "activezone" not in self._state["state"]
        ):
            _LOGGER.warning("Alarm not connected")
            return None

        if self._armed_away_state == None:
            _LOGGER.error(
                "No away state ( "
                + AlarmControlPanelState.ARMED_AWAY
                + " ) declared for this alarm"
            )

        try:
            await self._hass.async_add_executor_job(
                self._alarm.doActivate, code, self._armed_away_state.zones
            )
        except Exception as e:
            _LOGGER.warning("Failed to arm alarm: " + str(e))

        self.schedule_update_ha_state()

    @cached_property
    def supported_features(self) -> AlarmControlPanelEntityFeature:
        """Return the list of supported features."""
        return AlarmControlPanelEntityFeature.ARM_HOME | AlarmControlPanelEntityFeature.ARM_AWAY
