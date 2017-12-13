#### A HA Component fot Aliyun IoT Link Develop Platform

##### 1. 在 [Link Develop](http://linkdevelop.aliyun.com) 平台创建网关产品和设备，并接入；

如何在 [Link Develop](http://linkdevelop.aliyun.com) 平台创建网关产品和设备此处略去，直接讲创建后在 hass 里的集成。

首先，该 Component 依赖 `mqtt component`，需要先完成`mqtt component`的配置：

```yaml
mqtt:
  broker: {GATEWAY.product_key}.iot-as-mqtt.cn-shanghai.aliyuncs.com
  port: 1883
  client_id: {GATEWAY.product_key}.{GATEWAY.device_name}|securemode=3,signmethod=hmacsha1,gw=1|
  username: {GATEWAY.device_name}&{GATEWAY.product_key}
  password: {GATEWAT.sign}
  keepalive: 60
```

其中，`{GATEWAY.product_key}`对应于 [Link Develop](http://linkdevelop.aliyun.com) 平台上创建的网关型产品的`productKey`，`{GATEWAY.device_name}`是网关设备的`deviceName`，`{GATEWAT.sign}`的生成方法如下：

```python
def make_hmacsha1_hexdigest(key, data):
    """Generate HMAC-SHA1 Signature"""
    key = bytes(key, 'UTF-8')
    data = bytes(data, 'UTF-8')
    return hmac.new(key, data, hashlib.sha1).hexdigest()

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
```

完成`mqtt component`的配置后，重启`hass`，在 Link Develop 平台上即可看到该网关设备已经激活并上线。



##### 2. 在 [Link Develop](http://linkdevelop.aliyun.com) 平台创建具体的产品和设备，并在 hass 的配置文件中添加配置；

同样的，在 [Link Develop](http://linkdevelop.aliyun.com) 中创建一个 MotionSensor 产品和测试设备，添加好产品功能定义，注意此处需要功能定义的`标识符`和`hass`中的`binary_sensor.motion_sensor*`的属性名保持一致，如：`state`, `value`, `friendly_name`,`battery_level`等。当然你也可以创建其他类型的设备，如温湿度传感器。

完成后我们开始`aliyun_iot`这个 Component 的配置，打开`hass`的`configuration.yaml`，加入类似这样的配置：

```yaml
aliyun_iot:
  gateway:
    key: {GATEWAY.product_key}
    name: {GATEWAY.device_name}
    secret: {GATEWAY.device_secret}
  component_config_glob:
    'binary_sensor.motion_sensor*':
      include_attributes: 'friendly_name,battery_level,state,value'
  iot_devices:
    # 客厅人体传感器
    - product_key: {DEVICE.product_key}
      device_name: {DEVICE.device_name}
      device_secret: {DEVICE.device_secret}
      entity_id: binary_sensor.motion_sensor_158d00012a1978 # 对应 hass 中设备的 entity_id
```

`gateway`就是上面添加的网关产品和设备的信息；

`component_config_glob`是用来设定上传`hass`中该类型设备的哪些属性；

`iot_devices`是在 [Link Develop](http://linkdevelop.aliyun.com) 平台上创建的实际设备，可以添加多个设备；



##### 3. 配置完成后重启`hass`，会自动完成设备的激活和拓扑添加到网关的动作；

##### 4. 确认在网关设备中已经出现子设备，随后再次重启`hass`，完成设备的上线和数据上报，至此设备接入完成；



##### TODO：

1. 在设备拓扑添加完成后自动完成设备的上线和数据上报，避免重启两次；
2. 在`aliyun_iot`这个 Component 中自动完成`mqtt`的配置和初始化，避免`mqtt`的`sign`之类的信息还需要自己写代码生成后再填写；

