#!/usr/bin/env python3

import asyncio
import logging
from typing import Dict, List, Optional
import json

from .ble_serial_bridge import BLESerialBridge, BridgeState
from .ble_discovery import RNodeDevice

logger = logging.getLogger(__name__)

class BLEManager:
    """
    High-level manager for BLE RNode connections.
    Provides simple API for MeshChat integration.
    """

    def __init__(self):
        self.bridge = BLESerialBridge()
        self.is_started = False

        # Event callbacks for web API
        self.event_callbacks = []

    def add_event_callback(self, callback):
        """Add callback for bridge events"""
        self.event_callbacks.append(callback)

    def remove_event_callback(self, callback):
        """Remove event callback"""
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)

    async def start(self) -> bool:
        """Start the BLE manager"""
        if self.is_started:
            return True

        try:
            # Set up callbacks
            self.bridge.set_device_discovered_callback(self._on_device_discovered)
            self.bridge.set_bridge_state_callback(self._on_bridge_state_change)

            # Start bridge service
            await self.bridge.start(auto_discover=True, discovery_interval=30.0)

            self.is_started = True
            logger.info("BLE Manager started")

            # Notify events
            self._emit_event('manager_started', {})

            return True

        except Exception as e:
            logger.error(f"Failed to start BLE Manager: {e}")
            return False

    async def stop(self):
        """Stop the BLE manager"""
        if not self.is_started:
            return

        try:
            await self.bridge.stop()
            self.is_started = False
            logger.info("BLE Manager stopped")

            # Notify events
            self._emit_event('manager_stopped', {})

        except Exception as e:
            logger.error(f"Error stopping BLE Manager: {e}")

    async def scan_devices(self, timeout: float = 10.0) -> List[Dict]:
        """Scan for available RNode devices"""
        try:
            devices = await self.bridge.scan_for_devices(timeout)
            return [self._device_to_dict(device) for device in devices]

        except Exception as e:
            logger.error(f"Error scanning for devices: {e}")
            return []

    async def connect_device(self, address: str) -> Dict:
        """Connect to a specific RNode device"""
        try:
            success = await self.bridge.connect_device(address)
            return {
                'success': success,
                'address': address,
                'message': 'Connected successfully' if success else 'Connection failed'
            }

        except Exception as e:
            logger.error(f"Error connecting to device {address}: {e}")
            return {
                'success': False,
                'address': address,
                'message': f'Connection error: {e}'
            }

    async def disconnect_device(self, address: str) -> Dict:
        """Disconnect from a specific RNode device"""
        try:
            await self.bridge.disconnect_device(address)
            return {
                'success': True,
                'address': address,
                'message': 'Disconnected successfully'
            }

        except Exception as e:
            logger.error(f"Error disconnecting device {address}: {e}")
            return {
                'success': False,
                'address': address,
                'message': f'Disconnect error: {e}'
            }

    def get_connected_devices(self) -> List[Dict]:
        """Get list of connected devices"""
        return self.bridge.get_connected_devices()

    def get_discovered_devices(self) -> List[Dict]:
        """Get list of discovered (but not necessarily connected) devices"""
        devices = self.bridge.discovery.get_discovered_devices()
        return [self._device_to_dict(device) for device in devices]

    def get_status(self) -> Dict:
        """Get overall BLE manager status"""
        bridge_info = self.bridge.get_bridge_info()

        return {
            'is_started': self.is_started,
            'is_running': bridge_info['is_running'],
            'discovered_devices': bridge_info['discovered_devices'],
            'connected_bridges': bridge_info['connected_bridges'],
            'total_bridges': bridge_info['total_bridges'],
            'connected_devices': self.get_connected_devices()
        }

    def get_virtual_serial_ports(self) -> List[Dict]:
        """Get list of virtual serial ports for connected devices"""
        ports = []
        for device in self.get_connected_devices():
            ports.append({
                'device_name': device['device'],
                'device_address': device['address'],
                'serial_port': device['serial_port'],
                'symlink': device['symlink'],
                'description': f"RNode BLE Bridge ({device['address']})"
            })
        return ports

    def _device_to_dict(self, device: RNodeDevice) -> Dict:
        """Convert RNodeDevice to dictionary"""
        return {
            'name': device.name,
            'address': device.address,
            'rssi': device.rssi,
            'is_connected': device.is_connected
        }

    def _on_device_discovered(self, device: RNodeDevice):
        """Handle device discovery"""
        logger.info(f"Device discovered: {device}")

        self._emit_event('device_discovered', {
            'device': self._device_to_dict(device)
        })

    def _on_bridge_state_change(self, address: str, state: BridgeState):
        """Handle bridge state changes"""
        logger.info(f"Bridge {address} state changed to {state.value}")

        self._emit_event('bridge_state_changed', {
            'address': address,
            'state': state.value
        })

        # If connected, emit virtual serial port info
        if state == BridgeState.CONNECTED:
            connected_devices = self.get_connected_devices()
            device_info = next((d for d in connected_devices if d['address'] == address), None)
            if device_info:
                self._emit_event('virtual_serial_created', {
                    'address': address,
                    'serial_port': device_info['serial_port'],
                    'symlink': device_info['symlink']
                })

    def _emit_event(self, event_type: str, data: Dict):
        """Emit event to all registered callbacks"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': asyncio.get_event_loop().time()
        }

        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")

# Global instance for easy access
ble_manager = BLEManager()