using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

// Use the explicitly Unicode shell interface. WScript.Shell's shortcut saving
// can lose non-ASCII filenames when Windows uses a different system code page.
[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
class ShellLinkObject { }

[ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IShellLinkUnicode {
    void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int count, IntPtr data, uint flags);
    void GetIDList(out IntPtr item);
    void SetIDList(IntPtr item);
    void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int count);
    void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string value);
    void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int count);
    void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string value);
    void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int count);
    void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string value);
    void GetHotkey(out short value);
    void SetHotkey(short value);
    void GetShowCmd(out int value);
    void SetShowCmd(int value);
    void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder value, int count, out int index);
    void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string value, int index);
    void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string value, uint reserved);
    void Resolve(IntPtr window, uint flags);
    void SetPath([MarshalAs(UnmanagedType.LPWStr)] string value);
}

public class DashboardShortcutInfo {
    public string TargetPath;
    public string Arguments;
}

public static class DashboardShortcut {
    public static DashboardShortcutInfo Read(string filename) {
        var link = (IShellLinkUnicode)new ShellLinkObject();
        try {
            ((IPersistFile)link).Load(filename, 0);
            var path = new StringBuilder(32768);
            var args = new StringBuilder(32768);
            link.GetPath(path, path.Capacity, IntPtr.Zero, 4);
            link.GetArguments(args, args.Capacity);
            return new DashboardShortcutInfo { TargetPath = path.ToString(), Arguments = args.ToString() };
        } finally { Marshal.FinalReleaseComObject(link); }
    }
    public static void Save(string filename, string target, string arguments, string directory, string description, string icon) {
        var link = (IShellLinkUnicode)new ShellLinkObject();
        try {
            link.SetPath(target);
            link.SetArguments(arguments);
            link.SetWorkingDirectory(directory);
            link.SetDescription(description);
            link.SetShowCmd(7);
            link.SetIconLocation(icon, 0);
            ((IPersistFile)link).Save(filename, true);
        } finally { Marshal.FinalReleaseComObject(link); }
    }
}
