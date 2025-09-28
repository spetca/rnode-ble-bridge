# RNode BLE Bridge

This utility creates virtual serial ports for BLE RNode devices, allowing any application (like MeshChat) to connect to them as regular serial ports. It eliminates the need for complex GUI integration by providing a simple command-line interface.


```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐    ┌─────────────┐
│   MeshChat  │◄──►│ Virtual PTY  │◄──►│ BLE Bridge  │◄──►│ RNode (BLE) │
│             │    │ /tmp/cu.RNode│    │             │    │ Heltec v3   │
└─────────────┘    └──────────────┘    └─────────────┘    └─────────────┘
```

The gist: 

1. Finds RNode devices advertising Nordic UART Service
2. Creates `/tmp/cu.RNode-*` symlinks for easy access in services like MeshChat

## Disclaimer

Pairing is buggy and may require trying to run `./connect_rnode.sh auto` twice

## Quick Start

### Installation

```bash
pip install -r requirements.txt
```

### Usage

```bash
# Auto-connect to all RNode devices
./connect_rnode.sh auto

# Scan for devices
./connect_rnode.sh scan

# Connect to specific device
./connect_rnode.sh connect 12:34:56:78:9A:BC

# Interactive mode
./connect_rnode.sh
```

### Example Usage with MeshChat

1. Clone this repo
2. put device (like heltec v3) into pairing mode by holding user button for ~5 seconds and releasing
3. run `./connect_rnode.sh auto` from the location of this repo on your machine
4. during first pairing you may get errors like below

```
 ./connect_rnode.sh auto

🌉 RNode BLE Connection Helper
================================
🚀 Auto-connecting to all RNode devices...
🌉 RNode BLE-to-Serial Bridge
========================================
🚀 Starting BLE-to-Serial Bridge...
2025-09-27 20:05:26,178 - INFO - Starting BLE-to-Serial bridge service
2025-09-27 20:05:26,178 - INFO - BLE-to-Serial bridge service started
2025-09-27 20:05:26,178 - INFO - BLE Manager started
✅ BLE Bridge is running

🚀 Auto-connecting to all discovered devices...

🔍 Scanning for RNode devices (5.0s)...
2025-09-27 20:05:26,178 - INFO - Scanning for RNode devices (timeout: 5.0s)
2025-09-27 20:05:26,251 - INFO - Discovery worker started (interval: 30.0s)
2025-09-27 20:05:26,251 - INFO - Scanning for RNode devices (timeout: 5.0s)
2025-09-27 20:05:26,637 - INFO - Discovered RNode: RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:26,637 - INFO - Discovered RNode: RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:26,637 - INFO - RNode device discovered: RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:26,637 - INFO - Device discovered: RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:31,253 - INFO - Found 1 RNode device(s)

✅ Found 1 RNode device(s):
  1. RNode A1D0 (83505A21-5088-FDEC-FCB7-E282E48AC0AF)

🔗 Connecting to 83505A21-5088-FDEC-FCB7-E282E48AC0AF...
2025-09-27 20:05:31,253 - INFO - Creating bridge for RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:31,254 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state: connecting
2025-09-27 20:05:31,254 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state changed to connecting
2025-09-27 20:05:31,258 - INFO - Created symlink: /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF -> /dev/ttys054
2025-09-27 20:05:31,258 - INFO - Virtual serial port created: /dev/ttys054
2025-09-27 20:05:31,258 - INFO - Connecting to RNode RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:31,300 - INFO - Found 1 RNode device(s)
2025-09-27 20:05:32,858 - INFO - Pairing status for RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF): paired
2025-09-27 20:05:32,916 - INFO - Characteristics setup complete for RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:32,916 - INFO - Successfully connected to RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:32,916 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state: connected
2025-09-27 20:05:32,916 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state changed to connected
2025-09-27 20:05:32,916 - INFO - Bridge connected: RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF) -> /dev/ttys054
✅ Connected successfully!
   Serial Port: /dev/ttys054
   Symlink: /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF

📝 You can now use this port in MeshChat:
   /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF

✅ Connected to 1 device(s)
🚀 Starting BLE-to-Serial Bridge...
✅ BLE Bridge is running

🔄 Bridge is running. Press Ctrl+C to stop.
💡 Connected devices will remain available as virtual serial ports.
2025-09-27 20:05:40,393 - WARNING - Unexpected disconnection from RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:40,394 - WARNING - BLE disconnected for RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:40,394 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state: error
2025-09-27 20:05:40,394 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state changed to error
^C

⏹️  Shutting down...

⏹️  Stopping BLE Bridge...
2025-09-27 20:05:44,926 - INFO - Stopping BLE-to-Serial bridge service
2025-09-27 20:05:44,927 - INFO - Disconnecting all bridges
2025-09-27 20:05:44,927 - INFO - Disconnecting bridge for RNode(RNode A1D0 - 83505A21-5088-FDEC-FCB7-E282E48AC0AF)
2025-09-27 20:05:44,927 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state: disconnected
2025-09-27 20:05:44,927 - INFO - Bridge 83505A21-5088-FDEC-FCB7-E282E48AC0AF state changed to disconnected
2025-09-27 20:05:44,927 - INFO - Closing virtual serial port: /dev/ttys054
2025-09-27 20:05:44,976 - INFO - BLE-to-Serial bridge service stopped
2025-09-27 20:05:44,976 - INFO - BLE Manager stopped
✅ BLE Bridge stopped

💡 Tip: Connected devices are now available as virtual serial ports
   You can use them in MeshChat by selecting the /tmp/cu.RNode-* ports
```
4. restart with `./connect_rnode.sh auto` and note output
```
✅ Connected successfully!
   Serial Port: /dev/ttys054
   Symlink: /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF
```
5. put the above in your ~/.reticulum/config file
   <img width="451" height="218" alt="image" src="https://github.com/user-attachments/assets/8a3cb0ea-950f-444e-ba4a-d9237af5a049" />
6. open meshcat


