"""Optional per-user Windows shortcuts and serialized lifecycle actions."""
import contextlib
import os
from pathlib import Path
import subprocess
import sys
import time

from settings import ROOT, RUNTIME, FLAGS


def powershell(script, *arguments, timeout=20):
    executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return subprocess.run([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass',
                           '-File',str(ROOT/'scripts'/script),*arguments],capture_output=True,text=True,
                          encoding='utf-8',errors='replace',creationflags=FLAGS,timeout=timeout)


def manage_shortcuts(mode):
    if os.name!='nt': raise RuntimeError('Windows shortcuts require Windows.')
    pythonw=Path(sys.executable).with_name('pythonw.exe').resolve()
    if not pythonw.is_file(): raise FileNotFoundError('pythonw.exe is required; install the standard Windows Python distribution.')
    result=powershell('shortcuts.ps1','-Mode',mode,'-PythonPath',str(pythonw))
    if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def autostart_enabled():
    if os.name!='nt': return False
    try: return manage_shortcuts('Query')=='enabled'
    except (OSError,RuntimeError,subprocess.SubprocessError): return False


def ensure_kanali():
    # Only reuse an existing vendor task whose target is an installed KANALI.exe.
    # Never register a privileged task or request elevation.
    try:
        result=powershell('start_kanali.ps1',timeout=12)
        if result.returncode:
            RUNTIME.mkdir(exist_ok=True)
            (RUNTIME/'kanali-startup.log').write_text('KANALI could not be started automatically. Open KANALI or enable its own startup option.',encoding='utf-8')
    except (OSError,subprocess.SubprocessError): pass


@contextlib.contextmanager
def action_lock(timeout=100):
    import msvcrt
    RUNTIME.mkdir(exist_ok=True)
    with (RUNTIME/'launcher.lock').open('a+b') as stream:
        if stream.seek(0,2)==0: stream.write(b'0'); stream.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1); break
            except OSError:
                if time.monotonic()>=deadline: raise RuntimeError('Another dashboard action is still running.')
                time.sleep(.2)
        try: yield
        finally:
            stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
