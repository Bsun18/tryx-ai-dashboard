"""Desktop controller. Closing this window leaves the dashboard running."""
import ctypes
import hashlib
import queue
import sys
import threading
import tkinter as tk
from tkinter import messagebox
import launcher

TITLE = 'TRYX AI Dashboard 控制台'
BG, CARD, FG, MUTED, CYAN = '#080f14', '#14212b', '#ecf4f7', '#a4b4bf', '#48d9ed'


class ControlPanel:
    def __init__(self, root):
        self.root, self.events = root, queue.Queue()
        self.busy = self.refreshing = False
        root.title(TITLE)
        root.geometry('530x370')
        root.resizable(False, False)
        root.configure(bg=BG)
        root.iconbitmap(str(launcher.ROOT/'assets/dashboard.ico'))
        font = ('Microsoft YaHei UI', 11)
        tk.Label(root, text='AI TELEMETRY', bg=BG, fg=CYAN, font=('Segoe UI', 11, 'bold')).pack(anchor='w', padx=26, pady=(22, 8))
        self.state = tk.StringVar(value='正在读取状态…')
        tk.Label(root, textvariable=self.state, bg=BG, fg=FG, font=('Microsoft YaHei UI', 21, 'bold')).pack(anchor='w', padx=25)
        self.detail = tk.StringVar(value='')
        tk.Label(root, textvariable=self.detail, bg=BG, fg=MUTED, font=font, wraplength=475, justify='left').pack(anchor='w', padx=26, pady=(6, 20))
        buttons = tk.Frame(root, bg=BG); buttons.pack(fill='x', padx=26)
        self.start = tk.Button(buttons, text='启动仪表盘', command=lambda:self.run('start'), font=font,
                               bg=CYAN, fg=BG, activebackground='#7ce5f3', relief='flat', padx=22, pady=11)
        self.start.pack(side='left', expand=True, fill='x', padx=(0, 8))
        self.stop = tk.Button(buttons, text='关闭 · 返回原画面', command=lambda:self.run('stop'), font=font,
                              bg=CARD, fg=FG, activebackground='#253b49', activeforeground=FG, relief='flat', padx=12, pady=11)
        self.stop.pack(side='left', expand=True, fill='x')
        self.auto = tk.BooleanVar(value=launcher.autostart_enabled())
        self.check = tk.Checkbutton(root, text='登录 Windows 后自动启动', variable=self.auto, command=self.toggle_auto,
                                    bg=BG, fg=FG, selectcolor=CARD, activebackground=BG, activeforeground=FG, font=font)
        self.check.pack(anchor='w', padx=23, pady=(19, 8))
        self.note = tk.StringVar(value='关闭此窗口不影响仪表盘。桌面“TRYX 仪表盘开关”可直接切换。')
        tk.Label(root, textvariable=self.note, bg=BG, fg=MUTED, font=('Microsoft YaHei UI', 9),
                 wraplength=475, justify='left').pack(anchor='w', padx=26, pady=(6, 0))
        root.update_idletasks()
        root.geometry('{}x{}'.format(max(530, root.winfo_reqwidth()), max(370, root.winfo_reqheight()+24)))
        root.after(100, self.pump)
        root.after(100, self.refresh)

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.start, self.stop, self.check]: widget.configure(state='disabled' if busy else 'normal')

    def run(self, command):
        if self.busy: return
        self.set_busy(True); self.note.set('正在处理，请稍候…')
        def worker():
            try: self.events.put(('done', launcher.perform(command)))
            except Exception as error: self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=False).start()

    def toggle_auto(self):
        if self.busy: return
        desired = self.auto.get()
        self.set_busy(True)
        def worker():
            try:
                launcher.manage_shortcuts('Enable' if desired else 'Disable')
                self.events.put(('auto', desired))
            except Exception as error: self.events.put(('error', str(error)))
        threading.Thread(target=worker, daemon=False).start()

    def refresh(self):
        if not self.refreshing:
            self.refreshing = True
            def worker():
                try: self.events.put(('state', launcher.status()))
                except Exception as error: self.events.put(('state_error', str(error)))
            threading.Thread(target=worker, daemon=True).start()
        self.root.after(3000, self.refresh)

    def pump(self):
        while not self.events.empty():
            kind, value = self.events.get_nowait()
            if kind == 'state':
                self.refreshing = False
                self.state.set('仪表盘运行中' if value['live'] else '等待屏幕连接' if value['running'] else '仪表盘已关闭')
                self.detail.set(('USB 已连接 · 实时数据正常' if value['cpu_temp_c'] is not None else '实时数据正常 · 等待 KANALI 温度数据')
                                if value['live'] else 'USB 连接恢复后会自动显示。' if value['running'] else '当前显示 KANALI 原画面。')
                if not self.busy: self.auto.set(value['autostart'])
            elif kind == 'state_error': self.refreshing = False
            else:
                self.set_busy(False)
                if kind == 'error':
                    self.auto.set(launcher.autostart_enabled())
                    self.note.set('操作未完成，请查看错误信息。')
                    messagebox.showerror(TITLE, value, parent=self.root)
                elif kind == 'auto': self.note.set('已启用：下次登录自动启动。' if value else '已取消自启动；当前运行状态不变。')
                elif value == 'waiting': self.note.set('采集器已启动，正在后台等待 USB 屏幕连接。')
                else: self.note.set('已启动。关闭本窗口可继续运行。' if value == 'running' else '已关闭。本次登录期间不会自行重新启动。')
        self.root.after(100, self.pump)


def main():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    key = hashlib.sha256(str(launcher.ROOT).encode()).hexdigest()[:16]
    handle = kernel.CreateMutexW(None, False, 'Local\\AI-Telemetry-Control-'+key)
    if not handle: raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        user = ctypes.WinDLL('user32')
        user.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]; user.FindWindowW.restype = ctypes.c_void_p
        user.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        window = user.FindWindowW(None, TITLE)
        if window: user.ShowWindow(window, 9); user.SetForegroundWindow(window)
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]; kernel.CloseHandle(handle)
        return
    try:
        root = tk.Tk(); panel = ControlPanel(root)
        if '--self-test' in sys.argv:
            root.update_idletasks()
            for widget in root.winfo_children():
                assert widget.winfo_y()+widget.winfo_height() <= root.winfo_height(), 'Control clipped vertically'
                assert widget.winfo_x()+widget.winfo_width() <= root.winfo_width(), 'Control clipped horizontally'
            root.after(800, root.destroy)
        root.mainloop()
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]; kernel.CloseHandle(handle)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        launcher.RUNTIME.mkdir(exist_ok=True)
        (launcher.RUNTIME/'control-error.log').write_text(str(error), encoding='utf-8')
        raise
