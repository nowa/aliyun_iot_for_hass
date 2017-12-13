"""
A component which allows you to send data to Aliyun IoT Link Develop Platform.

For more details about this component, please refer to the documentation at
https://github.com/nowa/aliyun_iot_for_hass
"""
import logging
import hashlib
import hmac
import json
import voluptuous as vol
from random import randint

from homeassistant.const import (
    EVENT_STATE_CHANGED, STATE_UNAVAILABLE, STATE_UNKNOWN, CONF_HOST,
    CONF_PORT, CONF_SSL, CONF_VERIFY_SSL, CONF_USERNAME, CONF_PASSWORD,
    CONF_EXCLUDE, CONF_INCLUDE, CONF_DOMAINS, CONF_ENTITIES, CONF_ENTITY_ID)
from homeassistant.util.dt import now as dt_now
from homeassistant.helpers import state as state_helper
from homeassistant.helpers.entity_values import EntityValues
import homeassistant.loader as loader
import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

CONF_INCLUDE_ATTRIBUTES = 'include_attributes'
CONF_COMPONENT_CONFIG = 'component_config'
CONF_COMPONENT_CONFIG_GLOB = 'component_config_glob'
CONF_COMPONENT_CONFIG_DOMAIN = 'component_config_domain'
CONF_IOT_DEVICES = 'iot_devices'
CONF_GATEWAY = 'gateway'
CONF_KEY = 'key'
CONF_NAME = 'name'
CONF_SECRET = 'secret'
CONF_PRODUCT_KEY = 'product_key'
CONF_DEVICE_NAME = 'device_name'
CONF_DEVICE_SECRET = 'device_secret'

DOMAIN = 'aliyun_iot'
MQTT_DOMAIN = 'mqtt'
DEPENDENCIES = ['mqtt']
IOT_TOPICS = {
  'thing_topo_add': "/sys/{}/{}/thing/topo/add",
  'thing_topo_add_reply': "/sys/{}/{}/thing/topo/add_reply",
  'combine_login': "/ext/session/{}/{}/combine/login",
  'combine_login_reply': "/ext/session/{}/{}/combine/login_reply",
  'property_post': "/sys/{}/{}/thing/event/property/post",
  'property_post_reply': "/sys/{}/{}/thing/event/property/post_reply",
}

COMPONENT_CONFIG_SCHEMA_ENTRY = vol.Schema({
    vol.Optional(CONF_INCLUDE_ATTRIBUTES): cv.string,
})
COMPONENT_CONFIG_SCHEMA_IOT_DEVICE = vol.Schema({
    vol.Required(CONF_PRODUCT_KEY): cv.string,
    vol.Required(CONF_DEVICE_NAME): cv.string,
    vol.Required(CONF_DEVICE_SECRET): cv.string,
    vol.Required(CONF_ENTITY_ID): cv.entity_id,
})
COMPONENT_CONFIG_SCHEMA_IOT_DEVICE_CONTAINER = vol.All(cv.ensure_list, [COMPONENT_CONFIG_SCHEMA_IOT_DEVICE])
COMPONENT_CONFIG_SCHEMA_GATEWAY = vol.Schema({
    vol.Required(CONF_KEY): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Required(CONF_SECRET): cv.string,
})

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: vol.Schema({
        vol.Required(CONF_GATEWAY, default={}): COMPONENT_CONFIG_SCHEMA_GATEWAY,
        vol.Required(CONF_IOT_DEVICES, default=[]): COMPONENT_CONFIG_SCHEMA_IOT_DEVICE_CONTAINER,
        vol.Optional(CONF_COMPONENT_CONFIG, default={}):
            vol.Schema({cv.entity_id: COMPONENT_CONFIG_SCHEMA_ENTRY}),
        vol.Optional(CONF_COMPONENT_CONFIG_GLOB, default={}):
            vol.Schema({cv.string: COMPONENT_CONFIG_SCHEMA_ENTRY}),
        vol.Optional(CONF_COMPONENT_CONFIG_DOMAIN, default={}):
            vol.Schema({cv.string: COMPONENT_CONFIG_SCHEMA_ENTRY}),
    }),
}, extra=vol.ALLOW_EXTRA)

def make_hmacsha1_hexdigest(key, data):
    """Generate HMAC-SHA1 Signature"""
    key = bytes(key, 'UTF-8')
    data = bytes(data, 'UTF-8')
    return hmac.new(key, data, hashlib.sha1).hexdigest()

def make_random_int_str():
    """Generate random int str"""
    return "%d" % randint(1000000000000000, 9999999999999999)

def sign_for_device(device):
    """Generate signature for divice"""
    if not device:
        return ['', '']
    
    now = dt_now()
    timestamp = int(now.timestamp())
    device_product_key = device[CONF_PRODUCT_KEY]
    device_name = device[CONF_DEVICE_NAME]
    device_secret = device[CONF_DEVICE_SECRET]
    device_client_id = "%s&&&%s" % (device_product_key, device_name)
    device_sign_content = "clientId%sdeviceName%sproductKey%stimestamp%d" % (device_client_id, device_name, device_product_key, timestamp)
    device_sign = make_hmacsha1_hexdigest(device_secret, device_sign_content)
    return [device_client_id, device_sign, timestamp]

def login_iot_device(gateway, device, mqtt, hass):
    """Add device topo to gateway and login"""
    if not gateway or not device:
        return
    
    sign_data = sign_for_device(device)
    
    # Prepare payload for device topo
    topo_payload = {
        'id': make_random_int_str(),
        'version': "1.0",
        'params': [{
            'productKey': device[CONF_PRODUCT_KEY],
            'deviceName': device[CONF_DEVICE_NAME],
            'clientId': sign_data[0],
            'timestamp': sign_data[2],
            'signMethod': "hmacsha1",
            'sign': sign_data[1]
        }],
        'method': "thing.topo.add"
    }
    # add topo to gateway
    mqtt.publish(hass, IOT_TOPICS['thing_topo_add'].format(gateway[CONF_KEY], gateway[CONF_NAME]), json.dumps(topo_payload))
    _LOGGER.info("Topo added for device: %s", device[CONF_DEVICE_NAME])
    
    # Prepare payload for device property post
    login_payload = {
        'id': make_random_int_str(),
        'params': {
            'productKey': device[CONF_PRODUCT_KEY],
            'deviceName': device[CONF_DEVICE_NAME],
            'clientId': sign_data[0],
            'timestamp': sign_data[2],
            'signMethod': "hmacsha1",
            'sign': sign_data[1],
            'cleanSession': True
        }
    }
    # device login
    mqtt.publish(hass, IOT_TOPICS['combine_login'].format(gateway[CONF_KEY], gateway[CONF_NAME]), json.dumps(login_payload))
    _LOGGER.info("Logged in device: %s", device[CONF_DEVICE_NAME])

def setup(hass, config):
    mqtt = loader.get_component('mqtt')
    
    conf = config[DOMAIN]
    
    iot_devices = conf.get(CONF_IOT_DEVICES, [])
    gateway = conf.get(CONF_GATEWAY, [])
    
    if not iot_devices:
        _LOGGER.warning("No iot devices found.")
        return
    else:
        _LOGGER.info("Found %s iot devices.", len(iot_devices))
    
    if not gateway:
        _LOGGER.warning("No gateway found.")
        return
    else:
        _LOGGER.info("Found configuration for gateway: %s", gateway)
    
    # whitelist and blacklist for domains and entities
    whitelist_e = []
    entities_mapping = {}
    
    # init mapping for iot devices
    for iot_device in iot_devices:
        if CONF_ENTITY_ID in iot_device:
            entity_id = iot_device.get(CONF_ENTITY_ID)
            whitelist_e.append(entity_id)
            entities_mapping[entity_id] = {}
            entities_mapping[entity_id][CONF_PRODUCT_KEY] = iot_device.get(CONF_PRODUCT_KEY)
            entities_mapping[entity_id][CONF_DEVICE_NAME] = iot_device.get(CONF_DEVICE_NAME)
            entities_mapping[entity_id][CONF_DEVICE_SECRET] = iot_device.get(CONF_DEVICE_SECRET)
            login_iot_device(gateway, entities_mapping[entity_id], mqtt, hass)
    
    _LOGGER.info("whitelist for entities: %s", whitelist_e)
    
    component_config = EntityValues(
        conf[CONF_COMPONENT_CONFIG],
        conf[CONF_COMPONENT_CONFIG_DOMAIN],
        conf[CONF_COMPONENT_CONFIG_GLOB])
    
    def aliyun_iot_event_listener(event):
        """处理所有符合配置条件的 state changed 事件，转发到 aliyun iot"""
        state = event.data.get('new_state')
        
        if state is None or state.state in (
                STATE_UNKNOWN, '', STATE_UNAVAILABLE):
            return
        
        try:
            if (whitelist_e and state.entity_id not in whitelist_e):
                return

            _LOGGER.info("%s changed state to %s", state.entity_id, state.state)
            _state = int(state_helper.state_as_number(state))
            _state_key = "value"
        except ValueError:
            _state = state.state
            _state_key = "state"
        
        mapping_device = entities_mapping[state.entity_id]
        if not mapping_device:
            return
        
        whitelist_a = []
        include_attrs = component_config.get(state.entity_id).get(
            CONF_INCLUDE_ATTRIBUTES)
        # _LOGGER.info("properties can be posted: %s", include_attrs)
        if isinstance(include_attrs, str) and include_attrs not in (None, ''):
            whitelist_a = include_attrs.split(',')
        
        # Prepare payload for device property post
        payload_json = {
            'id': make_random_int_str(),
            'version': "1.0",
            'params': {
                _state_key: _state,
            },
            'method': "thing.event.property.post"
        }
        
        for key, value in state.attributes.items():
            if len(whitelist_a) > 0 and key not in whitelist_a:
                continue
            else:
                payload_json['params'][key] = value
        
        if _state_key != "state":
            payload_json['params']['state'] = state.state
        
        _LOGGER.info("iot device property post payload json: %s", payload_json)
        
        # Post device property to Aliyun IoT Link Develop Platform
        sign_data = sign_for_device(mapping_device)
        # _LOGGER.info("device client: %s", sign_data[0])
        # _LOGGER.info("device sign: %s", sign_data[1])
        
        mqtt.publish(hass, IOT_TOPICS['property_post'].format(mapping_device[CONF_PRODUCT_KEY], mapping_device[CONF_DEVICE_NAME]), json.dumps(payload_json))
    
    hass.bus.listen(EVENT_STATE_CHANGED, aliyun_iot_event_listener)

    return True