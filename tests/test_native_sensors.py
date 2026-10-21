import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collector
import native_sensors as native
import settings


def sensor(identity, name, kind, value, hardware='Cpu', owner='/amdcpu/0'):
    return dict(id=identity, name=name, type=kind, value=value, hardware_type=hardware,
                hardware_id=owner, hardware_name='Test hardware')


class NativeTelemetry(unittest.TestCase):
    def setUp(self):
        self.payload = dict(app='TRYX-Native-Sensors', schema_version=1, tick_ms=100000, sensors=[
            sensor('temp', 'Core (Tctl/Tdie)', 'Temperature', 51.5),
            sensor('ccd', 'CCD1 (Tdie)', 'Temperature', 48),
            sensor('power', 'Package', 'Power', 61),
            sensor('core-power', 'Core #1 (SMU)', 'Power', 4),
            sensor('cpu-fan', 'CPU Fan', 'Fan', 1200, 'SuperIO', '/lpc/0'),
            sensor('pump', 'Pump Fan #1', 'Fan', 3400, 'SuperIO', '/lpc/0')])

    def test_selects_package_values_and_cpu_fan_without_pump(self):
        data = native.map_sensors(self.payload, {}, 101000)
        self.assertEqual((data['cpu_temp_c'], data['cpu_power_w'], data['fan_rpm']), (51.5,61,1200))
        self.assertEqual(data['fan_sensor'], 'cpu-fan')
        self.assertEqual(data['sensor_age_s'], 1)

    def test_stale_future_and_wrong_source_are_all_unknown(self):
        for now in (105000, 99999):
            data = native.map_sensors(self.payload, {}, now)
            self.assertIsNone(data['cpu_temp_c'])
            self.assertIsNone(data['fan_rpm'])
        self.payload['app'] = 'Other program'
        self.assertIsNone(native.map_sensors(self.payload, {}, 100100)['cpu_power_w'])

    def test_missing_invalid_and_zero_sensor_values(self):
        for value in (None, float('nan'), float('inf'), True, -1, 0, 999):
            self.payload['sensors'][0]['value'] = value
            self.assertIsNone(native.map_sensors(self.payload, {}, 100100)['cpu_temp_c'])
        self.payload['sensors'][4]['value'] = 0
        self.assertEqual(native.map_sensors(self.payload, {}, 100100)['fan_rpm'], 0)

    def test_fresh_file_does_not_make_old_sensor_values_fresh(self):
        self.payload['sensors'][0]['sample_tick_ms'] = 95000
        result = native.map_sensors(self.payload, {}, 100100)
        self.assertIsNone(result['cpu_temp_c'])
        self.assertEqual(result['cpu_power_w'], 61)
        self.assertEqual(result['fan_rpm'], 1200)
        for stamp in (100200, None, True, '100000'):
            self.payload['sensors'][0]['sample_tick_ms'] = stamp
            self.assertIsNone(native.map_sensors(self.payload, {}, 100100)['cpu_temp_c'])

    def test_unknown_fan_name_is_not_guessed(self):
        self.payload['sensors'][4]['name'] = 'Fan #1'
        self.assertIsNone(native.map_sensors(self.payload, {}, 100100)['fan_rpm'])
        self.assertEqual(native.map_sensors(self.payload, {'fan_sensor_id':'cpu-fan'}, 100100)['fan_rpm'], 1200)
        self.assertIsNone(native.map_sensors(self.payload, {'fan_sensor_id':'absent'}, 100100)['fan_rpm'])

    def test_multiple_cpus_require_explicit_selection(self):
        self.payload['sensors'].append(sensor('other', 'CPU Package', 'Temperature', 71, owner='/intelcpu/0'))
        self.assertIsNone(native.map_sensors(self.payload, {}, 100100)['cpu_temp_c'])
        self.assertEqual(native.map_sensors(self.payload, {'cpu_hardware_id':'/intelcpu/0'}, 100100)['cpu_temp_c'], 71)

    def test_gpu_fallback_does_not_mix_different_cards(self):
        self.payload['sensors'].extend([
            sensor('igpu', 'GPU Core', 'Temperature', 40, 'GpuAmd', '/gpu-amd/0'),
            sensor('dgpu', 'GPU Core', 'Temperature', 62, 'GpuNvidia', '/gpu-nvidia/0')])
        self.assertNotIn('gpu_temp_c', native.map_sensors(self.payload, {}, 100100))
        self.assertEqual(native.map_sensors(self.payload, {'native_gpu_hardware_id':'/gpu-amd/0'}, 100100)['gpu_temp_c'], 40)

    def test_native_backend_never_starts_vendor_log_reader(self):
        with patch.object(collector, 'CONFIG', {'sensor_backend':'native'}), patch.object(collector, 'native_loop') as run, \
             patch.object(collector, 'vendor_loop') as vendor:
            collector.sensor_loop()
            run.assert_called_once()
            vendor.assert_not_called()

    def test_explicit_legacy_backend_remains_available(self):
        with patch.object(collector, 'CONFIG', {'sensor_backend':'kanali'}), patch.object(collector, 'native_loop') as run, \
             patch.object(collector, 'vendor_loop') as vendor:
            collector.sensor_loop()
            vendor.assert_called_once()
            run.assert_not_called()

    def test_transient_snapshot_sharing_failure_keeps_only_fresh_cache(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(native, 'locations', return_value=(Path(directory)/'sensors.json',Path(directory)/'lease','TEST')):
            reader = native.NativeSensors()
            with patch.object(reader, 'read', side_effect=[self.payload,{},{}]), \
                 patch.object(native,'tick_ms',side_effect=[100000,101000,106000]), \
                 patch.object(native.subprocess,'run') as run:
                self.assertEqual(reader.poll(),self.payload)
                self.assertEqual(reader.poll(),self.payload)
                self.assertEqual(reader.poll(),{})
                run.assert_called_once()


if __name__ == '__main__': unittest.main()
