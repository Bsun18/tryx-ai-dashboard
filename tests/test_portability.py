import json
from pathlib import Path
from types import SimpleNamespace as NS
import tempfile
import unittest
from unittest.mock import patch

import collector
import launcher
import settings
from telemetry_math import counter_rate, pcie_peak_mb_s, select_disk, short_label, storage_limits


class Calculations(unittest.TestCase):
    def test_pcie_is_single_direction_and_encoding_adjusted(self):
        self.assertAlmostEqual(pcie_peak_mb_s(4, 4), 7876.923076923077)
        self.assertAlmostEqual(pcie_peak_mb_s(5, 16), 63015.38461538462)
        self.assertEqual(pcie_peak_mb_s(2, 8), 4000)

    def test_unknown_capacity_is_not_guessed(self):
        for gen, width in [(None, 4), (6, 4), (4, None), (4, 0)]:
            self.assertIsNone(pcie_peak_mb_s(gen, width))

    def test_counter_rate_and_reset(self):
        old = {'disk': NS(read_bytes=1000000)}
        new = {'disk': NS(read_bytes=4000000)}
        self.assertEqual(counter_rate(new, old, 'disk', 'read_bytes', 2), 1.5)
        self.assertIsNone(counter_rate(old, new, 'disk', 'read_bytes', 1))
        for dt in [0, -1, float('nan')]:
            self.assertIsNone(counter_rate(new, old, 'disk', 'read_bytes', dt))
        self.assertIsNone(counter_rate(new, {}, 'disk', 'read_bytes', 1))

    def test_storage_selection_does_not_assume_disk_zero(self):
        disks = [dict(index=0, bus='USB', system=False), dict(index=2, bus='SATA', system=True),
                 dict(index=5, bus='NVMe', system=False), dict(index=7, bus='NVMe', system=True)]
        self.assertEqual(select_disk(disks)['index'], 7)
        self.assertEqual(select_disk(disks, 2)['index'], 2)
        self.assertIsNone(select_disk(disks, 99))
        self.assertIsNone(select_disk(disks[:1]))

    def test_capacity_from_other_computer(self):
        disk = dict(bus='NVMe', max_gen=3, max_width=2)
        read, write, basis = storage_limits(disk, {})
        self.assertAlmostEqual(read, 1969.2307692307693)
        self.assertEqual(read, write)
        self.assertEqual(basis, 'LINK')

    def test_external_and_sata_do_not_inherit_controller_peak(self):
        for bus in ['USB', 'SATA', 'SCSI']:
            self.assertEqual(storage_limits(dict(bus=bus, max_gen=4, max_width=4), {}), (None, None, 'UNKNOWN'))

    def test_partial_manual_reference_leaves_other_direction_unknown(self):
        self.assertEqual(storage_limits(dict(bus='NVMe', max_gen=4, max_width=4),
                                       {'storage_read_peak_mb_s': 3000}), (3000, None, 'REF'))
        self.assertEqual(storage_limits(None, {'storage_read_peak_mb_s': 3000}), (None, None, 'UNKNOWN'))

    def test_labels_clean_and_bound_arbitrary_hardware(self):
        self.assertEqual(short_label('AMD Ryzen 9 9950X 16-Core Processor '), 'Ryzen 9 9950X')
        self.assertEqual(short_label('NVIDIA GeForce RTX 4090'), 'RTX 4090')
        self.assertEqual(short_label('Intel(R) Core(TM) Ultra 9'), 'Intel Core Ultra 9')
        self.assertEqual(len(short_label('Long device name ' * 10)), 26)


class Configuration(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'config.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            return settings.load_config(path)

    def test_default_has_no_machine_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            config = settings.load_config(Path(directory)/'missing.json')
        self.assertEqual(config, settings.DEFAULTS)
        for key in ['device_serial', 'disk_index', 'network_interface', 'gpu_label', 'cpu_label']:
            self.assertIsNone(config[key])

    def test_overrides(self):
        config = self.load({'disk_index': 4, 'gpu_index': 1, 'network_interface': 'LAN 2'})
        self.assertEqual(config['disk_index'], 4)
        self.assertEqual(config['gpu_index'], 1)

    def test_bad_configuration_rejected(self):
        for value in [{'disk_index': -1}, {'gpu_index': True}, {'gpu_index': None},
                      {'storage_read_peak_mb_s': 0}, {'storage_write_peak_mb_s': float('inf')},
                      {'unknown': 1}, {'device_serial': '\n'}, []]:
            with self.subTest(value=value), self.assertRaises(ValueError): self.load(value)

    def test_device_discovery_ignores_phones_offline_and_unauthorized(self):
        devices = settings.parse_devices('List of devices attached\nPHONE device model:Pixel\n'
            'EXAMPLE_A device product:test model:cm01_se transport_id:2\n'
            'EXAMPLE_B unauthorized model:cm01_se\nEXAMPLE_C offline model:cm01_se\n')
        self.assertEqual(settings.choose_screen(devices)['serial'], 'EXAMPLE_A')

    def test_multiple_screens_require_local_selection(self):
        devices = [dict(serial='EXAMPLE_A', model='cm01_se'), dict(serial='EXAMPLE_B', model='cm01_se')]
        with self.assertRaises(RuntimeError): settings.choose_screen(devices)
        self.assertEqual(settings.choose_screen(devices, 'EXAMPLE_B')['serial'], 'EXAMPLE_B')
        with self.assertRaises(RuntimeError): settings.choose_screen(devices, 'ABSENT')

    def test_explicit_phone_is_still_rejected_by_hardware_validation(self):
        results = [NS(returncode=0, stdout='PHONE device model:Pixel', stderr=''),
                   NS(stdout='Pixel'), NS(stdout='Physical size: 2240x1080')]
        with patch.object(settings, 'find_adb', return_value='adb'), patch.object(settings, 'run_adb', side_effect=results):
            with self.assertRaises(RuntimeError): settings.connect_screen({'device_serial': 'PHONE'})


class CollectorPortability(unittest.TestCase):
    def test_network_prefers_active_default_physical_interface(self):
        stats = {'LAN': NS(isup=True, speed=1000), 'Wi-Fi': NS(isup=True, speed=2400),
                 'VPN': NS(isup=True, speed=10000)}
        with patch.object(collector, 'CONFIG', {}), patch.object(collector, 'INVENTORY',
                {'physical_interfaces': ['LAN', 'Wi-Fi'], 'default_interface': 'LAN'}):
            self.assertEqual(collector.choose_network(stats), 'LAN')

    def test_selected_offline_network_is_not_silently_replaced(self):
        with patch.object(collector, 'CONFIG', {'network_interface': 'LAN'}):
            self.assertIsNone(collector.choose_network({'LAN': NS(isup=False, speed=1000), 'Wi-Fi': NS(isup=True, speed=600)}))

    def test_other_pc_and_non_nvidia_partial_metrics(self):
        disk = dict(index=7, model='Example NVMe', bus='NVMe', max_gen=3, max_width=2)
        inventory = dict(cpu='Intel(R) Core(TM) Ultra 9', gpus=['AMD Radeon Example'],
                         physical_interfaces=['LAN 2'], default_interface='LAN 2')
        drives = {'PhysicalDrive7': NS(read_bytes=100, write_bytes=200)}
        net = {'LAN 2': NS(bytes_recv=100, bytes_sent=100)}
        with patch.object(collector, 'CONFIG', dict(settings.DEFAULTS, sensor_backend='kanali')), \
             patch.object(collector, 'INVENTORY', inventory), patch.object(collector, 'SELECTED_DISK', disk), \
             patch.object(collector, 'Nvidia', side_effect=RuntimeError('test: unavailable')), \
             patch.object(collector, 'vendor_time', 99), patch.object(collector, 'time') as timing, \
             patch.object(collector, 'vendor', {'cpu': {'temperature': 55}, 'gpu': {'load': 17}}), \
             patch.object(collector, 'stop') as stopped, patch.object(collector, 'psutil') as system:
            timing.monotonic.return_value = 100
            stopped.wait.side_effect = [False, True]
            system.cpu_percent.return_value = 25
            system.virtual_memory.return_value = NS(total=32*2**30, available=24*2**30, percent=25)
            system.disk_io_counters.return_value = drives
            system.net_io_counters.return_value = net
            system.net_if_stats.return_value = {'LAN 2': NS(isup=True, speed=2500)}
            # Sampling time must advance for valid counter deltas.
            timing.monotonic.side_effect = [100, 101, 101]
            collector.sampler()
            result = collector.snapshot
        self.assertEqual(result['cpu_label'], 'Intel Core Ultra 9')
        self.assertEqual(result['gpu_label'], 'AMD Radeon Example')
        self.assertEqual(result['gpu_util'], 17)
        self.assertNotIn('pcie_rx_mb_s', result)
        self.assertNotIn('vram_total_gib', result)
        self.assertEqual(result['nvme_counter'], 'PhysicalDrive7')
        self.assertAlmostEqual(result['nvme_read_peak_mb_s'], 1969.2307692307693)
        self.assertEqual(result['net_link_mbps'], 2500)

    def test_stop_without_owned_process_does_not_touch_adb(self):
        with patch.object(launcher, 'current', return_value=None), patch.object(launcher, 'run_adb') as adb:
            launcher.stop_dashboard()
            adb.assert_not_called()

    def test_start_refuses_port_owned_by_another_installation(self):
        with patch.object(launcher, 'current', return_value=None), patch.object(launcher, 'port_in_use', return_value=True), \
             patch.object(launcher, 'connect_screen') as connect:
            with self.assertRaises(RuntimeError): launcher.start()
            connect.assert_not_called()


if __name__ == '__main__': unittest.main()
