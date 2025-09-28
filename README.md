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

1. Clone this repo, create a python virtual environment, and install requirements
2. put device (like heltec v3) into pairing mode by holding user button for ~5 seconds and releasing
3. run `./connect_rnode.sh auto` from the location of this repo on your machin, when prompted put in the pairing key displayed on your rnode 
4. during first pairing you may get errors like below

```
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

5. restart with `./connect_rnode.sh auto` and note output
```
✅ Connected successfully!
   Serial Port: /dev/ttys054
   Symlink: /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF
```
6. put the symlink port into your ~/.reticulum/config file (the serial port may change from boot-to-boot)
   
```
 [[rnode000]]
    type = RNodeInterface
    interface_enabled = true
    #port = /dev/cu.usbserial-0001
    port = /tmp/cu.RNode-83505A21-5088-FDEC-FCB7-E282E48AC0AF
    frequency = 915000000
    bandwidth = 250000
    txpower = 22
    spreadingfactor = 5
    codingrate = 5
    airtime_limit_long = 10
    name = spet-midcity
    selected_interface_mode = 1
    configured_bitrate = None
```

7. open meshcat


