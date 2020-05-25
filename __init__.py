"""SECTOR ALARM"""
import logging
import json
import asyncio
import aiohttp
from datetime import datetime, timedelta
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.util import Throttle
from homeassistant.helpers import discovery

_LOGGER = logging.getLogger(__name__)

DOMAIN = "sector"

DEFAULT_NAME = "sector"
DATA_SA = "sector"

MIN_TIME_BETWEEN_UPDATES = timedelta(seconds=60)

CONF_USERID = "userid"
CONF_PASSWORD = "password"
CONF_CODE_FORMAT = "code_format"
CONF_CODE = "code"

CONFIG_SCHEMA = vol.Schema(
    {
    DOMAIN: vol.Schema(
        {
            vol.Required(CONF_USERID): cv.string,
            vol.Required(CONF_PASSWORD): cv.string,
            vol.Optional(CONF_CODE, default=""): cv.string,
            vol.Optional(CONF_CODE_FORMAT, default="^\\d{4,6}$"): cv.string,
        }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass, config):
    """Set Sector Alarm sensors"""
    firstrun = {}
    USERID = config[DOMAIN][CONF_USERID]
    PASSWORD = config[DOMAIN][CONF_PASSWORD]

    AUTH_TOKEN = ""
    FULLSYSTEMINFO = {}
    PANELID = ""

    message_headers = {
        "API-Version":"6",
        "Platform":"iOS",
        "User-Agent":"SectorAlarm/356 CFNetwork/1152.2 Darwin/19.4.0",
        "Version":"2.0.20",
        "Connection":"keep-alive",
        "Content-Type":"application/json"
    }

    json_data = {
        "UserId": USERID,
        "Password": PASSWORD
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://mypagesapi.sectoralarm.net/api/Login/Login",
            headers=message_headers, json=json_data) as response:
            if response.status != 200:
                    _LOGGER.debug("Sector: Failed to send Login: %d", response.status)

            data_out = await response.json()
            AUTH_TOKEN = data_out['AuthorizationToken']
            _LOGGER.debug("Sector: AUTH: %s", AUTH_TOKEN)

            message_headers = {
                "Authorization": AUTH_TOKEN,
                "API-Version":"6",
                "Platform":"iOS",
                "User-Agent":"SectorAlarm/356 CFNetwork/1152.2 Darwin/19.4.0",
                "Version":"2.0.20",
                "Connection":"keep-alive",
                "Content-Type":"application/json"
            }

        async with session.get("https://mypagesapi.sectoralarm.net/api/panel/getFullSystem",
            headers=message_headers) as response:
            if response.status != 200:
                _LOGGER.debug("Sector: Failed to get Full system: %d", response.status)

            firstrun = await response.json()

    PANELID = firstrun['Panel']['PanelId']
    FULLSYSTEMINFO = firstrun

    sector_data = SectorAlarmHub(FULLSYSTEMINFO, PANELID, USERID, PASSWORD, AUTH_TOKEN)
    await sector_data.async_update()
    hass.data[DATA_SA] = sector_data

    hass.async_create_task(
            discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
        )

    hass.async_create_task(
            discovery.async_load_platform(
                hass, 'lock', DOMAIN, {
                    CONF_CODE_FORMAT: config[DOMAIN][CONF_CODE_FORMAT],
                    CONF_CODE: config[DOMAIN][CONF_CODE]
                }, config))

    hass.async_create_task(
            discovery.async_load_platform(
                hass,
                "alarm_control_panel",
                DOMAIN,
                {
                    CONF_CODE_FORMAT: config[DOMAIN][CONF_CODE_FORMAT],
                    CONF_CODE: config[DOMAIN][CONF_CODE],
                },
                config,
            )
        )


    # Return boolean to indicate that initialization was successfully.
    return True

class SectorAlarmHub(object):
    """Implementation of Sector Alarm sensor"""

    def __init__(self, fullsysteminfo, panel_id, userid, password, authtoken):

        self._lockstatus = {}
        self._tempstatus = {}
        self._alarmstatus = None
        self._changed_by = None

        self.fullsysteminfo = fullsysteminfo
        self.panel_id = panel_id
        self.userid = userid
        self.password = password
        self.authtoken = authtoken


    async def get_thermometers(self):
        temps = self.fullsysteminfo['Temperatures']

        if temps is None:
            _LOGGER.debug("Sector Alarm failed to fetch temperature sensors")
            return None

        return (temp["Label"] for temp in temps)

    async def get_locks(self):
        locks = self.fullsysteminfo['Locks']

        if locks is None:
            _LOGGER.debug("Sector Alarm failed to fetch locks")
            return None

        return (lock["Serial"] for lock in locks)

    async def get_panel(self):
        panel = self.fullsysteminfo['Panel']

        if panel is None:
            _LOGGER.debug("Sector Alarm failed to fetch panel")
            return None

        return panel["PanelDisplayName"]

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    async def async_update(self):
        AUTH_TOKEN = self.authtoken
        async with aiohttp.ClientSession() as session:
            message_headers = {
                "Authorization": AUTH_TOKEN,
                "API-Version":"6",
                "Platform":"iOS",
                "User-Agent":"SectorAlarm/356 CFNetwork/1152.2 Darwin/19.4.0",
                "Version":"2.0.20",
                "Connection":"keep-alive",
                "Content-Type":"application/json",
            }

            async with session.get("https://mypagesapi.sectoralarm.net/api/panel/getFullSystem",
                headers=message_headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Sector: Failed to get full system in async_update, run login: %d", response.status)
                    message_headers = {
                        "API-Version":"6",
                        "Platform":"iOS",
                        "User-Agent":"SectorAlarm/356 CFNetwork/1152.2 Darwin/19.4.0",
                        "Version":"2.0.20",
                        "Connection":"keep-alive",
                        "Content-Type":"application/json"
                    }

                    json_data = {
                        "UserId": self.userid,
                        "Password": self.password
                    }
                    async with session.post("https://mypagesapi.sectoralarm.net/api/Login/Login",
                        headers=message_headers, json=json_data) as response:
                        if response.status != 200:
                            _LOGGER.debug("Sector: Failed to send Login: %d", response.status)
                            return False
                        data_out = await response.json()
                        #return data_out
                        dateTimeObj = datetime.now()
                        timestampStr = dateTimeObj.strftime("%d-%b-%Y (%H:%M:%S.%f)")
                        _LOGGER.debug("Sector: SECTOR ALARM LOGIN RUN %s", timestampStr)
                        #returndata = await async_login()
                        AUTH_TOKEN = data_out['AuthorizationToken']
                        self.authtoken = data_out['AuthorizationToken']
                        message_headers = {
                            "Authorization": AUTH_TOKEN,
                            "API-Version":"6",
                            "Platform":"iOS",
                            "User-Agent":"SectorAlarm/356 CFNetwork/1152.2 Darwin/19.4.0",
                            "Version":"2.0.20",
                            "Connection":"keep-alive",
                            "Content-Type":"application/json",
                        }
                _LOGGER.debug("Sector: AUTH_TOKEN still valid: %s", AUTH_TOKEN)

            async with session.get("https://mypagesapi.sectoralarm.net/api/Panel/GetTemperatures?panelId={}".format(self.panel_id),
                headers=message_headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Sector: Failed to get temperature update: %d", response.status)
                    return False
                else:
                    tempinfo = await response.json()
                    self._tempstatus = {
                        temperature["Label"]: temperature["Temprature"]
                        for temperature in tempinfo
                    }
                    _LOGGER.debug("Sector: Tempstatus fetch: %s", json.dumps(self._tempstatus))

            async with session.get("https://mypagesapi.sectoralarm.net/api/Panel/GetLockStatus?panelId={}".format(self.panel_id),
                headers=message_headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Sector: Failed to get locks update: %d", response.status)
                    return False
                else:
                    lockinfo = await response.json()
                    self._lockstatus = {
                        lock["Serial"]: lock["Status"]
                        for lock in lockinfo
                    }
                    _LOGGER.debug("Sector: Lockstatus fetch: %s", json.dumps(self._lockstatus))

            async with session.get("https://mypagesapi.sectoralarm.net/api/Panel/GetPanelStatus?panelId={}".format(self.panel_id),
                headers=message_headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Sector: Failed to get panel update: %d", response.status)
                    return False
                else:
                    alarminfo = await response.json()
                    self._alarmstatus = alarminfo['Status']
                    _LOGGER.debug("Sector: Alarmstatus fetch: %s", json.dumps(self._alarmstatus))

            async with session.get("https://mypagesapi.sectoralarm.net/api/panel/GetLogs?panelId={}".format(self.panel_id),
                headers=message_headers) as response:
                if response.status != 200:
                    _LOGGER.debug("Sector: Failed to get logs update: %d", response.status)
                    return False
                else:
                    loginfo = await response.json()
                    for users in loginfo:
                        if users['User'] != "" and "arm" in users['EventType']:
                            self._changed_by = users['User']
                            _LOGGER.debug("Sector: Last changed fetch: %s", json.dumps(self._changed_by))
                            break
                        else:
                            self._changed_by = "unknown"
                    _LOGGER.debug("Sector: Last changed fetch: %s", json.dumps(self._changed_by))

        return True

    @property
    def alarm_state(self):
        return self._alarmstatus

    @property
    def alarm_changed_by(self):
        return self._changed_by

    @property
    def temp_state(self):
        return self._tempstatus

    @property
    def lock_state(self):
        return self._lockstatus

    @property
    def alarm_id(self):
        return self.fullsysteminfo['Panel']['PanelId']
