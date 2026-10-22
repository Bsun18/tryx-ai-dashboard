"""Read-only PC telemetry, delivered only on loopback and the cooler USB tunnel."""
import ctypes as C
import datetime as dt
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

import psutil
from settings import ROOT, RUNTIME, PORT, FLAGS, load_config, connect_screen, windows_inventory
from telemetry_math import pcie_peak_mb_s, counter_rate, select_disk, short_label, storage_limits
from native_sensors import native_loop, map_sensors, tick_ms

CONFIG = load_config()
ADB_BASE = []
INVENTORY = {}
SELECTED_DISK = None
stop = threading.Event()
lock = threading.Lock()
snapshot = {}
sampled_at = 0.0
vendor = {}
vendor_time = 0.0
native_payload = {}
processes = []
STREAM_ID = uuid.uuid4().hex


def publish_native(payload):
    global native_payload
    native_payload = payload


def sensor_loop():
    if CONFIG['sensor_backend'] == 'kanali': vendor_loop()
    else: native_loop(stop, publish_native)

def prepare():
    global INVENTORY, SELECTED_DISK
    try:
        INVENTORY = windows_inventory()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print('Windows inventory unavailable:', type(error).__name__, flush=True)
        INVENTORY = {}
    SELECTED_DISK = select_disk(INVENTORY.get('disks', []), CONFIG.get('disk_index'))
    RUNTIME.mkdir(exist_ok=True)
    (RUNTIME/'hardware.json').write_text(json.dumps(INVENTORY, ensure_ascii=False, indent=2), encoding='utf-8')

def adb(*args, timeout=12):
    return subprocess.run(ADB_BASE+list(args), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, creationflags=FLAGS)

class Memory(C.Structure):
    _fields_ = [('total',C.c_ulonglong),('free',C.c_ulonglong),('used',C.c_ulonglong)]
class Util(C.Structure):
    _fields_ = [('gpu',C.c_uint),('memory',C.c_uint)]

class Nvidia:
    def __init__(self, index=0):
        self.lib=C.WinDLL('nvml.dll')
        self.call('nvmlInit_v2',[],[])
        self.handle=C.c_void_p()
        self.call('nvmlDeviceGetHandleByIndex_v2',[C.c_uint,C.POINTER(C.c_void_p)],[index,C.byref(self.handle)])
        name = C.create_string_buffer(128)
        try:
            self.call('nvmlDeviceGetName',[C.c_void_p,C.c_void_p,C.c_uint],[self.handle,name,len(name)])
            self.name = name.value.decode('utf-8',errors='replace')
        except (RuntimeError,AttributeError): self.name = 'NVIDIA GPU'
        self.max_gen = self.value('nvmlDeviceGetMaxPcieLinkGeneration')
        self.max_width = self.value('nvmlDeviceGetMaxPcieLinkWidth')
        self.peak = pcie_peak_mb_s(self.max_gen, self.max_width)
    def call(self,name,types,args):
        f=getattr(self.lib,name);f.argtypes=types;f.restype=C.c_int
        rc=f(*args)
        if rc: raise RuntimeError('%s returned %s'%(name,rc))
    def value(self,name,*selectors):
        out=C.c_uint()
        try:
            self.call(name,[C.c_void_p]+[C.c_uint]*len(selectors)+[C.POINTER(C.c_uint)],[self.handle,*selectors,C.byref(out)])
            return out.value
        except (RuntimeError,AttributeError): return None
    def sample(self):
        result={'gpu_label':short_label(CONFIG.get('gpu_label') or self.name),'gpu_source':'NVML','pcie_peak_mb_s':self.peak,'pcie_max_gen':self.max_gen,'pcie_max_width':self.max_width}
        memory=Memory();util=Util()
        try:
            self.call('nvmlDeviceGetMemoryInfo',[C.c_void_p,C.POINTER(Memory)],[self.handle,C.byref(memory)])
            result.update(vram_total_gib=memory.total/2**30,vram_used_gib=memory.used/2**30)
        except RuntimeError: pass
        try:
            self.call('nvmlDeviceGetUtilizationRates',[C.c_void_p,C.POINTER(Util)],[self.handle,C.byref(util)])
            result.update(gpu_util=util.gpu,gpu_mem_util=util.memory)
        except RuntimeError: pass
        for key,name,selectors,divisor in [
            ('gpu_temp_c','nvmlDeviceGetTemperature',[0],1),
            ('gpu_power_w','nvmlDeviceGetPowerUsage',[],1000),
            ('gpu_power_limit_w','nvmlDeviceGetPowerManagementLimit',[],1000),
            ('gpu_clock_mhz','nvmlDeviceGetClockInfo',[0],1),
            ('pcie_rx_mb_s','nvmlDeviceGetPcieThroughput',[1],1000),
            ('pcie_tx_mb_s','nvmlDeviceGetPcieThroughput',[0],1000)]:
            value=self.value(name,*selectors)
            result[key]=None if value is None else value/divisor
        gen=self.value('nvmlDeviceGetCurrPcieLinkGeneration');width=self.value('nvmlDeviceGetCurrPcieLinkWidth')
        result['pcie_link']='GEN%s x%s'%(gen or '--',width or '--')
        return result

def vendor_loop():
    """Observe the vendor's sensor messages; no driver or cooler writes."""
    global vendor,vendor_time
    while not stop.is_set():
        p=None
        try:
            if not ADB_BASE:
                stop.wait(3)
                continue
            p=subprocess.Popen(ADB_BASE+['logcat','-T','1','-v','raw','DataConvert:D','SerialMsgReceiverHandler:D','*:S'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,encoding='utf-8',errors='replace',creationflags=FLAGS)
            processes.append(p)
            for line in p.stdout:
                if stop.is_set(): break
                index=line.find('{')
                if index<0 or '"cpu"' not in line: continue
                try:
                    entry=json.loads(line[index:].strip())
                    if 'cpu' in entry:
                        vendor=entry;vendor_time=time.monotonic()
                except (ValueError,TypeError): pass
        except OSError: pass
        finally:
            if p:
                if p.poll() is None:p.terminate()
                if p in processes:processes.remove(p)
        stop.wait(3)

def choose_network(stats=None):
    stats = stats if stats is not None else psutil.net_if_stats()
    preferred = CONFIG.get('network_interface')
    if preferred:
        return preferred if preferred in stats and stats[preferred].isup else None
    physical = INVENTORY.get('physical_interfaces', [])
    candidates = []
    for name, stat in stats.items():
        lower = name.lower()
        if not stat.isup: continue
        if physical and name not in physical: continue
        if not physical and any(x in lower for x in ('loopback','vethernet','virtual','wsl','vpn','tap','tun')): continue
        candidates.append((stat.speed, name))
    route = INVENTORY.get('default_interface')
    if route and any(name == route for _, name in candidates): return route
    return sorted(candidates, reverse=True)[0][1] if candidates else None

def sampler():
    global snapshot,sampled_at
    gpu=None
    try:gpu=Nvidia(CONFIG['gpu_index'])
    except Exception as e:print('NVIDIA unavailable:',e,flush=True)
    disk = SELECTED_DISK
    nvme = 'PhysicalDrive'+str(disk['index']) if disk else None
    peak_read, peak_write, peak_basis = storage_limits(disk, CONFIG)
    storage_label = short_label(CONFIG.get('storage_label') or (disk or {}).get('model', '—'), 20)
    cpu_label = short_label(CONFIG.get('cpu_label') or INVENTORY.get('cpu', 'CPU'))
    gpus = INVENTORY.get('gpus', [])
    fallback_gpu_label = short_label(CONFIG.get('gpu_label') or (gpus[0] if len(gpus)==1 else 'GPU'))
    psutil.cpu_percent(None)
    prev_disks=psutil.disk_io_counters(perdisk=True,nowrap=False)
    prev_net=psutil.net_io_counters(pernic=True,nowrap=False)
    then=time.monotonic();seq=0
    while not stop.wait(float(CONFIG.get('sample_interval_s', 1))):
        now=time.monotonic();elapsed=now-then
        try:
            mem=psutil.virtual_memory();disks=psutil.disk_io_counters(perdisk=True,nowrap=False);net=psutil.net_io_counters(pernic=True,nowrap=False)
            record={'app':'AI-Telemetry','schema_version':3,'collector_pid':os.getpid(),'cpu_label':cpu_label,'gpu_label':fallback_gpu_label,'stream_id':STREAM_ID,'seq':seq,'sample_monotonic_s':now,'clock':dt.datetime.now().astimezone().strftime('%H:%M:%S'),'cpu_util':psutil.cpu_percent(None),
                    'ram_total_gib':mem.total/2**30,'ram_used_gib':(mem.total-mem.available)/2**30,'ram_util':mem.percent}
            if gpu: record.update(gpu.sample())
            for key,field in [('disk_read_mb_s','read_bytes'),('disk_write_mb_s','write_bytes')]:
                values=[max(0,getattr(counter,field)-getattr(prev_disks[name],field)) for name,counter in disks.items() if name in prev_disks]
                record[key]=sum(values)/elapsed/1e6 if values else None
            record['nvme_counter'] = nvme
            record['nvme_label'] = storage_label if nvme in disks else '—'
            for key,field in [('nvme_read_mb_s','read_bytes'),('nvme_write_mb_s','write_bytes')]:
                record[key]=counter_rate(disks,prev_disks,nvme,field,elapsed)
            record['nvme_read_peak_mb_s']=peak_read if nvme in disks else None
            record['nvme_write_peak_mb_s']=peak_write if nvme in disks else None
            record['storage_peak_basis']=peak_basis
            record['storage_title']='NVMe / SSD' if str((disk or {}).get('bus','')).upper()=='NVME' else 'DISK / I/O'
            stats=psutil.net_if_stats()
            name=choose_network(stats);record['network_interface']=name
            record['network_name']='ETHERNET' if name and ('以太' in name or 'ethernet' in name.lower()) else ('WLAN' if name and ('wlan' in name.lower() or 'wi-fi' in name.lower()) else 'ACTIVE NIC')
            record['net_link_mbps']=stats[name].speed if name in stats and stats[name].isup and stats[name].speed>0 else None
            for key,field in [('net_rx_mb_s','bytes_recv'),('net_tx_mb_s','bytes_sent')]:
                record[key]=counter_rate(net,prev_net,name,field,elapsed)
            if CONFIG['sensor_backend'] == 'native':
                readings = map_sensors(native_payload, CONFIG, tick_ms())
                if gpu:
                    readings = {k:v for k,v in readings.items() if not k.startswith('gpu_')}
                elif 'gpu_label' in readings:
                    readings['gpu_label'] = short_label(CONFIG.get('gpu_label') or readings['gpu_label'])
                record.update(readings)
            elif vendor_time and now-vendor_time<5:
                record['cpu_source'] = 'KANALI'
                record['vendor_age_s'] = max(0, round(now-vendor_time,2))
                cpu=vendor.get('cpu',{});fans=vendor.get('fans',[])
                record.update(cpu_temp_c=cpu.get('temperature'),cpu_power_w=cpu.get('power'))
                if gpu is None:
                    vendor_gpu=vendor.get('gpu',{})
                    record.update(gpu_source='KANALI',gpu_util=vendor_gpu.get('load'),gpu_temp_c=vendor_gpu.get('temperature'),gpu_power_w=vendor_gpu.get('power'),gpu_clock_mhz=vendor_gpu.get('speed'))
                record['fan_rpm']=next((f.get('value') for f in fans if f.get('name')=='CPU'),None)
            else:record.update(cpu_temp_c=None,cpu_power_w=None,fan_rpm=None)
            with lock:snapshot=record;sampled_at=time.monotonic()
            seq+=1;then=now;prev_disks=disks;prev_net=net
        except Exception as e:
            print('Sample failed:',type(e).__name__,str(e),flush=True)
            # Keep counters and their original timestamp paired after a failed sample.

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/metrics':self.send_error(404);return
        with lock:
            payload=dict(snapshot);payload['sample_age_s']=round(time.monotonic()-sampled_at,3) if sampled_at else None
        raw=json.dumps(payload,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
    def log_message(self,*args):pass

def usb_loop():
    global ADB_BASE
    renderer=None
    claimed=False
    while not stop.is_set():
        try:
            if not ADB_BASE:
                executable, serial = connect_screen(CONFIG)
                ADB_BASE = [executable, '-s', serial]
                (RUNTIME/'connection.json').write_text(json.dumps({'serial':serial}),encoding='utf-8')
            ready=adb('start-server',timeout=30)
            if ready.returncode: raise RuntimeError(ready.stderr.strip() or 'USB service startup failed')
            state=adb('get-state',timeout=5)
            if state.returncode==0 and state.stdout.strip()=='device':
                # The loopback port is exclusively owned by this collector. Clear
                # a renderer orphaned by an earlier collector crash or upgrade.
                if not claimed:
                    for pid in adb('shell','pidof','ai-telemetry').stdout.split():
                        if not pid.isdigit(): continue
                        identity=adb('shell','cat','/proc/'+pid+'/cmdline').stdout
                        if identity.split('\x00')[0]=='ai-telemetry':
                            adb('shell','kill','-TERM',pid)
                    claimed=True
                adb('reverse','tcp:'+str(PORT),'tcp:'+str(PORT))
                present=adb('shell','pidof','ai-telemetry',timeout=5)
                if not present.stdout.strip():
                    transfer=adb('push',str(ROOT/'renderer'/'renderer.jar'),'/data/local/tmp/ai-telemetry.jar')
                    if transfer.returncode==0:
                        with (RUNTIME/'renderer.log').open('w',encoding='utf-8') as log:
                            renderer=subprocess.Popen(ADB_BASE+['shell','CLASSPATH=/data/local/tmp/ai-telemetry.jar app_process / --nice-name=ai-telemetry local.aimonitor.dashboard.ScreenRenderer 0 '+str(max(1,min(100,int(CONFIG.get('screen_brightness_percent',80)))))],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=FLAGS)
                        processes.append(renderer)
                screen=bool(adb('shell','pidof','ai-telemetry',timeout=5).stdout.strip())
                (RUNTIME/'usb-status.json').write_text(json.dumps({'connected':True,'screen':screen,
                    'collector_pid':os.getpid(),'checked_at':time.monotonic(),'message':''}),encoding='utf-8')
            else:
                (RUNTIME/'usb-status.json').write_text(json.dumps({'connected':False,'message':'Waiting for the selected USB screen.'}),encoding='utf-8')
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
            (RUNTIME/'usb-status.json').write_text(json.dumps({'connected':False,'message':str(error)}),encoding='utf-8')
        for p in list(processes):
            if p.poll() is not None:processes.remove(p)
        stop.wait(8)

def main():
    server=http.server.ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    RUNTIME.mkdir(exist_ok=True)
    pid=RUNTIME/'collector.pid';pid.write_text(str(os.getpid()))
    prepare()
    for target in [sampler,sensor_loop,usb_loop]:threading.Thread(target=target,daemon=True).start()
    print('AI Telemetry: USB device linked; loopback port',PORT,flush=True)
    try:server.serve_forever(poll_interval=.5)
    except KeyboardInterrupt:pass
    finally:
        stop.set();server.server_close()
        for p in processes:
            if p.poll() is None:p.terminate()
        if pid.exists() and pid.read_text()==str(os.getpid()):pid.unlink()

if __name__=='__main__':main()
