from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_HOST, CONF_PORT, DEFAULT_PORT

class NavienConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    # 버전은 숫자여야 합니다.
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # 중복 등록 방지
            await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
            self._abort_if_unique_id_configured()
            
            return self.async_create_entry(title="Navien Wallpad", data=user_input)

        # 입력 폼 스키마
        data_schema = vol.Schema({
            vol.Required(CONF_HOST, default="192.168.0.100"): str,
            vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
        )
