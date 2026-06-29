// Insta360_HW launcher — thin shell that locates the platform root (its own
// directory), runs first-run readiness once, then launches the suite.
//
// It deliberately keeps NO business logic: Python discovery, port selection,
// service start and browser open all live in launch_tool_suite.ps1, which is
// already exercised by the test suite. This exe only:
//   1. Finds its sibling scripts next to itself.
//   2. On first run, runs oneclick_install.ps1 -Silent (install openpyxl, deploy
//      the Cadence loader, init config) and writes a .ready marker.
//   3. On every run, repairs the Cadence loader if it was removed or the real
//      Capture HOME differs from the installer assumption.
//   4. On every run, runs launch_tool_suite.ps1 hidden, forwarding CLI args so
//      Cadence menu deep-links (Source/Name/-Restart) keep working.
//
// Built with: csc.exe /target:winexe /win32icon:<icon> /out:Insta360_HW.exe
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        // The exe sits at the platform root, scripts are siblings.
        string exeDir = AppDomain.CurrentDomain.BaseDirectory;
        // Normalize: when launched from another CWD, BaseDirectory is still the
        // exe folder, which is exactly the platform root.
        string root = exeDir.TrimEnd('\\', '/');

        string installScript = Path.Combine(root, "oneclick_install.ps1");
        string redeployScript = Path.Combine(root, "scripts", "redeploy_cadence_loader.ps1");
        string launchScript = Path.Combine(root, "launch_tool_suite.ps1");
        string readyMarker = Path.Combine(root, "data", ".ready");

        try
        {
            EnsureFirstRunReady(root, installScript, readyMarker);
        }
        catch
        {
            // First-run readiness is best-effort: never block the user from the
            // platform if optional setup (e.g. Cadence deploy) fails. The launch
            // step below will surface real errors via its health check.
        }

        try
        {
            EnsureCadenceLoaderReady(root, redeployScript);
        }
        catch
        {
            // Cadence integration repair is best-effort. The platform still
            // opens so System Status can show diagnostics and repair actions.
        }

        return RunPowerShellHidden(root, launchScript, string.Join(" ", QuoteArgs(args)));
    }

    private static void EnsureFirstRunReady(string root, string installScript, string readyMarker)
    {
        if (File.Exists(readyMarker)) return;
        if (!File.Exists(installScript)) return;

        // Only trigger first-run readiness once per machine to avoid looping on
        // a setup that keeps failing. The marker is written even on partial
        // success so the user always reaches the platform.
        RunPowerShellHidden(root, installScript, "-Silent");
        try
        {
            Directory.CreateDirectory(Path.Combine(root, "data"));
            File.WriteAllText(readyMarker, DateTime.Now.ToString("s") + "\n");
        }
        catch
        {
            // Marker is a convenience, not a requirement.
        }
    }

    private static void EnsureCadenceLoaderReady(string root, string redeployScript)
    {
        if (!File.Exists(redeployScript)) return;
        RunPowerShellHidden(root, redeployScript, "");
    }

    private static int RunPowerShellHidden(string workingDir, string script, string extraArgs)
    {
        var psi = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments =
                "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" " + extraArgs,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
            CreateNoWindow = true,
        };
        using (var proc = Process.Start(psi))
        {
            if (proc == null) return 1;
            proc.WaitForExit();
            return proc.ExitCode;
        }
    }

    // Quote each CLI arg for PowerShell so paths/spaces survive forwarding.
    private static string[] QuoteArgs(string[] args)
    {
        var quoted = new string[args.Length];
        for (int i = 0; i < args.Length; i++)
        {
            string a = args[i];
            quoted[i] = a.Contains(" ") || a.Contains("\"")
                ? "\"" + a.Replace("\"", "`\"") + "\""
                : a;
        }
        return quoted;
    }
}
