#!/usr/bin/env python3

import asyncio
import logging
from typing import Optional, Callable, Any
import threading
from queue import Queue, Empty

try:
    from bleak import BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
    from bleak.exc import BleakError
except ImportError:
    raise ImportError("bleak library required: pip install bleak")

from .ble_discovery import RNodeDevice
from .ble_pairing import pairing_manager, BLEAuthHandler

logger = logging.getLogger(__name__)

class BLEGATTClient:
    """BLE GATT client for communicating with RNode devices"""

    # Nordic UART Service UUIDs
    NORDIC_UART_SERVICE_UUID = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
    NORDIC_UART_RX_UUID = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # Write to RNode
    NORDIC_UART_TX_UUID = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # Read from RNode

    def __init__(self, rnode: RNodeDevice):
        self.rnode = rnode
        self.client: Optional[BleakClient] = None
        self.is_connected = False
        self.is_connecting = False

        # Data handling
        self.rx_queue = Queue()  # Data received from RNode
        self.tx_queue = Queue()  # Data to send to RNode
        self.data_callback: Optional[Callable[[bytes], None]] = None

        # Characteristics
        self.tx_characteristic: Optional[BleakGATTCharacteristic] = None
        self.rx_characteristic: Optional[BleakGATTCharacteristic] = None

        # Connection monitoring
        self.connection_lost_callback: Optional[Callable[[], None]] = None
        self.connection_established_callback: Optional[Callable[[], None]] = None
        self.pairing_callback: Optional[Callable[[str, str], None]] = None

        # Authentication
        self.auth_handler = BLEAuthHandler(pairing_manager, rnode.address)

        # Background tasks
        self._tx_task: Optional[asyncio.Task] = None
        self._connection_monitor_task: Optional[asyncio.Task] = None

    def set_data_callback(self, callback: Callable[[bytes], None]):
        """Set callback for received data"""
        self.data_callback = callback

    def set_connection_callbacks(self,
                               established: Optional[Callable[[], None]] = None,
                               lost: Optional[Callable[[], None]] = None,
                               pairing: Optional[Callable[[str, str], None]] = None):
        """Set connection state callbacks"""
        self.connection_established_callback = established
        self.connection_lost_callback = lost
        self.pairing_callback = pairing
        if pairing:
            pairing_manager.set_pairing_callback(self.rnode.address, pairing)

    async def connect(self, timeout: float = 30.0) -> bool:
        """Connect to the RNode device"""
        if self.is_connected or self.is_connecting:
            logger.warning(f"Already connected/connecting to {self.rnode}")
            return self.is_connected

        logger.info(f"Connecting to RNode {self.rnode}")
        self.is_connecting = True

        try:
            # Check pairing status first
            pairing_status = await pairing_manager.check_pairing_status(self.rnode.address)
            logger.info(f"Pairing status for {self.rnode}: {pairing_status}")

            # Create client
            self.client = BleakClient(
                self.rnode.device,
                disconnected_callback=self._on_disconnect
            )

            # Attempt connection
            try:
                await asyncio.wait_for(self.client.connect(), timeout=timeout)
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ["not paired", "authentication", "bonding", "security"]):
                    logger.warning(f"Connection failed due to pairing/authentication: {e}")
                    if self.pairing_callback:
                        self.pairing_callback("pairing_required", str(e))
                    raise BleakError(f"Device not paired or authentication failed: {e}")
                else:
                    raise

            if not self.client.is_connected:
                raise BleakError("Failed to establish connection")

            # Discover and setup characteristics
            await self._setup_characteristics()

            # Start background tasks
            await self._start_background_tasks()

            self.is_connected = True
            self.rnode.is_connected = True

            logger.info(f"Successfully connected to {self.rnode}")

            # Notify connection established
            if self.connection_established_callback:
                self.connection_established_callback()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.rnode}: {e}")
            await self._cleanup_connection()
            return False
        finally:
            self.is_connecting = False

    async def disconnect(self):
        """Disconnect from the RNode device"""
        if not self.is_connected:
            return

        logger.info(f"Disconnecting from {self.rnode}")

        await self._cleanup_connection()

        if self.client and self.client.is_connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")

    async def _setup_characteristics(self):
        """Setup Nordic UART service characteristics"""
        if not self.client:
            raise BleakError("No client available")

        # Get Nordic UART service
        service = self.client.services.get_service(self.NORDIC_UART_SERVICE_UUID)
        if not service:
            raise BleakError("Nordic UART service not found")

        # Find characteristics
        self.rx_characteristic = None
        self.tx_characteristic = None

        for char in service.characteristics:
            if char.uuid.lower() == self.NORDIC_UART_RX_UUID.lower():
                self.rx_characteristic = char
            elif char.uuid.lower() == self.NORDIC_UART_TX_UUID.lower():
                self.tx_characteristic = char

        if not self.rx_characteristic:
            raise BleakError("RX characteristic not found")

        if not self.tx_characteristic:
            raise BleakError("TX characteristic not found")

        # Enable notifications on TX characteristic (data from RNode)
        await self.client.start_notify(self.tx_characteristic, self._on_data_received)

        logger.info(f"Characteristics setup complete for {self.rnode}")

    async def _start_background_tasks(self):
        """Start background tasks for data transmission and connection monitoring"""
        # Start TX task for sending queued data
        self._tx_task = asyncio.create_task(self._tx_worker())

        # Start connection monitor
        self._connection_monitor_task = asyncio.create_task(self._connection_monitor())

    async def _tx_worker(self):
        """Background task to send queued data to RNode"""
        logger.debug(f"TX worker started for {self.rnode}")

        while self.is_connected:
            try:
                # Get data from queue (non-blocking)
                try:
                    data = self.tx_queue.get_nowait()
                except Empty:
                    await asyncio.sleep(0.01)  # Small delay to prevent busy loop
                    continue

                # Send data to RNode
                if self.client and self.rx_characteristic:
                    try:
                        # Split large data into chunks if needed (BLE has MTU limits)
                        max_chunk_size = 20  # Conservative MTU size

                        for i in range(0, len(data), max_chunk_size):
                            chunk = data[i:i + max_chunk_size]
                            await self.client.write_gatt_char(self.rx_characteristic, chunk)
                            await asyncio.sleep(0.01)  # Small delay between chunks

                        logger.debug(f"Sent {len(data)} bytes to {self.rnode}")

                    except Exception as e:
                        logger.error(f"Error sending data to {self.rnode}: {e}")
                        # Re-queue the data for retry
                        self.tx_queue.put(data)
                        await asyncio.sleep(0.1)

                self.tx_queue.task_done()

            except Exception as e:
                logger.error(f"TX worker error for {self.rnode}: {e}")
                await asyncio.sleep(0.1)

        logger.debug(f"TX worker stopped for {self.rnode}")

    async def _connection_monitor(self):
        """Monitor connection health"""
        logger.debug(f"Connection monitor started for {self.rnode}")

        while self.is_connected:
            try:
                if not self.client or not self.client.is_connected:
                    logger.warning(f"Connection lost to {self.rnode}")
                    await self._handle_connection_lost()
                    break

                await asyncio.sleep(1)  # Check every second

            except Exception as e:
                logger.error(f"Connection monitor error for {self.rnode}: {e}")
                await asyncio.sleep(1)

        logger.debug(f"Connection monitor stopped for {self.rnode}")

    def _on_data_received(self, sender: BleakGATTCharacteristic, data: bytearray):
        """Callback for data received from RNode"""
        try:
            data_bytes = bytes(data)
            logger.debug(f"Received {len(data_bytes)} bytes from {self.rnode}")

            # Add to receive queue
            self.rx_queue.put(data_bytes)

            # Call data callback if set
            if self.data_callback:
                self.data_callback(data_bytes)

        except Exception as e:
            logger.error(f"Error processing received data from {self.rnode}: {e}")

    def _on_disconnect(self, client: BleakClient):
        """Callback for unexpected disconnection"""
        logger.warning(f"Unexpected disconnection from {self.rnode}")
        asyncio.create_task(self._handle_connection_lost())

    async def _handle_connection_lost(self):
        """Handle connection loss"""
        self.is_connected = False
        self.rnode.is_connected = False

        await self._cleanup_connection()

        # Notify connection lost
        if self.connection_lost_callback:
            self.connection_lost_callback()

    async def _cleanup_connection(self):
        """Clean up connection resources"""
        self.is_connected = False
        self.rnode.is_connected = False

        # Cancel background tasks
        if self._tx_task:
            self._tx_task.cancel()
            try:
                await self._tx_task
            except asyncio.CancelledError:
                pass

        if self._connection_monitor_task:
            self._connection_monitor_task.cancel()
            try:
                await self._connection_monitor_task
            except asyncio.CancelledError:
                pass

        # Stop notifications
        if self.client and self.tx_characteristic:
            try:
                await self.client.stop_notify(self.tx_characteristic)
            except Exception as e:
                logger.debug(f"Error stopping notifications: {e}")

        # Clear characteristics
        self.tx_characteristic = None
        self.rx_characteristic = None

    def send_data(self, data: bytes) -> bool:
        """Queue data to send to RNode"""
        if not self.is_connected:
            logger.warning(f"Cannot send data - not connected to {self.rnode}")
            return False

        try:
            self.tx_queue.put(data)
            logger.debug(f"Queued {len(data)} bytes for {self.rnode}")
            return True
        except Exception as e:
            logger.error(f"Error queuing data for {self.rnode}: {e}")
            return False

    def receive_data(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get received data from queue"""
        try:
            return self.rx_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_connection_info(self) -> dict:
        """Get connection information"""
        info = {
            'device': str(self.rnode),
            'connected': self.is_connected,
            'connecting': self.is_connecting,
            'tx_queue_size': self.tx_queue.qsize(),
            'rx_queue_size': self.rx_queue.qsize()
        }

        if self.client:
            info['mtu'] = getattr(self.client, 'mtu_size', 'unknown')

        return info