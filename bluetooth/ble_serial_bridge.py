#!/usr/bin/env python3

import asyncio
import logging
import threading
from typing import Dict, List, Optional, Callable
from enum import Enum
import time

from .ble_discovery import BLEDiscovery, RNodeDevice
from .ble_gatt_client import BLEGATTClient
from .virtual_serial import VirtualSerialPort

logger = logging.getLogger(__name__)

class BridgeState(Enum):
    """Bridge connection states"""
    DISCONNECTED = "disconnected"
    DISCOVERING = "discovering"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class BLESerialBridge:
    """
    Main bridge class that connects BLE RNode devices to virtual serial ports.
    Each RNode gets its own virtual serial port that MeshChat can connect to.
    """

    def __init__(self):
        self.discovery = BLEDiscovery()
        self.bridges: Dict[str, 'RNodeBridge'] = {}  # address -> RNodeBridge
        self.is_running = False

        # Callbacks
        self.device_discovered_callback: Optional[Callable[[RNodeDevice], None]] = None
        self.bridge_state_callback: Optional[Callable[[str, BridgeState], None]] = None

        # Background tasks
        self._discovery_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None

    def set_device_discovered_callback(self, callback: Callable[[RNodeDevice], None]):
        """Set callback for when new RNode devices are discovered"""
        self.device_discovered_callback = callback

    def set_bridge_state_callback(self, callback: Callable[[str, BridgeState], None]):
        """Set callback for bridge state changes"""
        self.bridge_state_callback = callback

    async def start(self, auto_discover: bool = True, discovery_interval: float = 30.0):
        """Start the BLE-to-Serial bridge service"""
        if self.is_running:
            logger.warning("Bridge service already running")
            return

        logger.info("Starting BLE-to-Serial bridge service")
        self.is_running = True

        # Set up discovery callback
        self.discovery.add_discovery_callback(self._on_device_discovered)

        if auto_discover:
            # Start periodic discovery
            self._discovery_task = asyncio.create_task(
                self._discovery_worker(discovery_interval)
            )

        # Start monitor task
        self._monitor_task = asyncio.create_task(self._monitor_worker())

        logger.info("BLE-to-Serial bridge service started")

    async def stop(self):
        """Stop the BLE-to-Serial bridge service"""
        if not self.is_running:
            return

        logger.info("Stopping BLE-to-Serial bridge service")
        self.is_running = False

        # Stop discovery
        if self._discovery_task:
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        # Stop monitor
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        # Disconnect all bridges
        await self._disconnect_all_bridges()

        logger.info("BLE-to-Serial bridge service stopped")

    async def scan_for_devices(self, timeout: float = 10.0) -> List[RNodeDevice]:
        """Manually scan for RNode devices"""
        logger.info("Manual scan for RNode devices")
        return await self.discovery.scan_for_rnodes(timeout)

    async def connect_device(self, device_address: str) -> bool:
        """Connect to a specific RNode device"""
        device = self.discovery.get_device_by_address(device_address)
        if not device:
            logger.error(f"Device {device_address} not found in discovery cache")
            return False

        return await self._create_bridge(device)

    async def disconnect_device(self, device_address: str):
        """Disconnect from a specific RNode device"""
        if device_address in self.bridges:
            await self.bridges[device_address].disconnect()
            del self.bridges[device_address]

    def get_connected_devices(self) -> List[Dict]:
        """Get list of connected devices and their virtual serial ports"""
        devices = []
        for bridge in self.bridges.values():
            if bridge.state == BridgeState.CONNECTED:
                devices.append({
                    'device': str(bridge.rnode),
                    'address': bridge.rnode.address,
                    'serial_port': bridge.virtual_serial.get_device_path(),
                    'symlink': bridge.virtual_serial.get_symlink_path(),
                    'state': bridge.state.value
                })
        return devices

    def get_bridge_info(self) -> Dict:
        """Get comprehensive bridge information"""
        info = {
            'is_running': self.is_running,
            'discovered_devices': len(self.discovery.get_discovered_devices()),
            'connected_bridges': len([b for b in self.bridges.values() if b.state == BridgeState.CONNECTED]),
            'total_bridges': len(self.bridges),
            'bridges': {}
        }

        for addr, bridge in self.bridges.items():
            info['bridges'][addr] = bridge.get_info()

        return info

    async def _discovery_worker(self, interval: float):
        """Background task for periodic device discovery"""
        logger.info(f"Discovery worker started (interval: {interval}s)")

        while self.is_running:
            try:
                logger.debug("Running periodic RNode discovery scan")
                devices = await self.discovery.scan_for_rnodes(timeout=5.0)

                # Auto-connect to new devices (optional behavior)
                # for device in devices:
                #     if device.address not in self.bridges:
                #         await self._create_bridge(device)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Discovery worker error: {e}")
                await asyncio.sleep(5.0)

        logger.info("Discovery worker stopped")

    async def _monitor_worker(self):
        """Background task for monitoring bridge health"""
        logger.debug("Monitor worker started")

        while self.is_running:
            try:
                # Check bridge states and attempt reconnections
                for addr, bridge in list(self.bridges.items()):
                    if bridge.state == BridgeState.ERROR:
                        logger.info(f"Attempting to reconnect bridge {addr}")
                        await bridge.reconnect()

                await asyncio.sleep(10.0)  # Monitor every 10 seconds

            except Exception as e:
                logger.error(f"Monitor worker error: {e}")
                await asyncio.sleep(5.0)

        logger.debug("Monitor worker stopped")

    def _on_device_discovered(self, device: RNodeDevice):
        """Handle discovery of new RNode device"""
        logger.info(f"RNode device discovered: {device}")

        # Notify callback
        if self.device_discovered_callback:
            self.device_discovered_callback(device)

    async def _create_bridge(self, device: RNodeDevice) -> bool:
        """Create a bridge for an RNode device"""
        if device.address in self.bridges:
            logger.warning(f"Bridge already exists for {device}")
            return self.bridges[device.address].state == BridgeState.CONNECTED

        logger.info(f"Creating bridge for {device}")

        try:
            bridge = RNodeBridge(device, self._on_bridge_state_change)
            self.bridges[device.address] = bridge

            success = await bridge.connect()
            return success

        except Exception as e:
            logger.error(f"Failed to create bridge for {device}: {e}")
            if device.address in self.bridges:
                del self.bridges[device.address]
            return False

    def _on_bridge_state_change(self, bridge: 'RNodeBridge', new_state: BridgeState):
        """Handle bridge state changes"""
        logger.info(f"Bridge {bridge.rnode.address} state: {new_state.value}")

        # Notify callback
        if self.bridge_state_callback:
            self.bridge_state_callback(bridge.rnode.address, new_state)

    async def _disconnect_all_bridges(self):
        """Disconnect all active bridges"""
        logger.info("Disconnecting all bridges")

        tasks = []
        for bridge in self.bridges.values():
            tasks.append(bridge.disconnect())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.bridges.clear()

class RNodeBridge:
    """Individual bridge for one RNode device"""

    def __init__(self, rnode: RNodeDevice, state_callback: Callable[['RNodeBridge', BridgeState], None]):
        self.rnode = rnode
        self.state = BridgeState.DISCONNECTED
        self.state_callback = state_callback

        # Components
        self.ble_client = BLEGATTClient(rnode)
        self.virtual_serial = VirtualSerialPort(f"RNode-{rnode.address.replace(':', '')}")

        # Setup callbacks
        self.ble_client.set_data_callback(self._on_ble_data_received)
        self.ble_client.set_connection_callbacks(
            established=self._on_ble_connected,
            lost=self._on_ble_disconnected
        )

        self.virtual_serial.set_data_callback(self._on_serial_data_received)
        self.virtual_serial.set_connection_callback(self._on_serial_connection_change)

        # Connection tracking
        self.last_connection_attempt = 0
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5

    async def connect(self) -> bool:
        """Connect the bridge (both BLE and virtual serial)"""
        self._set_state(BridgeState.CONNECTING)

        try:
            # Create virtual serial port first
            if not self.virtual_serial.open():
                raise Exception("Failed to create virtual serial port")

            # Connect to BLE device
            if not await self.ble_client.connect():
                raise Exception("Failed to connect to BLE device")

            self._set_state(BridgeState.CONNECTED)
            self.reconnect_attempts = 0
            logger.info(f"Bridge connected: {self.rnode} -> {self.virtual_serial.get_device_path()}")
            return True

        except Exception as e:
            logger.error(f"Bridge connection failed for {self.rnode}: {e}")
            self._set_state(BridgeState.ERROR)
            await self._cleanup()
            return False

    async def disconnect(self):
        """Disconnect the bridge"""
        logger.info(f"Disconnecting bridge for {self.rnode}")
        self._set_state(BridgeState.DISCONNECTED)
        await self._cleanup()

    async def reconnect(self) -> bool:
        """Attempt to reconnect the bridge"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.warning(f"Max reconnect attempts reached for {self.rnode}")
            return False

        if time.time() - self.last_connection_attempt < 10:
            logger.debug(f"Skipping reconnect for {self.rnode} (too soon)")
            return False

        self.last_connection_attempt = time.time()
        self.reconnect_attempts += 1

        logger.info(f"Reconnecting bridge for {self.rnode} (attempt {self.reconnect_attempts})")
        await self.disconnect()
        return await self.connect()

    def _on_ble_data_received(self, data: bytes):
        """Handle data received from BLE device"""
        # Forward to virtual serial port
        self.virtual_serial.send_data(data)

    def _on_serial_data_received(self, data: bytes):
        """Handle data received from virtual serial port"""
        # Forward to BLE device
        self.ble_client.send_data(data)

    def _on_ble_connected(self):
        """Handle BLE connection established"""
        logger.debug(f"BLE connected for {self.rnode}")

    def _on_ble_disconnected(self):
        """Handle BLE connection lost"""
        logger.warning(f"BLE disconnected for {self.rnode}")
        self._set_state(BridgeState.ERROR)

    def _on_serial_connection_change(self, connected: bool):
        """Handle virtual serial connection changes"""
        logger.debug(f"Virtual serial {'connected' if connected else 'disconnected'} for {self.rnode}")

    def _set_state(self, new_state: BridgeState):
        """Update bridge state and notify callback"""
        if self.state != new_state:
            self.state = new_state
            self.state_callback(self, new_state)

    async def _cleanup(self):
        """Clean up bridge resources"""
        await self.ble_client.disconnect()
        self.virtual_serial.close()

    def get_info(self) -> Dict:
        """Get bridge information"""
        return {
            'device': str(self.rnode),
            'address': self.rnode.address,
            'state': self.state.value,
            'reconnect_attempts': self.reconnect_attempts,
            'virtual_serial': self.virtual_serial.get_info(),
            'ble_client': self.ble_client.get_connection_info()
        }