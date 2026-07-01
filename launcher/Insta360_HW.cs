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
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class Program
{
    private const string MutexName = "Global\\Insta360_HW.exe";
    private const string PlatformUrl = "http://127.0.0.1:8765";

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

        bool createdNew;
        using (var mutex = new Mutex(true, MutexName, out createdNew))
        {
            if (!createdNew)
            {
                WriteLog("Existing instance detected; opening platform URL.");
                OpenPlatformUrl();
                return 0;
            }

            try
            {
                WriteLog("Launcher started. root=" + root);
                EnsureFirstRunReady(root, installScript, readyMarker);
            }
            catch (Exception ex)
            {
                WriteLog("First-run readiness failed: " + ex);
                // First-run readiness is best-effort: never block the user from the
                // platform if optional setup (e.g. Cadence deploy) fails. The launch
                // step below will surface real errors via its health check.
            }

            try
            {
                EnsureCadenceLoaderReady(root, redeployScript);
            }
            catch (Exception ex)
            {
                WriteLog("Cadence loader repair failed: " + ex);
                // Cadence integration repair is best-effort. The platform still
                // opens so System Status can show diagnostics and repair actions.
            }

            int exitCode = RunPowerShellHidden(root, launchScript, string.Join(" ", QuoteArgs(args)));
            if (exitCode != 0)
            {
                string message = "Insta360_HW 启动失败，错误码：" + exitCode + "\n\n日志：" + LogPath();
                WriteLog(message);
                MessageBox.Show(message, "Insta360_HW", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            return exitCode;
        }
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
        if (!File.Exists(script))
        {
            WriteLog("Missing script: " + script);
            return 2;
        }
        var psi = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments =
                "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\" " + extraArgs,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        using (var proc = Process.Start(psi))
        {
            if (proc == null) return 1;
            var output = new StringBuilder();
            var error = new StringBuilder();
            proc.OutputDataReceived += (sender, e) =>
            {
                if (e.Data != null) output.AppendLine(e.Data);
            };
            proc.ErrorDataReceived += (sender, e) =>
            {
                if (e.Data != null) error.AppendLine(e.Data);
            };
            proc.BeginOutputReadLine();
            proc.BeginErrorReadLine();
            proc.WaitForExit();
            string outputText = output.ToString();
            string errorText = error.ToString();
            if (!string.IsNullOrWhiteSpace(outputText))
            {
                WriteLog("[stdout] " + outputText.Trim());
            }
            if (!string.IsNullOrWhiteSpace(errorText))
            {
                WriteLog("[stderr] " + errorText.Trim());
            }
            WriteLog("PowerShell exited " + proc.ExitCode + ": " + script);
            return proc.ExitCode;
        }
    }

    private static void OpenPlatformUrl()
    {
        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = PlatformUrl,
                UseShellExecute = true,
            });
        }
        catch (Exception ex)
        {
            WriteLog("OpenPlatformUrl failed: " + ex);
        }
    }

    private static string LogPath()
    {
        string dir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Insta360_HW");
        return Path.Combine(dir, "launcher.log");
    }

    private static void WriteLog(string message)
    {
        try
        {
            string path = LogPath();
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            File.AppendAllText(path, DateTime.Now.ToString("s") + " " + message + Environment.NewLine, Encoding.UTF8);
        }
        catch
        {
            // Logging must never prevent the platform from opening.
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
