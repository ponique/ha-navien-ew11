import asyncio
import logging

LOGGER = logging.getLogger(__name__)

class AsyncConnection:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._connected = False

    async def open(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self._connected = True
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

    async def send(self, data: bytes):
        if not self._connected or not self.writer:
            return
        try:
            self.writer.write(data)
            await self.writer.drain()
        except Exception as e:
            LOGGER.error(f"Send error: {e}")
            self._connected = False

    async def recv(self):
        if not self._connected or not self.reader:
            return None
        try:
            data = await self.reader.read(1024)
            if not data: # EOF
                self._connected = False
                return None
            return data
        except Exception:
            self._connected = False
            return None