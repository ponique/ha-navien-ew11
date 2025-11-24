import re
import json
from json import dumps as json_dumps
from collections import defaultdict
from protocol_utils import ProtocolUtils

class Device:
    def __init__(self, device_name, device_id, device_subid, device_class, child_devices=None, mqtt_discovery=True, optional_info=None):
        self.device_name = device_name
        self.device_id = device_id
        self.device_subid = device_subid
        self.device_unique_id = f'rs485_{self.device_id}_{self.device_subid}'
        self.device_class = device_class
        self.child_devices = child_devices or []
        self.mqtt_discovery = mqtt_discovery
        self.optional_info = optional_info or {}
        self.status_messages = defaultdict(list)
        self.command_messages = {}

    def register_status(self, message_flag, attr_name, regex, topic_class, device_name=None, process_func=lambda v: v):
        device_name = device_name or self.device_name
        self.status_messages[message_flag].append({
            'regex': regex, 'process_func': process_func, 
            'device_name': device_name, 'attr_name': attr_name, 'topic_class': topic_class
        })

    def register_command(self, message_flag, attr_name, topic_class, controll_id=None, process_func=lambda v: v):
        self.command_messages[attr_name] = {
            'message_flag': message_flag, 'attr_name': attr_name, 'topic_class': topic_class, 
            'process_func': process_func, 'controll_id': controll_id
        }

    def parse_payload(self, payload_dict, root_topic):
        result = {}
        for status in self.status_messages[payload_dict['message_flag']]:
            parse_status = re.match(status['regex'], payload_dict['data'])
            if not parse_status: continue
            
            if len(self.child_devices) > 0:
                for index, child_device in enumerate(self.child_devices):
                    topic = f"{root_topic}/{self.device_class}/{child_device}{self.device_name}/{status['attr_name']}"
                    try:
                        if self.device_class == 'climate':
                            # 1=Power, 2=Away, 3=Current, 4=Target
                            target_group = 1
                            if status['attr_name'] == 'away_mode': target_group = 2
                            elif status['attr_name'] == 'currenttemp': target_group = 3
                            elif status['attr_name'] == 'targettemp': target_group = 4
                            
                            raw_val = parse_status.group(target_group)
                            
                            if status['attr_name'] in ['power', 'away_mode']:
                                result[topic] = status['process_func'](raw_val, index)
                            else:
                                result[topic] = status['process_func'](raw_val, index)

                        elif self.device_class == 'light':
                            result[topic] = status['process_func'](parse_status.group(index + 1))
                        else:
                            result[topic] = status['process_func'](parse_status.group(index + 1))
                    except (IndexError, ValueError): pass
            else:
                topic = f"{root_topic}/{self.device_class}/{self.device_name}/{status['attr_name']}"
                try:
                    # 그룹이 여러개인 전열교환기 처리
                    if parse_status.lastindex and parse_status.lastindex >= 1:
                         # 람다 함수 인자 개수에 따라 처리 (단순화)
                         # device_registry에서 람다로 처리하도록 raw값만 넘기거나
                         # 가장 첫번째 그룹을 넘김. 
                         # 전열교환기는 register_status에서 캡처그룹 1개만 쓰도록 최적화했으므로 문제없음.
                         result[topic] = status['process_func'](parse_status.group(1))
                except IndexError: pass
        return result

    def get_command_payload(self, attr_name, attr_value, child_name=None):
        attr_value = self.command_messages[attr_name]['process_func'](attr_value)
        if child_name is not None:
            idx = self.child_devices.index(child_name)
            cid = self.command_messages[attr_name]['controll_id'][idx]
            command_payload = ['f7', self.device_id, cid, self.command_messages[attr_name]['message_flag'], '01', attr_value]
        elif self.device_id == '33' and self.command_messages[attr_name]['message_flag'] == '81':
            command_payload = ['f7', self.device_id, self.device_subid, self.command_messages[attr_name]['message_flag'], '03', '00', attr_value, '00']
        else:
            # 전열교환기 42번 명령은 '01' + 값
            if (self.device_id == '32' and self.command_messages[attr_name]['message_flag'] == '42'):
                command_payload = ['f7', self.device_id, self.device_subid, self.command_messages[attr_name]['message_flag'], '01', attr_value]
            else:
                command_payload = ['f7', self.device_id, self.device_subid, self.command_messages[attr_name]['message_flag'], '00']
        
        command_payload.append(ProtocolUtils.xor(command_payload))
        command_payload.append(ProtocolUtils.add(command_payload))
        return bytes(bytearray.fromhex(' '.join(command_payload)))

    def get_mqtt_discovery_payload(self, root_topic, ha_root_topic):
        discovery_list = []
        if len(self.child_devices) > 0:
            for idx, child in enumerate(self.child_devices):
                u_id = self.device_unique_id + str(idx)
                d_name = child + self.device_name
                topic = f"{ha_root_topic}/{self.device_class}/{u_id}/config"
                res = {
                    '~': f"{root_topic}/{self.device_class}/{d_name}",
                    'name': d_name, 'uniq_id': u_id, 'device_class': self.device_class
                }
                res.update(self.optional_info)
                for sl in self.status_messages.values():
                    for s in sl: res[s['topic_class']] = f"~/{s['attr_name']}"
                for sl in self.command_messages.values():
                    res[sl['topic_class']] = f"~/{sl['attr_name']}/set"
                res['device'] = {'identifiers': u_id, 'name': d_name}
                discovery_list.append((topic, json_dumps(res, ensure_ascii=False)))
        else:
            topic = f"{ha_root_topic}/{self.device_class}/{self.device_unique_id}/config"
            res = {
                '~': f"{root_topic}/{self.device_class}/{self.device_name}",
                'name': self.device_name, 'uniq_id': self.device_unique_id
            }
            res.update(self.optional_info)
            for sl in self.status_messages.values():
                for s in sl: res[s['topic_class']] = f"~/{s['attr_name']}"
            for sl in self.command_messages.values():
                res[sl['topic_class']] = f"~/{sl['attr_name']}/set"
            res['device'] = {'identifiers': self.device_unique_id, 'name': self.device_name}
            discovery_list.append((topic, json_dumps(res, ensure_ascii=False)))
        return discovery_list