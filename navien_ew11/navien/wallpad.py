import time
import socket
import select
import logging
import paho.mqtt.client as mqtt
from protocol_utils import ProtocolUtils
from logger import setup_logger

class Wallpad:
    def __init__(self, config_manager):
        self.config = config_manager
        self.logger = setup_logger("Wallpad")
        self._device_list = []
        self.sock = None
        self.mqtt_client = None
        self._is_running = True
        
        self.MAX_BUFFER_SIZE = 4096
        self.MAX_PACKET_LEN = 120 
        
        self._setup_mqtt()

    def _setup_mqtt(self):
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if self.config.mqtt_username:
            self.mqtt_client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_message = self._on_mqtt_message
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        
        try:
            self.mqtt_client.connect(self.config.mqtt_server, self.config.mqtt_port)
            self.mqtt_client.loop_start()
        except Exception as e:
            self.logger.critical(f"MQTT Connection Failed: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            self.logger.info("MQTT Connected Successfully")
            client.subscribe(f"{self.config.root_topic}/+/+/+/set")
            client.subscribe(f"{self.config.root_topic}/+/+/+/+/set")
        else:
            self.logger.error(f"MQTT Connection Failed with code {rc}")

    def _on_mqtt_disconnect(self, client, userdata, flags, rc=0, properties=None):
        self.logger.warning("MQTT Disconnected. Library will auto-reconnect...")

    def _connect_socket(self):
        if self.sock:
            try: self.sock.close()
            except: pass
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(5.0)
            self.sock.connect((self.config.socket_ip, self.config.socket_port))
            self.logger.info(f"Connected to EW11 ({self.config.socket_ip}:{self.config.socket_port})")
            return True
        except Exception as e:
            self.logger.error(f"EW11 Connection Error: {e}")
            return False

    def add_device(self, *args, **kwargs):
        from device import Device
        device = Device(*args, **kwargs)
        self._device_list.append(device)
        return device

    def close(self):
        """Safe shutdown"""
        self._is_running = False
        if self.sock:
            self.sock.close()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
        self.logger.info("Wallpad controller shutdown complete.")

    def listen(self):
        # Discovery
        self.logger.info("Publishing Discovery payloads...")
        for device in self._device_list:
            if device.mqtt_discovery:
                payloads = device.get_mqtt_discovery_payload(self.config.root_topic, self.config.homeassistant_root_topic)
                for topic, payload in payloads:
                    self.mqtt_client.publish(topic, payload, qos=1, retain=True)

        buffer = b''
        self.logger.info("Main loop started.")
        
        while self._is_running:
            if self.sock is None:
                if not self._connect_socket():
                    time.sleep(5)
                    continue

            try:
                readable, _, _ = select.select([self.sock], [], [], 1.0)
                if self.sock in readable:
                    try:
                        data = self.sock.recv(1024)
                    except Exception as e:
                        self.logger.error(f"Socket Recv Error: {e}")
                        data = None
                    
                    if not data:
                        self.logger.warning("Socket closed by remote or empty data")
                        self.sock.close()
                        self.sock = None
                        continue
                        
                    buffer += data
                
                if len(buffer) > self.MAX_BUFFER_SIZE:
                    self.logger.warning("Buffer overflow! Clearing.")
                    buffer = buffer[-self.MAX_BUFFER_SIZE:]

                while True:
                    try: start_idx = buffer.index(b'\xf7')
                    except ValueError:
                        buffer = b''
                        break
                    if start_idx > 0: buffer = buffer[start_idx:]
                    if len(buffer) < 5: break

                    packet_found = False
                    search_limit = min(len(buffer) + 1, self.MAX_PACKET_LEN)
                    
                    for length in range(5, search_limit):
                        hex_str = buffer[:length].hex()
                        if ProtocolUtils.is_valid(hex_str):
                            self._handle_valid_packet(hex_str)
                            buffer = buffer[length:]
                            packet_found = True
                            break
                    if packet_found: continue
                    else:
                        if len(buffer) < self.MAX_PACKET_LEN: break
                        buffer = buffer[1:] 

            except Exception as e:
                self.logger.error(f"Socket Loop Critical Error: {e}")
                self.sock = None
                time.sleep(3)

    def _handle_valid_packet(self, hex_str):
        payload_dict = ProtocolUtils.parse_payload(hex_str)
        if not payload_dict: return
        try:
            device = self.get_device(
                device_id=payload_dict['device_id'], 
                device_subid=payload_dict['device_subid']
            )
            for topic, value in device.parse_payload(payload_dict, self.config.root_topic).items():
                self.mqtt_client.publish(topic, value, qos=0)
        except ValueError: pass

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            parts = msg.topic.split('/')
            # [Safety] 배열 길이 확인
            if len(parts) < 5 or parts[-1] != 'set': return
            
            device_class = parts[1]
            full_name = parts[2]
            attr_name = parts[3]
            value = msg.payload.decode()

            try: 
                device = self.get_device(device_name=full_name, device_class=device_class)
            except ValueError: 
                return

            if device.device_name == "전열교환기":
                if attr_name == "percentage" and value == "0": attr_name, value = "power", "OFF"
            
            child_name = None
            if full_name != device.device_name:
                for child in device.child_devices:
                    if full_name == f"{child}{device.device_name}":
                        child_name = child
                        break
                if child_name is None:
                    return

            cmd_bytes = device.get_command_payload(attr_name, value, child_name=child_name)
            
            if self.sock:
                self.sock.sendall(cmd_bytes)
                self.logger.info(f"CMD > {full_name}: {cmd_bytes.hex()}")
            else:
                self.logger.error("Socket disconnected, command dropped")

        except Exception as e:
            self.logger.error(f"Command Processing Error: {e}")

    def get_device(self, **kwargs):
        t_name = kwargs.get('device_name')
        t_class = kwargs.get('device_class')
        t_id = kwargs.get('device_id')
        t_subid = kwargs.get('device_subid')
        
        for device in self._device_list:
            if t_name:
                if t_class and device.device_class != t_class: continue
                if device.device_name == t_name: return device
                if device.child_devices:
                    if t_name in [f"{c}{device.device_name}" for c in device.child_devices]:
                        return device
            elif t_id and t_subid:
                if device.device_id == t_id and device.device_subid == t_subid: return device
                    
        raise ValueError(f"Device not found: {kwargs}")
