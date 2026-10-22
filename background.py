"""Start the collector through a least-privilege, on-demand Windows task."""
from pathlib import Path
import os
import subprocess
import sys
import time


def manage_task(root, mode='Start'):
    root = Path(root)
    pythonw = Path(sys.executable).with_name('pythonw.exe').resolve()
    shell = Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result = subprocess.run([str(shell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
        '-File', str(root/'scripts'/'background-task.ps1'), '-Root', str(root), '-PythonPath', str(pythonw), '-Mode', mode],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    if result.returncode:
        raise RuntimeError('Independent background startup failed: '+(result.stderr.strip() or result.stdout.strip()))
    return result.stdout.strip()


def launch(root, current):
    manage_task(root)
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        process = current()
        if process: return process
        time.sleep(.2)
    # A broken venv redirector can remain alive without ever running Python.
    # Stop only this directory's validated task, so a retry can recover.
    manage_task(root, 'Stop')
    raise RuntimeError('Background task did not start the collector. See collector.log / background-error.log.')


def run_collector():
    root = Path(__file__).resolve().parent
    runtime = root/'runtime' if (root/'settings.py').is_file() else root
    runtime.mkdir(exist_ok=True)
    try:
        with (runtime/'collector.log').open('w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, str(root/'collector.py')], cwd=root,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW)
            return process.wait()
    except Exception as error:
        (runtime/'background-error.log').write_text(str(error), encoding='utf-8')
        return 1


if __name__ == '__main__':
    sys.exit(run_collector())
