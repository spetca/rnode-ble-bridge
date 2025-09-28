# BLE-to-Serial Bridge for RNode Devices

This module provides a Bluetooth Low Energy (BLE) to Serial bridge that allows MeshChat to connect to RNode devices that only support BLE (like the Heltec v3).

## Overview

The bridge works by:

1. **Discovering** RNode devices advertising BLE Nordic UART Service
2. **Connecting** to RNode BLE GATT services with MITM encryption
3. **Creating** virtual serial ports (e.g., `/tmp/cu.RNode-XXXX`)
4. **Bridging** data between BLE GATT characteristics and virtual serial ports
5. **Presenting** RNode devices as standard serial ports to MeshChat

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│   MeshChat  │◄──►│ Virtual PTY  │◄──►│ BLE Bridge  │◄──►│ RNode (BLE) │
│             │    │ /tmp/cu.RNode│    │             │    │ Heltec v3   │
└─────────────┘    └──────────────┘    └─────────────┘    └─────────────┘
```

### Core Components

- **`ble_discovery.py`**: Scans for and identifies RNode BLE devices
- **`ble_gatt_client.py`**: Manages BLE GATT connections with Nordic UART Service
- **`virtual_serial.py`**: Creates virtual serial ports using PTY pairs
- **`ble_serial_bridge.py`**: Orchestrates the bridge connections
- **`ble_manager.py`**: High-level API for MeshChat integration

## Installation

### Prerequisites

1. **Python 3.8+** with asyncio support
2. **bleak** library for BLE communication
3. **Unix-like OS** with PTY support (Linux, macOS)

### Install Dependencies

```bash
pip install bleak>=0.21.1
```

Or using the project requirements:

```bash
pip install -r requirements.txt
```

## Usage

### Automatic Integration

The BLE bridge is automatically integrated into MeshChat. When you scan for serial ports, connected BLE RNode devices will appear as:

- Device path: `/tmp/cu.RNode-XXXXXXXXXXXX`
- Product: `RNode BLE Bridge (XX:XX:XX:XX:XX:XX)`

### Manual Testing

Test the bridge functionality:

```bash
# Test all components
python test_ble_bridge.py all

# Test only discovery
python test_ble_bridge.py discovery

# Test only virtual serial ports
python test_ble_bridge.py serial

# Test manager functionality
python test_ble_bridge.py manager
```

### API Endpoints

MeshChat provides REST API endpoints for BLE management:

#### Get BLE Status
```bash
GET /api/v1/ble/status
```

#### Start BLE Manager
```bash
POST /api/v1/ble/start
```

#### Scan for Devices
```bash
POST /api/v1/ble/scan
Content-Type: application/json

{
    "timeout": 10.0
}
```

#### Connect to Device
```bash
POST /api/v1/ble/connect
Content-Type: application/json

{
    "address": "XX:XX:XX:XX:XX:XX"
}
```

#### Get Connected Devices
```bash
GET /api/v1/ble/devices
```

## RNode BLE Requirements

### Firmware Requirements

The RNode firmware must implement:

1. **Nordic UART Service** (`6e400001-b5a3-f393-e0a9-e50e24dcca9e`)
2. **RX Characteristic** (`6e400002-b5a3-f393-e0a9-e50e24dcca9e`) - Write
3. **TX Characteristic** (`6e400003-b5a3-f393-e0a9-e50e24dcca9e`) - Notify

### Security Requirements

The bridge expects RNode devices to implement:

- **MITM-resistant pairing** (`ESP_BLE_SEC_ENCRYPT_MITM`)
- **Encrypted characteristics** (`ESP_GATT_PERM_WRITE_ENC_MITM`, `ESP_GATT_PERM_READ_ENC_MITM`)
- **Authentication callbacks** (passkey, PIN confirmation)

### Compatible Devices

- **Heltec LoRa32 v3** with RNode firmware
- **ESP32** devices with BLE Nordic UART Service
- Any BLE device implementing the Nordic UART Service pattern

## Platform Support

### macOS

- ✅ **BLE Discovery**: Works without special permissions
- ✅ **GATT Connection**: Standard Core Bluetooth support
- ✅ **Virtual Serial**: PTY pairs work natively
- ⚠️ **Pairing**: May require manual pairing in System Preferences

### Linux

- ✅ **BLE Discovery**: Works with BlueZ
- ✅ **GATT Connection**: Standard BlueZ support
- ✅ **Virtual Serial**: PTY pairs work natively
- ✅ **Pairing**: Handled automatically by bleak/BlueZ

### Windows

- ⚠️ **Limited Support**: BLE works, but PTY creation is complex
- 🔄 **Alternative**: Consider named pipes or COM port emulation

## Troubleshooting

### Common Issues

1. **"BLE support not available"**
   - Install bleak: `pip install bleak`
   - Check Python version (3.8+ required)

2. **"No devices found"**
   - Ensure RNode is in BLE mode and advertising
   - Check RNode firmware supports Nordic UART Service
   - Verify RNode is not connected to another device

3. **"Connection failed"**
   - Pair the RNode device manually first
   - Check MITM encryption requirements
   - Ensure Nordic UART Service is available

4. **"Virtual serial port creation failed"**
   - Check PTY support on your system
   - Verify permissions for `/tmp` directory
   - Try running as different user

### Debug Logging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Manual Pairing

If automatic pairing fails, manually pair the device:

**macOS:**
1. Open System Preferences → Bluetooth
2. Put RNode in pairing mode
3. Click "Connect" when device appears
4. Enter PIN/passkey when prompted

**Linux:**
```bash
bluetoothctl
scan on
pair XX:XX:XX:XX:XX:XX
trust XX:XX:XX:XX:XX:XX
```

## Development

### Adding New Features

1. **Extend Discovery**: Modify `ble_discovery.py` for new device patterns
2. **Custom Security**: Add authentication methods in `ble_gatt_client.py`
3. **Alternative Serial**: Implement different virtual port types in `virtual_serial.py`

### Testing

Run the test suite:

```bash
python test_ble_bridge.py all
```

### Contributing

1. Follow existing code patterns
2. Add comprehensive error handling
3. Include logging for debugging
4. Test on multiple platforms
5. Update documentation

## Security Considerations

### BLE Security

- Bridge enforces MITM-resistant pairing
- All communication uses encrypted GATT characteristics
- Passkey/PIN verification required for initial pairing

### Local Security

- Virtual serial ports created in `/tmp` (world-readable)
- Consider using more restrictive permissions for sensitive deployments
- Monitor for unauthorized access to virtual serial devices

### Network Security

- BLE bridge only provides transport layer
- All Reticulum encryption/authentication happens at protocol level
- RNode firmware handles crypto operations

## License

This BLE bridge module inherits the same license as the main MeshChat project.

## Support

For issues specific to BLE functionality:

1. Check this documentation
2. Run test suite for diagnostics
3. Enable debug logging
4. Check RNode firmware compatibility
5. Report issues with full debug logs