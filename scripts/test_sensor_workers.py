"""Test hardware-worker isolation on Windows without opening devices or a driver."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.name != 'nt':
        raise RuntimeError('This test uses the Windows .NET Framework runtime.')
    payload = ROOT / 'build/native/payload'
    if not (payload / 'LibreHardwareMonitorLib.dll').exists():
        raise RuntimeError('Run scripts/prepare_native.py first.')
    compiler = Path(os.environ['SystemRoot']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    with tempfile.TemporaryDirectory(prefix='worker-test-', dir=ROOT / 'build') as temporary:
        directory = Path(temporary)
        for library in payload.glob('*.dll'):
            shutil.copy2(library, directory / library.name)
        executable = directory / 'SensorWorkerTests.exe'
        shutil.copy2(ROOT / 'sensors/SensorHost.exe.config', str(executable) + '.config')
        subprocess.run([str(compiler), '/nologo', '/target:exe', '/platform:x64',
                        '/main:SensorWorkerTests', '/reference:System.Web.Extensions.dll',
                        '/reference:' + str(payload / 'LibreHardwareMonitorLib.dll'),
                        '/out:' + str(executable), str(ROOT / 'sensors/SensorHost.cs'),
                        str(ROOT / 'tests/SensorWorkerTests.cs')], check=True)
        subprocess.run([str(executable)], check=True, timeout=15)


if __name__ == '__main__':
    main()
