# RNode BLE Bridge

This utility creates virtual serial ports for BLE RNode devices, allowing any application (like MeshChat) to connect to them as regular serial ports. It eliminates the need for complex GUI integration by providing a simple command-line interface.

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

