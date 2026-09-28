import asyncio
import logging
from datetime import datetime, timezone
from time import monotonic_ns
from uuid import uuid4

LOGGER = logging.getLogger(__name__)
WIRE_LOGGER = logging.getLogger(f"{__package__}.wire")
PACKET_LOGGER = logging.getLogger(f"{__package__}.packet")


def _debug_event(logger, event, **fields):
    """Format observation metadata only while the selected logger is enabled."""
    if not logger.isEnabledFor(logging.DEBUG):
        return
    logger.debug(
        "%s wall_utc=%s mono_ns=%d %s",
        event,
        datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        monotonic_ns(),
        " ".join(f"{key}={value!r}" for key, value in fields.items()),
    )

class AsyncConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._connected = False
        self._debug_connection_id = None
        self._debug_rx_sequence = 0

    async def open(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self._connected = True
            self._debug_connection_id = uuid4().hex
            self._debug_rx_sequence = 0
            LOGGER.info(f"Connected to {self.host}:{self.port}")
        except Exception as e:
            self._connected = False
            LOGGER.error(f"Connection failed: {e}")
            # Re-raise to let gateway handle retry
            raise e

    async def close(self):
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except: pass
        self._connected = False

    async def send(self, data: bytes, *, tx_id=None):
        _debug_connection_id = self._debug_connection_id
        if not self._connected or not self.writer:
            _debug_event(PACKET_LOGGER, "TX_RESULT", connection=_debug_connection_id,
                         tx_id=tx_id, result="SKIPPED_NOT_CONNECTED", attempted_bytes=0)
            return
        if PACKET_LOGGER.isEnabledFor(logging.DEBUG):
            _debug_event(PACKET_LOGGER, "TX_ATTEMPT", connection=_debug_connection_id,
                         tx_id=tx_id, length=len(data), raw=data.hex())
        _debug_stage = "WRITE"
        try:
            self.writer.write(data)
            _debug_event(PACKET_LOGGER, "TX_RESULT", connection=_debug_connection_id,
                         tx_id=tx_id, result="WRITE_QUEUED", attempted_bytes=len(data))
            _debug_stage = "DRAIN"
            await self.writer.drain()
            _debug_event(PACKET_LOGGER, "TX_RESULT", connection=_debug_connection_id,
                         tx_id=tx_id, result="DRAIN_COMPLETED", attempted_bytes=len(data),
                         ack="NOT_OBSERVED")
        except Exception as e:
            _debug_event(PACKET_LOGGER, "TX_RESULT", connection=_debug_connection_id,
                         tx_id=tx_id, result="ERROR", stage=_debug_stage,
                         error_type=type(e).__name__)
            LOGGER.error(f"Send error: {e}")
            self._connected = False

    async def recv(self):
        _debug_connection_id = self._debug_connection_id
        _debug_sequence = self._debug_rx_sequence
        if not self._connected or not self.reader:
            return None
        try:
            data = await self.reader.read(1024)
            if not data: # EOF
                _debug_event(WIRE_LOGGER, "RX_EOF", connection=_debug_connection_id,
                             sequence=_debug_sequence)
                self._connected = False
                return None
            _debug_sequence += 1
            if self._debug_connection_id == _debug_connection_id:
                self._debug_rx_sequence = _debug_sequence
            if WIRE_LOGGER.isEnabledFor(logging.DEBUG):
                _debug_event(WIRE_LOGGER, "RX_CHUNK", connection=_debug_connection_id,
                             sequence=_debug_sequence, kind="TCP_CHUNK",
                             length=len(data), raw=data.hex())
            return data
        except Exception as _debug_error:
            _debug_event(WIRE_LOGGER, "RX_ERROR", connection=_debug_connection_id,
                         sequence=_debug_sequence,
                         error_type=type(_debug_error).__name__)
            self._connected = False
            return None