#!/usr/bin/env python3

import asyncio
import logging
import os
import platform
import tempfile
import threading
from typing import Optional, Callable
from queue import Queue, Empty
import pty
import select
import termios

logger = logging.getLogger(__name__)

class VirtualSerialPort:
    """Creates a virtual serial port that appears as /dev/pts/X (Linux/macOS)"""

    def __init__(self, device_name: str = "RNode"):
        self.device_name = device_name
        self.is_open = False

        # PTY file descriptors
        self.master_fd: Optional[int] = None
        self.slave_fd: Optional[int] = None
        self.slave_path: Optional[str] = None

        # Data queues
        self.rx_queue = Queue()  # Data to send to client (from BLE)
        self.tx_queue = Queue()  # Data received from client (to BLE)

        # Callbacks
        self.data_callback: Optional[Callable[[bytes], None]] = None
        self.connection_callback: Optional[Callable[[bool], None]] = None

        # Background threads
        self._read_thread: Optional[threading.Thread] = None
        self._write_thread: Optional[threading.Thread] = None
        self._running = False

    def set_data_callback(self, callback: Callable[[bytes], None]):
        """Set callback for data received from serial client"""
        self.data_callback = callback

    def set_connection_callback(self, callback: Callable[[bool], None]):
        """Set callback for connection state changes"""
        self.connection_callback = callback

    def open(self) -> bool:
        """Create and open the virtual serial port"""
        if self.is_open:
            logger.warning("Virtual serial port already open")
            return True

        try:
            # Create PTY pair
            self.master_fd, self.slave_fd = pty.openpty()

            # Get slave device path
            self.slave_path = os.ttyname(self.slave_fd)

            # Configure terminal settings
            self._configure_terminal()

            # Create symlink for easier access (optional)
            self._create_symlink()

            self.is_open = True
            self._running = True

            # Start background threads
            self._start_threads()

            logger.info(f"Virtual serial port created: {self.slave_path}")

            # Notify connection established
            if self.connection_callback:
                self.connection_callback(True)

            return True

        except Exception as e:
            logger.error(f"Failed to create virtual serial port: {e}")
            self._cleanup()
            return False

    def close(self):
        """Close the virtual serial port"""
        if not self.is_open:
            return

        logger.info(f"Closing virtual serial port: {self.slave_path}")

        self._running = False
        self.is_open = False

        # Stop threads
        self._stop_threads()

        # Close file descriptors
        self._cleanup()

        # Notify disconnection
        if self.connection_callback:
            self.connection_callback(False)

    def _configure_terminal(self):
        """Configure terminal settings for the PTY"""
        if not self.slave_fd:
            return

        try:
            # Get current settings
            attrs = termios.tcgetattr(self.slave_fd)

            # Configure for raw mode
            attrs[0] = 0  # iflag
            attrs[1] = 0  # oflag
            attrs[2] |= termios.CS8  # cflag - 8 data bits
            attrs[3] = 0  # lflag - no echo, canonical mode, etc.

            # Set baud rate (doesn't matter for virtual port, but set anyway)
            attrs[4] = termios.B115200  # ispeed
            attrs[5] = termios.B115200  # ospeed

            # Apply settings
            termios.tcsetattr(self.slave_fd, termios.TCSANOW, attrs)

        except Exception as e:
            logger.warning(f"Could not configure terminal settings: {e}")

    def _create_symlink(self):
        """Create a user-friendly symlink to the PTY device"""
        if not self.slave_path:
            return

        try:
            # Create symlink in /tmp for easier access
            symlink_path = f"/tmp/cu.{self.device_name}"

            # Remove existing symlink if present
            if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                os.unlink(symlink_path)

            # Create new symlink
            os.symlink(self.slave_path, symlink_path)

            logger.info(f"Created symlink: {symlink_path} -> {self.slave_path}")

        except Exception as e:
            logger.warning(f"Could not create symlink: {e}")

    def _start_threads(self):
        """Start background threads for data handling"""
        self._read_thread = threading.Thread(target=self._read_worker, daemon=True)
        self._write_thread = threading.Thread(target=self._write_worker, daemon=True)

        self._read_thread.start()
        self._write_thread.start()

    def _stop_threads(self):
        """Stop background threads"""
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=1.0)

        if self._write_thread and self._write_thread.is_alive():
            self._write_thread.join(timeout=1.0)

    def _read_worker(self):
        """Background thread to read data from serial client"""
        logger.debug("Virtual serial read worker started")

        while self._running and self.master_fd is not None:
            try:
                # Use select to check for data availability
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)

                if ready:
                    # Read data from master (client)
                    data = os.read(self.master_fd, 1024)
                    if data:
                        logger.debug(f"Read {len(data)} bytes from virtual serial")

                        # Add to TX queue (data going to BLE)
                        self.tx_queue.put(data)

                        # Call data callback
                        if self.data_callback:
                            self.data_callback(data)

            except OSError as e:
                if e.errno in (9, 5):  # Bad file descriptor or I/O error
                    logger.debug("Virtual serial read worker: client disconnected")
                    break
                else:
                    logger.error(f"Virtual serial read error: {e}")
                    break
            except Exception as e:
                logger.error(f"Virtual serial read worker error: {e}")
                break

        logger.debug("Virtual serial read worker stopped")

    def _write_worker(self):
        """Background thread to write data to serial client"""
        logger.debug("Virtual serial write worker started")

        while self._running and self.master_fd is not None:
            try:
                # Get data from RX queue (data from BLE)
                try:
                    data = self.rx_queue.get(timeout=0.1)
                except Empty:
                    continue

                # Write data to master (client)
                if self.master_fd is not None:
                    try:
                        os.write(self.master_fd, data)
                        logger.debug(f"Wrote {len(data)} bytes to virtual serial")
                    except OSError as e:
                        if e.errno in (9, 32):  # Bad file descriptor or broken pipe
                            logger.debug("Virtual serial write worker: client disconnected")
                            break
                        else:
                            logger.error(f"Virtual serial write error: {e}")
                            # Re-queue the data
                            self.rx_queue.put(data)

                self.rx_queue.task_done()

            except Exception as e:
                logger.error(f"Virtual serial write worker error: {e}")

        logger.debug("Virtual serial write worker stopped")

    def _cleanup(self):
        """Clean up resources"""
        # Close file descriptors
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None

        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except:
                pass
            self.slave_fd = None

        # Remove symlink
        if self.slave_path:
            symlink_path = f"/tmp/cu.{self.device_name}"
            try:
                if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                    os.unlink(symlink_path)
            except:
                pass

        self.slave_path = None

    def send_data(self, data: bytes) -> bool:
        """Send data to the serial client (from BLE)"""
        if not self.is_open:
            return False

        try:
            self.rx_queue.put(data)
            return True
        except Exception as e:
            logger.error(f"Error queuing data for virtual serial: {e}")
            return False

    def receive_data(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get data from serial client (to BLE)"""
        try:
            return self.tx_queue.get(timeout=timeout)
        except Empty:
            return None

    def get_device_path(self) -> Optional[str]:
        """Get the device path that clients should connect to"""
        return self.slave_path

    def get_symlink_path(self) -> str:
        """Get the symlink path for easier access"""
        return f"/tmp/cu.{self.device_name}"

    def get_info(self) -> dict:
        """Get virtual serial port information"""
        return {
            'device_name': self.device_name,
            'slave_path': self.slave_path,
            'symlink_path': self.get_symlink_path(),
            'is_open': self.is_open,
            'master_fd': self.master_fd,
            'slave_fd': self.slave_fd,
            'rx_queue_size': self.rx_queue.qsize(),
            'tx_queue_size': self.tx_queue.qsize()
        }