"""Unprivileged reader for the protected, read-only Windows sensor host."""
import ctypes
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
MAX_AGE_MS = 5000


def tick_ms():
    kernel = ctypes.WinDLL('kernel32')
    kernel.GetTickCount64.restype = ctypes.c_ulonglong
    return kernel.GetTickCount64()


@lru_cache(maxsize=1)
def locations():
    result = subprocess.run(['whoami.exe', '/user', '/fo', 'csv', '/nh'], capture_output=True,
                            text=True, encoding='utf-8', errors='replace', timeout=5, creationflags=FLAGS, check=True)
    matches = re.findall(r'S-1-5-(?:\d+-)*\d+', result.stdout)
    if len(matches) != 1: raise RuntimeError('Cannot identify the Windows user for sensor access.')
    sid = matches[0]
    return (Path(os.environ['ProgramData'])/'TryxAiDashboard'/sid/'sensors.json',
            Path(os.environ['USERPROFILE'])/'.tryx-ai-dashboard'/'sensors.lease', 'TRYX AI Sensors-'+sid)


def fresh_payload(payload, now_ms):
    if not isinstance(payload, dict) or payload.get('app') != 'TRYX-Native-Sensors' or payload.get('schema_version') != 1:
        return False
    tick = payload.get('tick_ms')
    return (isinstance(tick, int) and not isinstance(tick, bool) and 0 <= now_ms-tick < MAX_AGE_MS
            and isinstance(payload.get('sensors'), list))


def usable(sensor, kind):
    value = sensor.get('value')
    if sensor.get('type') != kind or isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        return False
    return 0 < value <= 150 if kind == 'Temperature' else value >= 0


def select(sensors, kind, names, explicit=None):
    if explicit:
        matches = [s for s in sensors if s.get('id') == explicit and usable(s, kind)]
        return matches[0] if len(matches) == 1 else None
    for name in names:
        matches = [s for s in sensors if s.get('name', '').casefold() == name.casefold() and usable(s, kind)]
        if len(matches) == 1: return matches[0]
        if len(matches) > 1: return None
    return None


def map_sensors(payload, config, now_ms):
    result = dict(cpu_temp_c=None, cpu_power_w=None, fan_rpm=None, cpu_source='LibreHardwareMonitor',
                  sensor_age_s=None, cpu_temp_sensor=None, cpu_power_sensor=None, fan_sensor=None)
    if not fresh_payload(payload, now_ms): return result
    result['sensor_age_s'] = (now_ms-payload['tick_ms'])/1000
    sensors = [s for s in payload['sensors'] if isinstance(s, dict)]
    cpus = [s for s in sensors if s.get('hardware_type') == 'Cpu']
    cpu_ids = sorted({s.get('hardware_id', '') for s in cpus})
    cpu_id = config.get('cpu_hardware_id') or (cpu_ids[0] if len(cpu_ids) == 1 else None)
    cpu = [s for s in cpus if cpu_id and s.get('hardware_id') == cpu_id]
    board = [s for s in sensors if s.get('hardware_type') in ('SuperIO', 'Motherboard', 'EmbeddedController')]
    mappings = [
        ('cpu_temp_c', 'cpu_temp_sensor', select(cpu, 'Temperature', ['Core (Tctl/Tdie)', 'CPU (Tctl/Tdie)', 'CPU Package', 'Core (Tdie)', 'Core Average'], config.get('cpu_temp_sensor_id'))),
        ('cpu_power_w', 'cpu_power_sensor', select(cpu, 'Power', ['Package', 'CPU Package'], config.get('cpu_power_sensor_id'))),
        ('fan_rpm', 'fan_sensor', select(board, 'Fan', ['CPU Fan', 'CPU Fan #1', 'CPU'], config.get('fan_sensor_id'))),
    ]
    for field, identity, sensor in mappings:
        if sensor:
            result[field], result[identity] = sensor['value'], sensor['id']
    # LHM GPU identifiers are distinct from NVML indices. Only auto-select when unambiguous.
    gpus = [s for s in sensors if s.get('hardware_type', '').startswith('Gpu')]
    gpu_ids = sorted({s.get('hardware_id', '') for s in gpus})
    gpu_id = config.get('native_gpu_hardware_id') or (gpu_ids[0] if len(gpu_ids) == 1 else None)
    gpu = [s for s in gpus if gpu_id and s.get('hardware_id') == gpu_id]
    if gpu:
        result.update(gpu_source='LibreHardwareMonitor', gpu_label=gpu[0].get('hardware_name', 'GPU'))
        for field, kind, names in [
            ('gpu_temp_c', 'Temperature', ['GPU Core']), ('gpu_util', 'Load', ['GPU Core']),
            ('gpu_power_w', 'Power', ['GPU Package', 'GPU Power', 'GPU Total']),
            ('gpu_clock_mhz', 'Clock', ['GPU Core'])]:
            sensor = select(gpu, kind, names)
            result[field] = sensor['value'] if sensor else None
    return result


class NativeSensors:
    def __init__(self):
        self.path, self.lease, self.task = locations()
        self.last_start = -math.inf
        self.last_payload = {}

    def read(self, now):
        try:
            info = self.path.stat()
            if info.st_size > 1024*1024 or not 0 <= time.time()-info.st_mtime < 10: return {}
            payload = json.loads(self.path.read_text(encoding='utf-8-sig'))
            return payload if fresh_payload(payload, now) else {}
        except (OSError, ValueError): return {}

    def poll(self):
        now = tick_ms()
        try:
            self.lease.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.lease.with_suffix('.tmp')
            temporary.write_text(str(now), encoding='ascii')
            temporary.replace(self.lease)
        except OSError:
            # The elevated reader can briefly hold the lease. Retry next poll.
            pass
        payload = self.read(now)
        if payload: self.last_payload = payload
        elif fresh_payload(self.last_payload, now): payload = self.last_payload
        if not payload and time.monotonic()-self.last_start > 30:
            self.last_start = time.monotonic()
            subprocess.run(['schtasks.exe', '/Run', '/TN', self.task], capture_output=True,
                           timeout=5, creationflags=FLAGS)
        return payload


def native_loop(stop, publish):
    reader = None
    while not stop.is_set():
        try:
            if reader is None: reader = NativeSensors()
            publish(reader.poll())
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            publish({})
        stop.wait(1)
    release_lease()


def release_lease():
    try: locations()[1].unlink(missing_ok=True)
    except (OSError, RuntimeError, subprocess.SubprocessError): pass
