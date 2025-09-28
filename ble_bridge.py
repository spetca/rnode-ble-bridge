#!/usr/bin/env python3

"""
Standalone BLE-to-Serial Bridge for RNode Devices

This utility creates virtual serial ports for BLE RNode devices,
allowing any application (like MeshChat) to connect to them as
regular serial ports.

Usage:
    python ble_bridge.py                    # Interactive mode
    python ble_bridge.py --scan             # Scan and list devices
    python ble_bridge.py --connect ADDRESS  # Connect to specific device
    python ble_bridge.py --auto             # Auto-connect to all devices
"""

import asyncio
import argparse
import logging
import signal
import sys
import os
from typing import Dict, List

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

try:
    from bluetooth.ble_manager import BLEManager
    from bluetooth.ble_discovery import BLEDiscovery
    from bluetooth.ble_pairing import pairing_manager
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure 'bleak' is installed: pip install bleak")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class BLEBridgeApp:
    """Standalone BLE Bridge Application"""

    def __init__(self):
        self.manager = BLEManager()
        self.discovery = BLEDiscovery()
        self.running = False
        self.connected_devices: Dict[str, dict] = {}

    async def scan_devices(self, timeout: float = 10.0) -> List[dict]:
        """Scan for RNode BLE devices"""
        print(f"\n🔍 Scanning for RNode devices ({timeout}s)...")

        devices = await self.discovery.scan_for_rnodes(timeout)

        if devices:
            print(f"\n✅ Found {len(devices)} RNode device(s):")
            for i, device in enumerate(devices, 1):
                print(f"  {i}. {device.name} ({device.address})")
                if device.rssi:
                    print(f"     RSSI: {device.rssi} dBm")
        else:
            print("\n❌ No RNode devices found")
            print("Make sure your RNode is:")
            print("  - Powered on and in BLE mode")
            print("  - Advertising Nordic UART Service")
            print("  - Not connected to another device")

        return [self._device_to_dict(device) for device in devices]

    def _device_to_dict(self, device) -> dict:
        """Convert RNodeDevice to dictionary"""
        return {
            'name': device.name,
            'address': device.address,
            'rssi': device.rssi,
            'is_connected': device.is_connected
        }

    async def connect_device(self, address: str, pin: str = None) -> bool:
        """Connect to a specific device"""
        print(f"\n🔗 Connecting to {address}...")

        # Store PIN if provided
        if pin:
            pairing_manager.store_pin_for_device(address, pin)
            print(f"   Using PIN: {pin}")

        try:
            success = await self.manager.connect_device(address)

            if success:
                # Get connection info
                connected = self.manager.get_connected_devices()
                device_info = next((d for d in connected if d['address'] == address), None)

                if device_info:
                    self.connected_devices[address] = device_info
                    print(f"✅ Connected successfully!")
                    print(f"   Serial Port: {device_info['serial_port']}")
                    print(f"   Symlink: {device_info['symlink']}")
                    print(f"\n📝 You can now use this port in MeshChat:")
                    print(f"   {device_info['symlink']}")
                else:
                    print("❌ Connection succeeded but device info not available")
                    success = False
            else:
                print("❌ Connection failed")

            return success

        except Exception as e:
            error_msg = str(e)
            if any(keyword in error_msg.lower() for keyword in ["not paired", "authentication", "bonding"]):
                print("❌ Connection failed - device not paired")
                await self._handle_pairing_needed(address)
            else:
                print(f"❌ Connection failed: {e}")
            return False

    async def _handle_pairing_needed(self, address: str):
        """Handle when device needs pairing"""
        print(f"\n🔐 Device {address} needs to be paired first")

        # Get pairing instructions
        instructions = pairing_manager.get_pairing_instructions(address)

        print(f"\n📋 {instructions['platform']} Pairing Instructions:")
        for i, instruction in enumerate(instructions['instructions'], 1):
            print(f"  {i}. {instruction}")

        if instructions.get('notes'):
            print(f"\n💡 Note: {instructions['notes']}")

        # Ask for PIN
        while True:
            try:
                pin = input("\n🔑 Enter PIN (or 'skip' to continue without pairing): ").strip()
                if pin.lower() in ['skip', 'q', 'quit']:
                    break

                if pin:
                    print(f"   Attempting to pair with PIN: {pin}")
                    success = await pairing_manager.pair_with_pin(address, pin)
                    if success:
                        print("✅ Pairing successful!")
                        return await self.connect_device(address, pin)
                    else:
                        print("❌ Pairing failed, try again")
                else:
                    print("❌ Please enter a PIN")
            except KeyboardInterrupt:
                print("\n\n⏹️  Pairing cancelled")
                break

    async def auto_connect_all(self) -> int:
        """Auto-connect to all discovered devices"""
        print("\n🚀 Auto-connecting to all discovered devices...")

        devices = await self.scan_devices(5.0)
        if not devices:
            return 0

        connected_count = 0
        for device in devices:
            if not device['is_connected']:
                success = await self.connect_device(device['address'])
                if success:
                    connected_count += 1

        return connected_count

    async def interactive_mode(self):
        """Interactive device selection and connection"""
        print("\n🎛️  Interactive Mode")
        print("Commands: scan, connect, list, quit")

        while True:
            try:
                command = input("\nble-bridge> ").strip().lower()

                if command in ['q', 'quit', 'exit']:
                    break
                elif command == 'scan':
                    await self.scan_devices()
                elif command == 'list':
                    await self.list_connected_devices()
                elif command.startswith('connect'):
                    parts = command.split()
                    if len(parts) >= 2:
                        address = parts[1]
                        pin = parts[2] if len(parts) > 2 else None
                        await self.connect_device(address, pin)
                    else:
                        await self.interactive_connect()
                elif command == 'help':
                    self.print_help()
                else:
                    print("Unknown command. Type 'help' for available commands.")

            except KeyboardInterrupt:
                print("\n")
                break
            except EOFError:
                print("\n")
                break

    async def interactive_connect(self):
        """Interactive device connection"""
        devices = await self.scan_devices(5.0)
        if not devices:
            return

        print("\n📱 Select device to connect:")
        for i, device in enumerate(devices, 1):
            status = "✅ Connected" if device['is_connected'] else "❌ Disconnected"
            print(f"  {i}. {device['name']} ({device['address']}) - {status}")

        try:
            choice = input("\nSelect device number (or 'cancel'): ").strip()
            if choice.lower() in ['cancel', 'c', 'q']:
                return

            device_idx = int(choice) - 1
            if 0 <= device_idx < len(devices):
                device = devices[device_idx]
                if not device['is_connected']:
                    pin = input("Enter PIN (optional): ").strip() or None
                    await self.connect_device(device['address'], pin)
                else:
                    print("Device is already connected")
            else:
                print("Invalid selection")

        except (ValueError, KeyboardInterrupt):
            print("Selection cancelled")

    async def list_connected_devices(self):
        """List currently connected devices"""
        connected = self.manager.get_connected_devices()

        if connected:
            print(f"\n🔗 Connected Devices ({len(connected)}):")
            for device in connected:
                print(f"  • {device['device']} ({device['address']})")
                print(f"    Serial Port: {device['serial_port']}")
                print(f"    Symlink: {device['symlink']}")
                print()
        else:
            print("\n❌ No devices currently connected")

    def print_help(self):
        """Print help information"""
        print("\n📖 Available Commands:")
        print("  scan                    - Scan for RNode devices")
        print("  connect                 - Interactive device connection")
        print("  connect ADDRESS [PIN]   - Connect to specific device")
        print("  list                    - List connected devices")
        print("  help                    - Show this help")
        print("  quit                    - Exit the bridge")

    async def start_bridge(self):
        """Start the BLE bridge service"""
        print("🚀 Starting BLE-to-Serial Bridge...")

        success = await self.manager.start()
        if not success:
            print("❌ Failed to start BLE manager")
            return False

        self.running = True
        print("✅ BLE Bridge is running")
        return True

    async def stop_bridge(self):
        """Stop the BLE bridge service"""
        if self.running:
            print("\n⏹️  Stopping BLE Bridge...")
            await self.manager.stop()
            self.running = False
            print("✅ BLE Bridge stopped")

    async def run_forever(self):
        """Run the bridge until interrupted"""
        if not await self.start_bridge():
            return

        print("\n🔄 Bridge is running. Press Ctrl+C to stop.")
        print("💡 Connected devices will remain available as virtual serial ports.")

        try:
            while self.running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n")
        finally:
            await self.stop_bridge()

async def main():
    """Main application entry point"""
    parser = argparse.ArgumentParser(
        description="Standalone BLE-to-Serial Bridge for RNode Devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python ble_bridge.py                           # Interactive mode
  python ble_bridge.py --scan                    # Scan and list devices
  python ble_bridge.py --connect 12:34:56:78     # Connect to specific device
  python ble_bridge.py --auto                    # Auto-connect all devices
  python ble_bridge.py --daemon                  # Run as background service
        """
    )

    parser.add_argument('--scan', action='store_true',
                        help='Scan for devices and exit')
    parser.add_argument('--connect', metavar='ADDRESS',
                        help='Connect to specific device address')
    parser.add_argument('--pin', metavar='PIN',
                        help='PIN for pairing (use with --connect)')
    parser.add_argument('--auto', action='store_true',
                        help='Auto-connect to all discovered devices')
    parser.add_argument('--daemon', action='store_true',
                        help='Run as background service')
    parser.add_argument('--timeout', type=float, default=10.0,
                        help='Scan timeout in seconds (default: 10)')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    app = BLEBridgeApp()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n⏹️  Shutting down...")
        asyncio.create_task(app.stop_bridge())

    signal.signal(signal.SIGINT, signal_handler)

    try:
        if args.scan:
            # Scan mode
            await app.start_bridge()
            devices = await app.scan_devices(args.timeout)
            await app.stop_bridge()

        elif args.connect:
            # Connect mode
            await app.start_bridge()
            success = await app.connect_device(args.connect, args.pin)
            if success and not args.daemon:
                await app.run_forever()
            elif not success:
                await app.stop_bridge()
                sys.exit(1)

        elif args.auto:
            # Auto-connect mode
            await app.start_bridge()
            count = await app.auto_connect_all()
            print(f"\n✅ Connected to {count} device(s)")
            if count > 0:
                await app.run_forever()
            else:
                await app.stop_bridge()

        elif args.daemon:
            # Daemon mode - just run the service
            await app.start_bridge()
            await app.run_forever()

        else:
            # Interactive mode
            await app.start_bridge()
            await app.interactive_mode()
            await app.stop_bridge()

    except KeyboardInterrupt:
        print("\n\n⏹️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("🌉 RNode BLE-to-Serial Bridge")
    print("=" * 40)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"💥 Fatal error: {e}")
        sys.exit(1)