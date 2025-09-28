#!/usr/bin/env python3

import asyncio
import logging
from typing import List, Dict, Optional, Callable
import platform

try:
    from bleak import BleakScanner, BleakClient, BLEDevice
    from bleak.backends.service import BleakGATTService
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError:
    raise ImportError("bleak library required: pip install bleak")

logger = logging.getLogger(__name__)

class RNodeDevice:
    """Represents a discovered RNode BLE device"""

    def __init__(self, device: BLEDevice, name: str = None):
        self.device = device
        self.name = name or device.name or "Unknown RNode"
        self.address = device.address
        self.rssi = getattr(device, 'rssi', None)
        self.is_connected = False

    def __str__(self):
        return f"RNode({self.name} - {self.address})"

    def __repr__(self):
        return self.__str__()

class BLEDiscovery:
    """Discovers RNode devices using BLE scanning"""

    # Nordic UART Service UUID (used by RNode BLE implementation)
    NORDIC_UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    NORDIC_UART_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write to RNode
    NORDIC_UART_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Read from RNode

    def __init__(self):
        self.discovered_devices: Dict[str, RNodeDevice] = {}
        self.scan_callbacks: List[Callable[[RNodeDevice], None]] = []
        self.is_scanning = False

    def add_discovery_callback(self, callback: Callable[[RNodeDevice], None]):
        """Add callback for when new RNode devices are discovered"""
        self.scan_callbacks.append(callback)

    def remove_discovery_callback(self, callback: Callable[[RNodeDevice], None]):
        """Remove discovery callback"""
        if callback in self.scan_callbacks:
            self.scan_callbacks.remove(callback)

    async def scan_for_rnodes(self, timeout: float = 10.0) -> List[RNodeDevice]:
        """Scan for RNode devices advertising Nordic UART service"""
        logger.info(f"Scanning for RNode devices (timeout: {timeout}s)")

        self.is_scanning = True
        self.discovered_devices.clear()

        try:
            def detection_callback(device: BLEDevice, advertisement_data):
                """Called when a BLE device is discovered during scanning"""
                if self._is_rnode_device(device, advertisement_data):
                    self._handle_rnode_discovery(device, advertisement_data)

            # Start scanning
            scanner = BleakScanner(detection_callback=detection_callback)
            await scanner.start()

            # Wait for timeout
            await asyncio.sleep(timeout)

            # Stop scanning
            await scanner.stop()

        except Exception as e:
            logger.error(f"Error during BLE scan: {e}")
        finally:
            self.is_scanning = False

        devices = list(self.discovered_devices.values())
        logger.info(f"Found {len(devices)} RNode device(s)")
        return devices

    def _is_rnode_device(self, device: BLEDevice, advertisement_data) -> bool:
        """Check if discovered device is likely an RNode"""

        # Check for Nordic UART service in advertised services
        if hasattr(advertisement_data, 'service_uuids'):
            for uuid in advertisement_data.service_uuids:
                if uuid.lower() == self.NORDIC_UART_SERVICE_UUID.lower():
                    return True

        # Check device name patterns
        if device.name:
            name_lower = device.name.lower()
            if any(pattern in name_lower for pattern in ['rnode', 'reticulum', 'lora']):
                return True

        # For devices without clear identifiers, we'll need to connect and check services
        # This is more invasive but might be necessary for some RNode implementations
        return False

    def _handle_rnode_discovery(self, device: BLEDevice, advertisement_data):
        """Process discovered RNode device"""
        if device.address not in self.discovered_devices:
            rnode = RNodeDevice(device)
            self.discovered_devices[device.address] = rnode

            logger.info(f"Discovered RNode: {rnode}")

            # Notify callbacks
            for callback in self.scan_callbacks:
                try:
                    callback(rnode)
                except Exception as e:
                    logger.error(f"Error in discovery callback: {e}")

    async def get_device_info(self, rnode: RNodeDevice) -> Dict:
        """Get detailed information about an RNode device"""
        info = {
            'name': rnode.name,
            'address': rnode.address,
            'rssi': rnode.rssi,
            'services': [],
            'characteristics': {}
        }

        try:
            async with BleakClient(rnode.device) as client:
                logger.info(f"Connected to {rnode} for info gathering")

                # Get services
                for service in client.services:
                    service_info = {
                        'uuid': service.uuid,
                        'description': service.description
                    }
                    info['services'].append(service_info)

                    # Get characteristics for Nordic UART service
                    if service.uuid.lower() == self.NORDIC_UART_SERVICE_UUID.lower():
                        info['characteristics']['nordic_uart'] = []
                        for char in service.characteristics:
                            char_info = {
                                'uuid': char.uuid,
                                'properties': char.properties,
                                'description': char.description
                            }
                            info['characteristics']['nordic_uart'].append(char_info)

        except Exception as e:
            logger.error(f"Error getting device info for {rnode}: {e}")
            info['error'] = str(e)

        return info

    async def verify_rnode_compatibility(self, rnode: RNodeDevice) -> bool:
        """Verify that device supports required Nordic UART characteristics"""
        try:
            async with BleakClient(rnode.device) as client:
                logger.info(f"Verifying compatibility for {rnode}")

                # Look for Nordic UART service
                service = client.services.get_service(self.NORDIC_UART_SERVICE_UUID)
                if not service:
                    logger.warning(f"No Nordic UART service found on {rnode}")
                    return False

                # Check for required characteristics
                rx_char = None
                tx_char = None

                for char in service.characteristics:
                    if char.uuid.lower() == self.NORDIC_UART_RX_UUID.lower():
                        rx_char = char
                    elif char.uuid.lower() == self.NORDIC_UART_TX_UUID.lower():
                        tx_char = char

                if not rx_char:
                    logger.warning(f"No RX characteristic found on {rnode}")
                    return False

                if not tx_char:
                    logger.warning(f"No TX characteristic found on {rnode}")
                    return False

                # Check properties
                if "write" not in rx_char.properties and "write-without-response" not in rx_char.properties:
                    logger.warning(f"RX characteristic on {rnode} doesn't support write")
                    return False

                if "notify" not in tx_char.properties and "read" not in tx_char.properties:
                    logger.warning(f"TX characteristic on {rnode} doesn't support notify/read")
                    return False

                logger.info(f"RNode {rnode} is compatible")
                return True

        except Exception as e:
            logger.error(f"Error verifying compatibility for {rnode}: {e}")
            return False

    def get_discovered_devices(self) -> List[RNodeDevice]:
        """Get list of currently discovered devices"""
        return list(self.discovered_devices.values())

    def get_device_by_address(self, address: str) -> Optional[RNodeDevice]:
        """Get device by Bluetooth address"""
        return self.discovered_devices.get(address)