#!/bin/bash

# Simple RNode BLE Connection Script
# This script helps you connect to RNode devices via BLE

set -e

echo "🌉 RNode BLE Connection Helper"
echo "================================"

# Check if bleak is installed
if ! python3 -c "import bleak" 2>/dev/null; then
    echo "❌ Missing dependency: bleak"
    echo "Installing bleak..."
    pip3 install bleak>=0.21.1
fi

# Change to script directory
cd "$(dirname "$0")"

# Function to show usage
show_usage() {
    echo ""
    echo "Usage:"
    echo "  $0                    # Interactive mode"
    echo "  $0 scan              # Scan for devices"
    echo "  $0 auto              # Auto-connect all devices"
    echo "  $0 connect ADDRESS   # Connect to specific device"
    echo ""
    echo "Examples:"
    echo "  $0 scan"
    echo "  $0 connect 12:34:56:78:9A:BC"
    echo "  $0 auto"
    echo ""
}

# Check arguments
case "${1:-interactive}" in
    "help"|"-h"|"--help")
        show_usage
        exit 0
        ;;
    "scan")
        echo "🔍 Scanning for RNode devices..."
        python3 ble_bridge.py --scan
        ;;
    "auto")
        echo "🚀 Auto-connecting to all RNode devices..."
        python3 ble_bridge.py --auto
        echo ""
        echo "💡 Tip: Connected devices are now available as virtual serial ports"
        echo "   You can use them in MeshChat by selecting the /tmp/cu.RNode-* ports"
        ;;
    "connect")
        if [ -z "$2" ]; then
            echo "❌ Error: Please specify device address"
            echo "Usage: $0 connect ADDRESS"
            exit 1
        fi
        echo "🔗 Connecting to $2..."
        python3 ble_bridge.py --connect "$2"
        ;;
    "interactive"|"")
        echo "🎛️  Starting interactive mode..."
        python3 ble_bridge.py
        ;;
    *)
        echo "❌ Unknown command: $1"
        show_usage
        exit 1
        ;;
esac