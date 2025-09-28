#!/usr/bin/env python3

import asyncio
import logging
from typing import Optional, Callable, Dict
import platform

try:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.exc import BleakError
except ImportError:
    raise ImportError("bleak library required: pip install bleak")

logger = logging.getLogger(__name__)

class BLEPairingManager:
    """Manages BLE pairing and authentication for RNode devices"""

    def __init__(self):
        self.pairing_callbacks: Dict[str, Callable] = {}
        self.pairing_state: Dict[str, str] = {}  # address -> state
        self.stored_pins: Dict[str, str] = {}    # address -> pin

    def set_pairing_callback(self, device_address: str, callback: Callable[[str, str], None]):
        """Set callback for pairing events (device_address, event_type, data)"""
        self.pairing_callbacks[device_address] = callback

    def store_pin_for_device(self, device_address: str, pin: str):
        """Store PIN for a device (for automatic pairing)"""
        self.stored_pins[device_address] = pin
        logger.info(f"Stored PIN for device {device_address}")

    def get_stored_pin(self, device_address: str) -> Optional[str]:
        """Get stored PIN for a device"""
        return self.stored_pins.get(device_address)

    def clear_stored_pin(self, device_address: str):
        """Clear stored PIN for a device"""
        if device_address in self.stored_pins:
            del self.stored_pins[device_address]

    async def pair_with_pin(self, device_address: str, pin: str) -> bool:
        """Attempt to pair with device using provided PIN"""
        try:
            self.pairing_state[device_address] = "pairing"

            # Store PIN for this device
            self.store_pin_for_device(device_address, pin)

            # Platform-specific pairing
            if platform.system() == "Darwin":  # macOS
                success = await self._pair_macos(device_address, pin)
            elif platform.system() == "Linux":
                success = await self._pair_linux(device_address, pin)
            else:
                logger.warning(f"Pairing not implemented for {platform.system()}")
                success = False

            if success:
                self.pairing_state[device_address] = "paired"
                logger.info(f"Successfully paired with {device_address}")
            else:
                self.pairing_state[device_address] = "failed"
                logger.error(f"Failed to pair with {device_address}")

            return success

        except Exception as e:
            logger.error(f"Pairing error for {device_address}: {e}")
            self.pairing_state[device_address] = "error"
            return False

    async def _pair_macos(self, device_address: str, pin: str) -> bool:
        """Handle pairing on macOS"""
        # On macOS, pairing usually happens through System Preferences
        # We can guide the user or attempt to trigger pairing
        logger.info(f"macOS pairing for {device_address} with PIN {pin}")

        # Attempt connection which may trigger pairing dialog
        try:
            from bleak import BleakClient
            async with BleakClient(device_address) as client:
                # Connection attempt may trigger pairing
                await client.connect()
                return client.is_connected
        except Exception as e:
            logger.info(f"Connection attempt triggered pairing dialog: {e}")
            # This is expected - user needs to enter PIN in system dialog
            return False

    async def _pair_linux(self, device_address: str, pin: str) -> bool:
        """Handle pairing on Linux using bluetoothctl"""
        try:
            import subprocess

            # Use bluetoothctl for pairing
            commands = [
                f"bluetoothctl pair {device_address}",
                f"bluetoothctl trust {device_address}"
            ]

            for cmd in commands:
                logger.info(f"Running: {cmd}")
                result = subprocess.run(
                    cmd.split(),
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    logger.warning(f"Command failed: {result.stderr}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Linux pairing error: {e}")
            return False

    def get_pairing_instructions(self, device_address: str) -> Dict[str, str]:
        """Get platform-specific pairing instructions"""
        system = platform.system()

        if system == "Darwin":  # macOS
            return {
                "platform": "macOS",
                "title": "Pair RNode Device",
                "instructions": [
                    "1. Open System Preferences → Bluetooth",
                    "2. Make sure your RNode is in pairing mode",
                    "3. Click 'Connect' when the RNode appears",
                    "4. Enter the PIN when prompted",
                    "5. Return to MeshChat and try connecting again"
                ],
                "notes": "The PIN is usually displayed on the RNode or is a default like '123456'"
            }
        elif system == "Linux":
            return {
                "platform": "Linux",
                "title": "Pair RNode Device",
                "instructions": [
                    "1. Open a terminal",
                    "2. Run: bluetoothctl",
                    "3. Run: scan on",
                    "4. Run: pair " + device_address,
                    "5. Enter PIN when prompted",
                    "6. Run: trust " + device_address,
                    "7. Return to MeshChat and try connecting"
                ],
                "notes": "You can also use your desktop's Bluetooth manager"
            }
        else:
            return {
                "platform": system,
                "title": "Manual Pairing Required",
                "instructions": [
                    "1. Use your system's Bluetooth settings",
                    "2. Pair with the RNode device",
                    "3. Enter the PIN when prompted",
                    "4. Return to MeshChat and try connecting"
                ],
                "notes": "Automatic pairing not implemented for this platform"
            }

    async def check_pairing_status(self, device_address: str) -> str:
        """Check if device is already paired"""
        try:
            # Try a quick connection test
            from bleak import BleakClient
            client = BleakClient(device_address)

            try:
                await asyncio.wait_for(client.connect(), timeout=5.0)
                if client.is_connected:
                    await client.disconnect()
                    return "paired"
                else:
                    return "unpaired"
            except asyncio.TimeoutError:
                return "unpaired"
            except Exception as e:
                if "not paired" in str(e).lower() or "authentication" in str(e).lower():
                    return "unpaired"
                else:
                    return "unknown"

        except Exception as e:
            logger.debug(f"Pairing status check error: {e}")
            return "unknown"

    def notify_pairing_event(self, device_address: str, event_type: str, data: str = ""):
        """Notify about pairing events"""
        callback = self.pairing_callbacks.get(device_address)
        if callback:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Pairing callback error: {e}")

class BLEAuthHandler:
    """Handles BLE authentication callbacks during connection"""

    def __init__(self, pairing_manager: BLEPairingManager, device_address: str):
        self.pairing_manager = pairing_manager
        self.device_address = device_address
        self.pending_pin = None

    def on_passkey_request(self) -> int:
        """Handle passkey request from device"""
        logger.info(f"Passkey requested for {self.device_address}")

        # Try to get stored PIN
        stored_pin = self.pairing_manager.get_stored_pin(self.device_address)
        if stored_pin:
            try:
                return int(stored_pin)
            except ValueError:
                logger.warning(f"Invalid stored PIN format: {stored_pin}")

        # Default PIN (common for RNode devices)
        default_pins = ["123456", "000000", "111111", "654321"]
        for pin in default_pins:
            logger.info(f"Trying default PIN: {pin}")
            return int(pin)

        # If no PIN available, return 0 (will likely fail)
        logger.warning(f"No PIN available for {self.device_address}")
        return 0

    def on_passkey_notify(self, passkey: int):
        """Handle passkey notification (device shows PIN to user)"""
        logger.info(f"Device {self.device_address} is showing PIN: {passkey:06d}")
        self.pairing_manager.notify_pairing_event(
            self.device_address,
            "pin_display",
            f"{passkey:06d}"
        )

    def on_confirm_pin(self, pin: int) -> bool:
        """Handle PIN confirmation request"""
        logger.info(f"Confirm PIN {pin:06d} for {self.device_address}")

        # Check if we have a stored PIN that matches
        stored_pin = self.pairing_manager.get_stored_pin(self.device_address)
        if stored_pin:
            try:
                return int(stored_pin) == pin
            except ValueError:
                pass

        # For now, auto-confirm (user will need to verify manually)
        logger.info(f"Auto-confirming PIN {pin:06d} for {self.device_address}")
        self.pairing_manager.notify_pairing_event(
            self.device_address,
            "pin_confirm",
            f"{pin:06d}"
        )
        return True

    def on_security_request(self) -> bool:
        """Handle security request"""
        logger.info(f"Security request for {self.device_address}")
        return True  # Accept security requests

    def on_authentication_complete(self, success: bool):
        """Handle authentication completion"""
        if success:
            logger.info(f"Authentication successful for {self.device_address}")
            self.pairing_manager.notify_pairing_event(
                self.device_address,
                "auth_success",
                "Authentication completed successfully"
            )
        else:
            logger.warning(f"Authentication failed for {self.device_address}")
            self.pairing_manager.notify_pairing_event(
                self.device_address,
                "auth_failed",
                "Authentication failed - check PIN"
            )

# Global pairing manager instance
pairing_manager = BLEPairingManager()