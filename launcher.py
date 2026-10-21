"""Configure, start, inspect, or stop this checkout's background dashboard."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import psutil
from settings import ROOT, RUNTIME, PORT, FLAGS, connect_screen, find_adb, load_config, run_adb, windows_inventory
from telemetry_math import select_disk, storage_limits
from windows_integration import action_lock, autostart_enabled, ensure_kanali, manage_shortcuts


def current():
    try:
        process = psutil.Process(int((RUNTIME/'collector.pid').read_text()))
        if any(Path(a).resolve() == ROOT/'collector.py' for a in process.cmdline()[1:] if a.endswith('collector.py')):
            return process
    except (OSError, ValueError, psutil.Error): pass
    return None


def metrics():
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/metrics', timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError): return {}


def port_in_use():
    try:
        with socket.create_connection(('127.0.0.1', PORT), timeout=1): return True
    except OSError: return False


def configure():
    config = load_config()
    adb, serial = connect_screen(config)
    inventory = windows_inventory()
    disk = select_disk(inventory.get('disks', []), config.get('disk_index'))
    peaks = storage_limits(disk, config)
    RUNTIME.mkdir(exist_ok=True)
    (RUNTIME/'hardware.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    if not (ROOT/'config.json').exists():
        (ROOT/'config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Compatible cm01_se screen found (2240 x 1080).')
    print('CPU:', inventory.get('cpu', 'unknown'))
    print('GPU:', ', '.join(inventory.get('gpus', [])) or 'unknown')
    print('Storage:', disk.get('model') if disk else 'unknown')
    print('Storage reference:', peaks[2], peaks[0], '/', peaks[1], 'MB/s')
    print('Physical network interfaces:', ', '.join(inventory.get('physical_interfaces', [])))
    print('Automatic configuration is ready. No display changes were made.')


def start():
    process = current()
    if not process:
        if port_in_use():
            raise RuntimeError(f'Port {PORT} is already in use. Stop the other dashboard installation before starting this one.')
        if not (ROOT/'renderer'/'renderer.jar').is_file():
            raise FileNotFoundError('renderer/renderer.jar missing. Run scripts/build_renderer.py or download a complete release.')
        RUNTIME.mkdir(exist_ok=True)
        (RUNTIME/'renderer.log').write_text('', encoding='utf-8')
        for name in ['connection.json','usb-status.json']:
            (RUNTIME/name).unlink(missing_ok=True)
        executable = Path(sys.executable).with_name('pythonw.exe')
        if not executable.exists(): executable = Path(sys.executable)
        with (RUNTIME/'collector.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([str(executable), str(ROOT/'collector.py')], cwd=ROOT, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT, creationflags=FLAGS | subprocess.CREATE_NEW_PROCESS_GROUP)
        (RUNTIME/'collector.pid').write_text(str(process.pid),encoding='ascii')
    ensure_kanali()
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        time.sleep(.5)
        owned = current()
        data = metrics()
        if owned and data.get('collector_pid') == owned.pid and data.get('sample_age_s', 999) is not None and data.get('sample_age_s', 999) < 4:
            log = RUNTIME/'renderer.log'
            if log.exists() and 'AI_TELEMETRY_PORTABLE_SURFACE_READY' in log.read_text(encoding='utf-8', errors='replace'):
                return 'running'
        if not current(): raise RuntimeError('Collector exited. See runtime/collector.log.')
        # Fresh host data with no screen is a valid waiting state. The collector
        # keeps discovering the USB device, even after this launcher exits.
        if owned and data.get('collector_pid') == owned.pid and not (RUNTIME/'connection.json').exists():
            return 'waiting'
    if current(): return 'waiting'
    raise RuntimeError('Startup failed. See runtime/collector.log.')


def stop_dashboard():
    process = current()
    if not process:
        return 'stopped'
    connection_path = RUNTIME/'connection.json'
    connection = json.loads(connection_path.read_text(encoding='utf-8')) if connection_path.exists() else {}
    children = process.children(recursive=True)
    process.terminate()
    for child in children:
        try: child.terminate()
        except psutil.Error: pass
    _, alive = psutil.wait_procs([process] + children, timeout=5)
    for child in alive:
        try: child.kill()
        except psutil.Error: pass
    serial = connection.get('serial')
    if serial:
        try:
            executable = find_adb(load_config())
            result = run_adb(executable, '-s', serial, 'shell', 'pidof', 'ai-telemetry')
            for value in result.stdout.split():
                if not value.isdigit(): continue
                identity = run_adb(executable, '-s', serial, 'shell', 'cat', '/proc/'+value+'/cmdline').stdout
                if identity.split('\x00')[0] == 'ai-telemetry':
                    run_adb(executable, '-s', serial, 'shell', 'kill', '-TERM', value)
            run_adb(executable, '-s', serial, 'reverse', '--remove', 'tcp:'+str(PORT))
        except (OSError,subprocess.SubprocessError): pass
    return 'stopped'


def status():
    process=current()
    data=metrics() if process else {}
    owned=bool(process and data.get('collector_pid')==process.pid)
    age=data.get('sample_age_s') if owned else None
    screen=False
    if owned:
        try:
            connection=json.loads((RUNTIME/'connection.json').read_text(encoding='utf-8'))
            screen=bool(run_adb(find_adb(load_config()),'-s',connection['serial'],'shell','pidof','ai-telemetry',timeout=3).stdout.strip())
        except (OSError,ValueError,KeyError,subprocess.SubprocessError): pass
    return {'running':bool(process),'live':bool(owned and screen and isinstance(age,(int,float)) and age<4),
            'screen':screen,'sample_age_s':age,'cpu_temp_c':data.get('cpu_temp_c') if owned else None,
            'autostart':autostart_enabled()}


def perform(command):
    with action_lock():
        if command=='toggle': command='stop' if current() else 'start'
        return stop_dashboard() if command=='stop' else start()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['configure','start','stop','toggle','autostart','status','install-shortcuts','enable-autostart','disable-autostart'], nargs='?', default='start')
    args = parser.parse_args()
    if os.name != 'nt': raise RuntimeError('The collector requires Windows 10/11.')
    if args.command == 'configure': configure()
    elif args.command in {'start','stop','toggle','autostart'}:
        result=perform(args.command)
        if sys.stdout: print(result)
    elif args.command=='status':
        if sys.stdout: print(json.dumps(status(),indent=2))
    else:
        result=manage_shortcuts({'install-shortcuts':'Install','enable-autostart':'Enable','disable-autostart':'Disable'}[args.command])
        if sys.stdout: print(result)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        RUNTIME.mkdir(exist_ok=True)
        (RUNTIME/'launcher-error.log').write_text(str(error), encoding='utf-8')
        if sys.stdout: print(str(error))
        sys.exit(1)
