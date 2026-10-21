using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;

internal static class SensorWorkerTests
{
    public static int Main()
    {
        var stop = new ManualResetEvent(false);
        var release = new ManualResetEvent(false);
        var entered = new ManualResetEvent(false);
        var fast = new SensorHost.SensorWorker("Cpu", stop,
            delegate(List<object> values, List<string> errors) { values.Add("fresh CPU"); });
        var slow = new SensorHost.SensorWorker("GpuNvidia", stop,
            delegate(List<object> values, List<string> errors) { entered.Set(); release.WaitOne(); values.Add("GPU"); });
        fast.Start(); slow.Start();
        try
        {
            if (!entered.WaitOne(2000)) throw new Exception("Slow reader did not start");
            var watch = Stopwatch.StartNew();
            List<object> values;
            do {
                values = new List<object>();
                var errors = new List<string>(); var timings = new List<object>();
                fast.Append(SensorHost.GetTickCount64(), values, errors, timings);
                slow.Append(SensorHost.GetTickCount64(), values, errors, timings);
                if (values.Contains("fresh CPU")) break;
                Thread.Sleep(10);
            } while (watch.ElapsedMilliseconds < 2000);
            if (!values.Contains("fresh CPU") || values.Contains("GPU"))
                throw new Exception("Blocked GPU prevented fresh CPU data");
            values.Clear();
            fast.Append(SensorHost.GetTickCount64() + 6000, values, new List<string>(), new List<object>());
            if (values.Count != 0) throw new Exception("Expired worker sample was reused");
            stop.Set();
            if (!fast.Join(1000)) throw new Exception("Fast worker did not stop");
            if (slow.Join(50)) throw new Exception("Blocked worker test did not block");
            Console.WriteLine("PASS: blocked device isolation, stale samples, bounded shutdown");
            return 0;
        }
        finally { stop.Set(); release.Set(); fast.Join(2000); slow.Join(2000); }
    }
}
