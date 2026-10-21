"""Local configuration, ADB discovery and compatible-screen selection."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
RUNTIME = ROOT / 'runtime'
PORT = 18765
FLAGS = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
DEFAULTS = {'device_serial': None, 'adb_path': None, 'gpu_index': 0, 'disk_index': None,
            'network_interface': None, 'gpu_label': None, 'cpu_label': None, 'storage_label': None,
            'storage_read_peak_mb_s': None, 'storage_write_peak_mb_s': None}


def load_config(path=None):
    path = Path(path) if path is not None else ROOT / 'config.json'
    supplied = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(supplied, dict):
        raise ValueError('config.json must contain a JSON object')
    unknown = set(supplied) - set(DEFAULTS)
    if unknown:
        raise ValueError('Unknown configuration keys: ' + ', '.join(sorted(unknown)))
    result = dict(DEFAULTS, **supplied)
    for key, value in result.items():
        if value is None:
            if key == 'gpu_index': raise ValueError('gpu_index must be an integer')
            continue
        if key in {'gpu_index', 'disk_index'}:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(key + ' must be a nonnegative integer')
        elif key.endswith('_mb_s'):
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                raise ValueError(key + ' must be a positive number or null')
        elif not isinstance(value, str) or not value.strip() or any(c in value for c in '\r\n\x00'):
            raise ValueError(key + ' must be a nonempty string or null')
    return result


def run_adb(adb, *args, timeout=12):
    return subprocess.run([str(adb), *args], capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=timeout, creationflags=FLAGS)


def find_adb(config):
    explicit = config.get('adb_path')
    candidates = [Path(os.path.expandvars(explicit))] if explicit else [
        ROOT/'tools'/'platform-tools'/'adb.exe', ROOT/'tools'/'adb.exe', RUNTIME/'adb'/'adb.exe']
    if not explicit:
        found = shutil.which('adb')
        if found: candidates.append(Path(found))
        for variable in ['ANDROID_HOME', 'ANDROID_SDK_ROOT']:
            if os.environ.get(variable): candidates.append(Path(os.environ[variable])/'platform-tools'/'adb.exe')
    for candidate in candidates:
        if candidate.is_file():
            try:
                if run_adb(candidate, 'version', timeout=5).returncode == 0:
                    return str(candidate.resolve())
            except (OSError, subprocess.SubprocessError): pass
    # KANALI is already installed by the screen owner. Copy its local ADB runtime;
    # no vendor executable or DLL is distributed in this repository or release.
    if not explicit:
        for variable in ['ProgramFiles', 'ProgramFiles(x86)']:
            base = Path(os.environ.get(variable, 'C:/Program Files'))/'KANALI'
            files = [base/'bin'/'adb.exe', base/'AdbWinApi.dll', base/'AdbWinUsbApi.dll']
            if all(p.is_file() for p in files):
                target = RUNTIME/'adb'; target.mkdir(parents=True, exist_ok=True)
                for source in files: shutil.copy2(source, target/source.name)
                if run_adb(target/'adb.exe', 'version', timeout=5).returncode == 0:
                    return str(target/'adb.exe')
    raise FileNotFoundError('ADB not found. Install KANALI, add platform-tools to PATH, or set adb_path in config.json.')


def parse_devices(output):
    found = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[1] != 'device': continue
        tags = dict(f.split(':', 1) for f in fields[2:] if ':' in f)
        found.append({'serial': fields[0], 'model': tags.get('model', '')})
    return found


def choose_screen(devices, serial=None):
    candidates = [d for d in devices if d['serial'] == serial] if serial else [d for d in devices if d['model'].casefold() == 'cm01_se']
    if len(candidates) != 1:
        raise RuntimeError('Exactly one compatible PANORAMA SE screen is required. Check KANALI/USB; for multiple screens set device_serial locally.')
    return candidates[0]


def connect_screen(config):
    adb = find_adb(config)
    result = run_adb(adb, 'devices', '-l')
    if result.returncode: raise RuntimeError(result.stderr.strip() or 'ADB device discovery failed')
    selected = choose_screen(parse_devices(result.stdout), config.get('device_serial'))
    serial = selected['serial']
    model = run_adb(adb, '-s', serial, 'shell', 'getprop', 'ro.product.model').stdout.strip()
    size = run_adb(adb, '-s', serial, 'shell', 'wm', 'size').stdout
    dimensions = re.findall(r'(\d+)x(\d+)', size)
    if model.casefold() != 'cm01_se' or not dimensions or tuple(map(int, dimensions[-1])) != (2240, 1080):
        raise RuntimeError('This release supports cm01_se at 2240 x 1080 only; no display changes were made.')
    return adb, serial


def windows_inventory():
    shell = Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
    result = subprocess.run([str(shell), '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(ROOT/'scripts'/'inventory.ps1')], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=45, creationflags=FLAGS, check=True)
    return json.loads(result.stdout.lstrip('\ufeff'))
