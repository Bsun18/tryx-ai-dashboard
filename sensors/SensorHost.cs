// Read-only sensor host. No fan controls, shell commands, or user-selected DLLs.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Threading;
using System.Web.Script.Serialization;
using LibreHardwareMonitor.Hardware;

internal static class SensorHost
{
    [DllImport("kernel32.dll")] internal static extern ulong GetTickCount64();
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern bool SetDllDirectory(string directory);
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer();
    private static readonly string Sid = WindowsIdentity.GetCurrent().User.Value;
    private static readonly string OutputDirectory = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "TryxAiDashboard", Sid);
    private static readonly string Lease = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".tryx-ai-dashboard", "sensors.lease");

    private static ulong ReadConsumerTick()
    {
        try
        {
            var info = new FileInfo(Lease);
            if (!info.Exists || info.Length > 40) return 0;
            ulong tick;
            if (!ulong.TryParse(File.ReadAllText(Lease).Trim(), out tick)) return 0;
            ulong now = GetTickCount64();
            return tick <= now ? tick : 0;
        }
        catch (IOException) { return 0; }
        catch (UnauthorizedAccessException) { return 0; }
    }

    // LHM 0.9.6 exposes no public package-only refresh API. This adapter is
    // restricted to its pinned AMD implementation and verified member shape.
    // Other CPU implementations retain the ordinary Update path.
    private static bool UpdateRequiredSensors(IHardware hardware)
    {
        Type type = hardware.GetType();
        if (type.FullName != "LibreHardwareMonitor.Hardware.Cpu.Amd17Cpu" ||
            type.Assembly.GetName().Version != new Version(0, 9, 6, 0))
        {
            hardware.Update();
            return false;
        }
        var field = type.GetField("_processor", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic);
        if (field == null) throw new MissingFieldException(type.FullName, "_processor");
        object processor = field.GetValue(hardware);
        var update = processor.GetType().GetMethod("UpdateSensors", Type.EmptyTypes);
        if (update == null || update.ReturnType != typeof(void)) throw new MissingMethodException("AMD package UpdateSensors");
        update.Invoke(processor, null);
        return true;
    }

    private static void Read(IHardware hardware, List<object> sensors, List<string> errors)
    {
        try
        {
            ulong sampled = GetTickCount64();
            bool packageOnly = UpdateRequiredSensors(hardware);
            foreach (ISensor sensor in hardware.Sensors)
            {
                if (sensor.SensorType != SensorType.Temperature && sensor.SensorType != SensorType.Power &&
                    sensor.SensorType != SensorType.Fan && sensor.SensorType != SensorType.Load &&
                    sensor.SensorType != SensorType.Clock) continue;
                // Do not export stale per-core load, clocks or power left from initialization.
                if (packageOnly && sensor.SensorType != SensorType.Temperature &&
                    !(sensor.SensorType == SensorType.Power && sensor.Name == "Package")) continue;
                float? value = sensor.Value;
                if (value.HasValue && (float.IsNaN(value.Value) || float.IsInfinity(value.Value))) value = null;
                sensors.Add(new { id = sensor.Identifier.ToString(), name = sensor.Name,
                    type = sensor.SensorType.ToString(), value = value, sample_tick_ms = sampled,
                    hardware_id = hardware.Identifier.ToString(), hardware_name = hardware.Name,
                    hardware_type = hardware.HardwareType.ToString() });
            }
        }
        catch (Exception error) { errors.Add(hardware.HardwareType + ": " + error.GetType().Name); }
        foreach (IHardware child in hardware.SubHardware) Read(child, sensors, errors);
    }

    // Each top-level device owns one worker; no concurrent calls into the same device.
    internal sealed class SensorWorker
    {
        private readonly object gate = new object();
        private readonly ManualResetEvent stop;
        private readonly Action<List<object>, List<string>> read;
        private readonly Thread thread;
        private List<object> sensors = new List<object>();
        private List<string> errors = new List<string>();
        private ulong sampled, elapsed;
        internal readonly string Kind;
        internal SensorWorker(string kind, ManualResetEvent stopEvent, Action<List<object>, List<string>> reader)
        {
            Kind = kind; stop = stopEvent; read = reader;
            thread = new Thread(Loop) { IsBackground = true, Name = "Sensors " + kind };
        }
        internal void Start() { thread.Start(); }
        internal bool Join(int timeout) { return thread.Join(timeout); }
        private void Loop()
        {
            while (!stop.WaitOne(0))
            {
                ulong began = GetTickCount64();
                var values = new List<object>(); var failures = new List<string>();
                try { read(values, failures); }
                catch (Exception error) { failures.Add(Kind + ": " + error.GetType().Name); }
                lock (gate) { sensors = values; errors = failures; sampled = began; elapsed = GetTickCount64() - began; }
                if (stop.WaitOne(1000)) break;
            }
        }
        internal void Append(ulong now, List<object> values, List<string> failures, List<object> timings)
        {
            lock (gate)
            {
                bool fresh = sampled > 0 && now >= sampled && now - sampled < 5000;
                if (fresh) values.AddRange(sensors);
                failures.AddRange(errors);
                timings.Add(new { hardware = Kind, elapsed_ms = elapsed,
                    sample_age_ms = sampled > 0 && now >= sampled ? (ulong?)(now - sampled) : null, fresh = fresh });
            }
        }
    }

    private static void Save(string name, object value)
    {
        string path = Path.Combine(OutputDirectory, name), temporary = path + ".tmp";
        File.WriteAllText(temporary, Json.Serialize(value), new System.Text.UTF8Encoding(false));
        for (int attempt = 0; ; attempt++)
        {
            try
            {
                if (File.Exists(path)) File.Replace(temporary, path, null);
                else File.Move(temporary, path);
                return;
            }
            catch (IOException)
            {
                // A normal reader may briefly omit FILE_SHARE_DELETE on Windows.
                if (attempt >= 7) throw;
                Thread.Sleep(25);
            }
        }
    }

    public static int Main(string[] args)
    {
        // The installer secures this directory. Never execute code from a writable checkout.
        SetDllDirectory("");
        Directory.SetCurrentDirectory(AppDomain.CurrentDomain.BaseDirectory);
        bool created;
        using (var singleton = new Mutex(true, "Local\\TryxAiDashboardSensors-" + Sid, out created))
        {
            if (!created) return 0;
            var computer = new Computer { IsCpuEnabled = true, IsMotherboardEnabled = true,
                IsGpuEnabled = true, IsMemoryEnabled = false, IsStorageEnabled = false,
                IsNetworkEnabled = false, IsControllerEnabled = false };
            var workers = new List<SensorWorker>();
            var stopWorkers = new ManualResetEvent(false);
            try
            {
                if (!Directory.Exists(OutputDirectory)) return 2;
                if (!LibreHardwareMonitor.PawnIo.PawnIo.IsInstalled)
                    throw new InvalidOperationException("PawnIO is not installed.");
                computer.Open();
                foreach (IHardware hardware in computer.Hardware)
                {
                    IHardware device = hardware;
                    var worker = new SensorWorker(device.HardwareType.ToString(), stopWorkers,
                        delegate(List<object> values, List<string> failures) { Read(device, values, failures); });
                    workers.Add(worker); worker.Start();
                }
                long sequence = 0;
                ulong started = GetTickCount64();
                ulong lastConsumer = 0;
                long skippedWrites = 0;
                while (true)
                {
                    lastConsumer = Math.Max(lastConsumer, ReadConsumerTick());
                    ulong now = GetTickCount64();
                    if (now - started >= 30000 && (lastConsumer == 0 || now - lastConsumer >= 20000)) break;
                    var sensors = new List<object>();
                    var errors = new List<string>();
                    var timings = new List<object>();
                    foreach (SensorWorker worker in workers) worker.Append(GetTickCount64(), sensors, errors, timings);
                    try
                    {
                        Save("sensors.json", new { app = "TRYX-Native-Sensors", schema_version = 1,
                            tick_ms = GetTickCount64(), seq = sequence++, process_id = System.Diagnostics.Process.GetCurrentProcess().Id,
                            source = "LibreHardwareMonitor", library_version = typeof(Computer).Assembly.GetName().Version.ToString(),
                            driver_version = LibreHardwareMonitor.PawnIo.PawnIo.Version.ToString(), sensors = sensors,
                            errors = errors, timings = timings, skipped_writes = skippedWrites, host_version = "0.5.2" });
                    }
                    catch (IOException) { skippedWrites++; }
                    Thread.Sleep(1000);
                }
                return 0;
            }
            catch (Exception error)
            {
                try { Save("sensor-error.json", new { error = error.ToString(), tick_ms = GetTickCount64() }); }
                catch (Exception) { }
                return 1;
            }
            finally
            {
                stopWorkers.Set();
                bool allStopped = true;
                foreach (SensorWorker worker in workers) if (!worker.Join(500)) allStopped = false;
                // Never close hardware under an in-flight driver call. Background workers
                // terminate with the process and Windows releases its driver handles.
                if (allStopped) { computer.Close(); stopWorkers.Dispose(); }
                singleton.ReleaseMutex();
            }
        }
    }
}
