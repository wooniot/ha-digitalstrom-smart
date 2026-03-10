"""Binary sensor entities for Digital Strom.

Exposes device on/off state as binary sensors for Joker (black) devices.
PRO FEATURE - requires license key.
"""

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, GROUP_JOKER, CONF_ENABLED_ZONES
from .coordinator import DigitalStromCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Digital Strom binary sensors for Joker devices."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: DigitalStromCoordinator = data["coordinator"]
    enabled_zones = entry.data.get(CONF_ENABLED_ZONES, [])

    entities = []
    for dsuid, dev in coordinator.devices.items():
        zone_id = dev.get("zone_id")
        if enabled_zones and zone_id not in enabled_zones:
            continue
        # Joker (black) devices with binary input capability
        if GROUP_JOKER in dev.get("groups", []) and dev.get("sensors"):
            entities.append(
                DigitalStromBinarySensor(coordinator, dsuid, dev)
            )

    async_add_entities(entities)


class DigitalStromBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """A Digital Strom binary sensor (Joker device state)."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(
        self,
        coordinator: DigitalStromCoordinator,
        dsuid: str,
        dev_info: dict,
    ) -> None:
        super().__init__(coordinator)
        self._dsuid = dsuid
        dss_id = coordinator.dss_id
        zone_name = dev_info.get("zone_name", "")
        dev_name = dev_info.get("name", dsuid[:8])
        self._attr_unique_id = f"ds_{dss_id}_dev_{dsuid}_binary"
        self._attr_name = dev_name or f"Sensor {dsuid[:8]}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{dss_id}_zone_{dev_info.get('zone_id', 0)}")},
            "name": zone_name,
            "manufacturer": MANUFACTURER,
            "model": "Zone",
        }

    @property
    def available(self) -> bool:
        return not self.coordinator.is_paused and super().available

    @property
    def is_on(self) -> bool | None:
        dev = self.coordinator.devices.get(self._dsuid)
        if dev:
            return dev.get("is_on", False)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
