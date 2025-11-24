import asyncio
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from .transport import AsyncConnection
from .controller import NavienController
from .const import DOMAIN

class NavienGateway:
    def __init__(self, hass: HomeAssistant, host, port):
        self.hass = hass
        self.conn = AsyncConnection(host, port)
        self.controller = NavienController(self)
        self.devices = {}
        self._reconnect_task = None

    async def start(self):
        await self.conn.open()
        asyncio.create_task(self._loop())

    async def stop(self):
        await self.conn.close()

    async def _loop(self):
        while True:
            data = await self.conn.recv()
            if data:
                self.controller.feed(data)
            else:
                # Connection lost, wait and retry
                await asyncio.sleep(5)
                try: await self.conn.open()
                except: pass

    @callback
    def update_device(self, state):
        uid = state.key.unique_id
        if uid not in self.devices:
            self.devices[uid] = state
            async_dispatcher_send(self.hass, f"{DOMAIN}_new_device", state)
        else:
            self.devices[uid] = state
            async_dispatcher_send(self.hass, f"{DOMAIN}_update_{uid}", state)

    async def send(self, key, action, **kwargs):
        pkt = self.controller.make_cmd(key.device_type, key.index, action, **kwargs)
        await self.conn.send(pkt)