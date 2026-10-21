"""Download verified upstream components and build the small .NET sensor host."""
import hashlib
from pathlib import Path
import os
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build' / 'native'
LHM_URL = 'https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/download/v0.9.6/LibreHardwareMonitor.zip'
LHM_SHA256 = '086d9f1b5a99e643edc2cfaaac16051685b551e4c5ac0b32a57c58c0e529c001'
PAWN_URL = 'https://github.com/namazso/PawnIO.Setup/releases/download/2.2.0/PawnIO_setup.exe'
PAWN_SHA256 = '1f519a22e47187f70a1379a48ca604981c4fcf694f4e65b734aaa74a9fba3032'


def download(url, path, digest):
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        with urllib.request.urlopen(url, timeout=60) as response, path.open('wb') as output:
            shutil.copyfileobj(response, output)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise RuntimeError('Upstream checksum mismatch: ' + path.name)


def main():
    if os.name != 'nt': raise RuntimeError('The sensor host requires Windows.')
    BUILD.mkdir(parents=True, exist_ok=True)
    download(LHM_URL, BUILD/'LibreHardwareMonitor.zip', LHM_SHA256)
    download(PAWN_URL, BUILD/'PawnIO_setup.exe', PAWN_SHA256)
    stage = BUILD/'payload'
    stage.mkdir(exist_ok=True)
    with zipfile.ZipFile(BUILD/'LibreHardwareMonitor.zip') as archive:
        for name in archive.namelist():
            # Only root-level runtime DLLs; the upstream GUI is not installed.
            if '/' not in name and name.endswith('.dll') and not name.startswith(('Aga.', 'OxyPlot', 'Microsoft.Win32.TaskScheduler')):
                (stage/name).write_bytes(archive.read(name))
    shutil.copy2(ROOT/'sensors'/'SensorHost.exe.config', stage/'SensorHost.exe.config')
    compiler = Path(os.environ['SystemRoot'])/'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64', '/optimize+',
                    '/reference:System.Web.Extensions.dll', '/reference:'+str(stage/'LibreHardwareMonitorLib.dll'),
                    '/out:'+str(stage/'SensorHost.exe'), str(ROOT/'sensors'/'SensorHost.cs')], check=True)
    # Retain source and license notices alongside the installed dependencies.
    shutil.copy2(ROOT/'sensors'/'SensorHost.cs', stage/'SensorHost.cs')
    for remote, local in [('LICENSE', 'LibreHardwareMonitor-LICENSE.txt'),
                          ('THIRD-PARTY-NOTICES.txt', 'LibreHardwareMonitor-THIRD-PARTY-NOTICES.txt')]:
        url = 'https://raw.githubusercontent.com/LibreHardwareMonitor/LibreHardwareMonitor/v0.9.6/' + remote
        with urllib.request.urlopen(url, timeout=30) as response:
            (stage/local).write_bytes(response.read())
    import json
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(stage.iterdir()) if p.is_file()}
    (BUILD/'payload-sha256.json').write_text(json.dumps(hashes, indent=2), encoding='utf-8')
    print('Native sensor host prepared. Official LHM 0.9.6 / PawnIO 2.2.0 checksums verified.')


if __name__ == '__main__': main()
