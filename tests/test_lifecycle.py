import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch

import collector
import diagnose_screen
import launcher
import windows_integration
import background


class Lifecycle(unittest.TestCase):
    def test_failed_background_start_stops_its_hung_task_before_retry(self):
        with patch.object(background,'manage_task') as task, \
             patch.object(background.time,'monotonic',side_effect=[0,16]):
            with self.assertRaisesRegex(RuntimeError,'did not start'):
                background.launch(Path('example'),lambda:None)
            self.assertEqual(task.call_args_list[-1].args,(Path('example'),'Stop'))

    def test_status_uses_only_fresh_owned_usb_report_without_starting_adb(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(launcher,'RUNTIME',Path(directory)), \
             patch.object(launcher,'current',return_value=NS(pid=100)), \
             patch.object(launcher,'metrics',return_value={'collector_pid':100,'sample_age_s':0}), \
             patch.object(launcher,'autostart_enabled',return_value=False), \
             patch.object(launcher.time,'monotonic',return_value=100), patch.object(launcher,'run_adb') as adb:
            for pid, checked, expected in [(100,99,True),(101,99,False),(100,60,False),(100,101,False)]:
                (Path(directory)/'usb-status.json').write_text(json.dumps(
                    {'collector_pid':pid,'checked_at':checked,'screen':True}),encoding='utf-8')
                self.assertEqual(launcher.status()['live'],expected)
            adb.assert_not_called()

    def test_failed_daemon_start_does_not_run_short_usb_commands(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collector,'RUNTIME',Path(directory)), \
             patch.object(collector,'ADB_BASE',['adb','-s','EXAMPLE']), patch.object(collector,'processes',[]), \
             patch.object(collector,'adb',return_value=NS(returncode=1,stderr='service not ready')) as adb, \
             patch.object(collector,'stop') as stopped:
            stopped.is_set.side_effect=[False,True]
            collector.usb_loop()
            adb.assert_called_once_with('start-server',timeout=30)
            self.assertFalse(json.loads((Path(directory)/'usb-status.json').read_text())['connected'])

    def test_usb_discovery_retries_then_starts_only_validated_target(self):
        commands=[]
        def fake_adb(*args, **kwargs):
            commands.append(args)
            return NS(returncode=0,stdout='device' if args==('get-state',) else '')
        process=MagicMock(); process.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory, patch.object(collector,'RUNTIME',Path(directory)), \
             patch.object(collector,'ADB_BASE',[]), patch.object(collector,'processes',[]), \
             patch.object(collector,'connect_screen',side_effect=[RuntimeError('USB not ready'),('adb','EXAMPLE')]) as connect, \
             patch.object(collector,'adb',side_effect=fake_adb), patch.object(collector.subprocess,'Popen',return_value=process), \
             patch.object(collector,'stop') as stopped:
            stopped.is_set.side_effect=[False,False,True]
            collector.usb_loop()
            self.assertEqual(connect.call_count,2)
            self.assertEqual(json.loads((Path(directory)/'connection.json').read_text())['serial'],'EXAMPLE')
            self.assertTrue(json.loads((Path(directory)/'usb-status.json').read_text())['connected'])
        self.assertEqual(sum(command[0]=='push' for command in commands),1)

    def test_unsupported_device_never_receives_upload_or_reverse(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(collector,'RUNTIME',Path(directory)), \
             patch.object(collector,'ADB_BASE',[]), patch.object(collector,'processes',[]), \
             patch.object(collector,'connect_screen',side_effect=RuntimeError('Unsupported screen')), \
             patch.object(collector,'adb') as adb, patch.object(collector,'stop') as stopped:
            stopped.is_set.side_effect=[False,True]
            collector.usb_loop()
            adb.assert_not_called()
            self.assertFalse(json.loads((Path(directory)/'usb-status.json').read_text())['connected'])

    def test_vendor_reader_waits_without_using_untargeted_adb(self):
        with patch.object(collector,'ADB_BASE',[]), patch.object(collector,'stop') as stopped, \
             patch.object(collector.subprocess,'Popen') as spawn:
            stopped.is_set.side_effect=[False,True]
            collector.vendor_loop()
            spawn.assert_not_called()

    def test_status_does_not_adopt_another_collectors_metrics(self):
        with patch.object(launcher,'current',return_value=NS(pid=100)), \
             patch.object(launcher,'metrics',return_value={'collector_pid':101,'sample_age_s':0,'cpu_temp_c':60}), \
             patch.object(launcher,'autostart_enabled',return_value=False), patch.object(launcher,'run_adb') as adb:
            result=launcher.status()
            self.assertFalse(result['live'])
            self.assertIsNone(result['cpu_temp_c'])
            adb.assert_not_called()

    def test_diagnostic_report_is_read_only_and_has_no_serial(self):
        commands=[]
        def run(*args, **kwargs):
            commands.append(args)
            if args[1:]==('devices','-l'): output='PRIVATE_SERIAL device model:cm01_se'
            elif args[-2:]==('wm','size'): output='Physical size: 2240x1080'
            else: output={'ro.product.model':'cm01_se','ro.product.manufacturer':'Example',
                          'ro.build.version.release':'11','ro.build.version.sdk':'30'}[args[-1]]
            return NS(returncode=0,stdout=output)
        with patch.object(diagnose_screen,'find_adb',return_value='adb'), patch.object(diagnose_screen,'run_adb',side_effect=run):
            report=diagnose_screen.inspect_screens({})
        self.assertNotIn('PRIVATE_SERIAL',json.dumps(report))
        self.assertTrue(report['devices'][0]['matches_current_profile'])
        self.assertTrue(all('push' not in cmd and 'reverse' not in cmd and 'kill' not in cmd for cmd in commands))

    @unittest.skipUnless(os.name=='nt','Windows file lock')
    def test_actions_are_serialized(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(windows_integration,'RUNTIME',Path(directory)):
            with windows_integration.action_lock():
                with self.assertRaises(RuntimeError):
                    with windows_integration.action_lock(timeout=0): pass
            with windows_integration.action_lock(timeout=0): pass

    @unittest.skipUnless(os.name=='nt','Windows COM shortcuts')
    def test_shortcuts_use_this_installation_without_changing_real_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            desktop=Path(directory)/'Desktop-\u684c\u9762'; startup=Path(directory)/'Startup-\u542f\u52a8'
            desktop.mkdir(); startup.mkdir()
            pythonw=Path(sys.executable).with_name('pythonw.exe')
            def manage(mode):
                result=windows_integration.powershell('shortcuts.ps1','-Mode',mode,'-PythonPath',str(pythonw),
                    '-DesktopDirectory',str(desktop),'-StartupDirectory',str(startup))
                self.assertEqual(result.returncode,0,result.stderr)
                return result.stdout.strip()
            manage('Install')
            self.assertEqual(len(list(desktop.glob('*.lnk'))),2)
            self.assertEqual(manage('Query'),'disabled')
            manage('Enable'); self.assertEqual(manage('Query'),'enabled')
            foreign=windows_integration.powershell('shortcuts.ps1','-Mode','Enable','-PythonPath',str(Path(directory)/'other-pythonw.exe'),
                '-DesktopDirectory',str(desktop),'-StartupDirectory',str(startup))
            self.assertNotEqual(foreign.returncode,0)
            self.assertEqual(manage('Query'),'enabled')
            manage('Disable'); self.assertEqual(manage('Query'),'disabled')
            self.assertEqual(len(list(desktop.glob('*.lnk'))),2)


if __name__=='__main__': unittest.main()
