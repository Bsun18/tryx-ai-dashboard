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
        connect_screen(load_config())
        RUNTIME.mkdir(exist_ok=True)
        (RUNTIME/'renderer.log').write_text('', encoding='utf-8')
        executable = Path(sys.executable).with_name('pythonw.exe')
        if not executable.exists(): executable = Path(sys.executable)
        with (RUNTIME/'collector.log').open('w', encoding='utf-8') as log:
            subprocess.Popen([str(executable), str(ROOT/'collector.py')], cwd=ROOT, stdin=subprocess.DEVNULL,
                             stdout=log, stderr=subprocess.STDOUT, creationflags=FLAGS | subprocess.CREATE_NEW_PROCESS_GROUP)
    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        time.sleep(.5)
        owned = current()
        data = metrics()
        if owned and data.get('collector_pid') == owned.pid and data.get('sample_age_s', 999) is not None and data.get('sample_age_s', 999) < 4:
            log = RUNTIME/'renderer.log'
            if log.exists() and 'AI_TELEMETRY_PORTABLE_SURFACE_READY' in log.read_text(encoding='utf-8', errors='replace'):
                print('Dashboard running. Live data is updating on the cooler screen.')
                return
    raise RuntimeError('Startup was not confirmed. See runtime/collector.log and runtime/renderer.log.')


def stop_dashboard():
    process = current()
    if not process:
        print('No collector owned by this installation is running.')
        return
    connection_path = RUNTIME/'connection.json'
    connection = json.loads(connection_path.read_text(encoding='utf-8')) if connection_path.exists() else {}
    children = process.children(recursive=True)
    process.terminate()
    for child in children:
        try: child.terminate()
        except psutil.Error: pass
    psutil.wait_procs([process] + children, timeout=5)
    serial = connection.get('serial')
    if serial:
        executable = find_adb(load_config())
        result = run_adb(executable, '-s', serial, 'shell', 'pidof', 'ai-telemetry')
        for value in result.stdout.split():
            if not value.isdigit(): continue
            identity = run_adb(executable, '-s', serial, 'shell', 'cat', '/proc/'+value+'/cmdline').stdout
            if identity.split('\x00')[0] == 'ai-telemetry':
                run_adb(executable, '-s', serial, 'shell', 'kill', '-TERM', value)
        run_adb(executable, '-s', serial, 'reverse', '--remove', 'tcp:'+str(PORT))
    print('Dashboard stopped. The original KANALI display is visible when USB is connected.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['configure', 'start', 'stop', 'status'], nargs='?', default='start')
    args = parser.parse_args()
    if os.name != 'nt': raise RuntimeError('The collector requires Windows 10/11.')
    if args.command == 'configure': configure()
    elif args.command == 'start': start()
    elif args.command == 'stop': stop_dashboard()
    else:
        process = current()
        data = metrics()
        owned = bool(process and data.get('collector_pid') == process.pid)
        print(json.dumps({'running': owned, 'sample_age_s': data.get('sample_age_s') if owned else None}, indent=2))


if __name__ == '__main__':
    try: main()
    except Exception as error:
        RUNTIME.mkdir(exist_ok=True)
        (RUNTIME/'launcher-error.log').write_text(str(error), encoding='utf-8')
        print(str(error)); sys.exit(1)
