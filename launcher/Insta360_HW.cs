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
using System.Net;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using Microsoft.Win32;

internal static class Program
{
    private const string MutexName = "Global\\Insta360_HW.exe";
    private const string PlatformUrl = "http://127.0.0.1:8765";
    private const string ReconnectProtocolUrl = "insta360-hw://reconnect";
    private const int MAX_LOG_BYTES = 512 * 1024;
    private const int MAX_LOG_FILES = 5;

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
        // The .ready marker lives under %LOCALAPPDATA%\Insta360_HW so read-only
        // install locations (Program Files, network mounts) do not break the
        // first-run gate. Any prior data\.ready copy is ignored.
        string readyMarker = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Insta360_HW", ".ready");
        bool reconnectRequest = IsReconnectRequest(args);
        bool suppressBrowserOpen = reconnectRequest;
        EnsureReconnectProtocolReady();
        try
        {
            Directory.CreateDirectory(Path.GetDirectoryName(readyMarker));
        }
        catch
        {
            // Marker directory is a convenience; failure will surface at write time.
        }

        bool createdNew;
        Mutex mutex = null;
        try
        {
            try
            {
                mutex = new Mutex(true, MutexName, out createdNew);
            }
            catch (AbandonedMutexException ex)
            {
                WriteLog("Recovered abandoned launcher mutex: " + ex.Message);
                createdNew = true;
                mutex = new Mutex(true, MutexName);
            }

            if (!createdNew)
            {
                // The first instance owns the mutex and is either already
                // serving or still coming up. Give it a brief grace period
                // before deciding whether to open a browser tab, since
                // repeated ShellExecute of the same URL can spawn extra tabs
                // on browsers that don't dedupe (e.g. Firefox).
                WriteLog("Second instance detected");
                if (reconnectRequest)
                {
                    WriteLog("Reconnect request detected");
                }
                if (!IsPlatformReady())
                {
                    Thread.Sleep(2000);
                }
                if (suppressBrowserOpen)
                {
                    WriteLog("Skipping browser open for reconnect request");
                }
                else if (!IsPlatformReady())
                {
                    WriteLog("Platform not ready after wait, opening browser as usual");
                    OpenPlatformUrl();
                }
                else
                {
                    WriteLog("Platform already ready, skipping browser open");
                }
                return 0;
            }

            try
            {
                WriteLog("Launcher started. root=" + root);
                if (reconnectRequest)
                {
                    WriteLog("Reconnect request detected");
                }
                if (!File.Exists(readyMarker) && !suppressBrowserOpen)
                {
                    // First-run: open waiting.html (or fall back to a
                    // MessageBox) so the user sees something within a few
                    // seconds while the ~30-60s silent installer runs.
                    OpenWaitingPage(root);
                }
                EnsureFirstRunReady(root, installScript, readyMarker);
            }
            catch (Exception ex)
            {
                ShowStartupFailure("First-run readiness failed", ex);
            }

            try
            {
                EnsureCadenceLoaderReady(root, redeployScript);
            }
            catch (Exception ex)
            {
                ShowStartupFailure("Cadence loader repair failed", ex);
            }

            string launchArgs = BuildLaunchArgs(args, suppressBrowserOpen);
            int exitCode = RunPowerShellHidden(root, launchScript, launchArgs);
            if (exitCode != 0)
            {
                string message =
                    "Insta360_HW startup failed\n\n" +
                    "Exit code: " + exitCode + "\n\n" +
                    "Log: " + LogPath();
                WriteLog(message);
                MessageBox.Show(message, "Insta360_HW", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            return exitCode;
        }
        finally
        {
            if (mutex != null)
            {
                mutex.Dispose();
            }
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
            Directory.CreateDirectory(Path.GetDirectoryName(readyMarker));
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

    private static void OpenWaitingPage(string root)
    {
        try
        {
            string waitFile = Path.Combine(root, "app", "frontend", "waiting.html");
            if (File.Exists(waitFile))
            {
                // file:/// URL so the default browser opens the local page.
                string url = "file:///" + waitFile.Replace('\\', '/');
                Process.Start(new ProcessStartInfo
                {
                    FileName = url,
                    UseShellExecute = true,
                });
                WriteLog("Opened first-run waiting page: " + waitFile);
                return;
            }
            WriteLog("waiting.html not found at " + waitFile + "; falling back to MessageBox.");
        }
        catch (Exception ex)
        {
            WriteLog("OpenWaitingPage failed, falling back to MessageBox: " + ex);
        }

        // Fallback: show a non-blocking MessageBox on a background thread so
        // Main can proceed to the ~30-60s silent installer.
        try
        {
            var thread = new Thread(() =>
            {
                try
                {
                    MessageBox.Show(
                        "Insta360_HW is initializing. Please wait 30-60 seconds.\n\nFirst run deploys the runtime and OrCAD integration.",
                        "Insta360 HW",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
                catch
                {
                    // Never let UI failure block first-run install.
                }
            });
            thread.IsBackground = true;
            thread.SetApartmentState(ApartmentState.STA);
            thread.Start();
        }
        catch (Exception ex)
        {
            WriteLog("OpenWaitingPage MessageBox fallback failed: " + ex);
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

    private static bool IsPlatformReady()
    {
        try
        {
            var request = (HttpWebRequest)WebRequest.Create(PlatformUrl + "/api/health");
            request.Method = "GET";
            request.Timeout = 800;
            request.ReadWriteTimeout = 800;
            using (var response = (HttpWebResponse)request.GetResponse())
            {
                return (int)response.StatusCode >= 200 && (int)response.StatusCode < 500;
            }
        }
        catch
        {
            return false;
        }
    }

    private static bool IsReconnectRequest(string[] args)
    {
        foreach (string arg in args)
        {
            if (arg != null && arg.StartsWith(ReconnectProtocolUrl, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }
        return false;
    }

    private static string BuildLaunchArgs(string[] args, bool suppressBrowserOpen)
    {
        string forwarded = string.Join(" ", QuoteArgs(FilterProtocolArgs(args)));
        if (suppressBrowserOpen)
        {
            if (!string.IsNullOrWhiteSpace(forwarded))
            {
                forwarded += " ";
            }
            forwarded += "-NoOpen";
        }
        return forwarded;
    }

    private static string[] FilterProtocolArgs(string[] args)
    {
        var kept = new System.Collections.Generic.List<string>();
        foreach (string arg in args)
        {
            if (arg == null || arg.StartsWith(ReconnectProtocolUrl, StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            kept.Add(arg);
        }
        return kept.ToArray();
    }

    private static void EnsureReconnectProtocolReady()
    {
        try
        {
            string exePath = Assembly.GetExecutingAssembly().Location;
            using (RegistryKey protocol = Registry.CurrentUser.CreateSubKey("Software\\Classes\\insta360-hw"))
            {
                if (protocol == null) return;
                protocol.SetValue("", "URL:Insta360_HW reconnect protocol", RegistryValueKind.String);
                protocol.SetValue("URL Protocol", "", RegistryValueKind.String);
            }
            using (RegistryKey icon = Registry.CurrentUser.CreateSubKey("Software\\Classes\\insta360-hw\\DefaultIcon"))
            {
                if (icon != null)
                {
                    icon.SetValue("", "\"" + exePath + "\",0", RegistryValueKind.String);
                }
            }
            using (RegistryKey command = Registry.CurrentUser.CreateSubKey("Software\\Classes\\insta360-hw\\shell\\open\\command"))
            {
                if (command != null)
                {
                    command.SetValue("", "\"" + exePath + "\" \"%1\"", RegistryValueKind.String);
                }
            }
        }
        catch (Exception ex)
        {
            WriteLog("Reconnect protocol registration failed: " + ex.Message);
        }
    }

    private static void ShowStartupFailure(string title, Exception ex)
    {
        string message =
            "Insta360_HW startup warning\n\n" +
            title + "\n\n" +
            ex.Message + "\n\n" +
            "Log: " + LogPath() + "\n" +
            "Please send the log to the administrator.";
        WriteLog(title + ": " + ex);
        MessageBox.Show(message, "Insta360_HW", MessageBoxButtons.OK, MessageBoxIcon.Warning);
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
            RotateIfNeeded(path);
            File.AppendAllText(path, DateTime.Now.ToString("s") + " " + message + Environment.NewLine, Encoding.UTF8);
        }
        catch
        {
            // Logging must never prevent the platform from opening.
        }
    }

    private static void RotateIfNeeded(string path)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length < MAX_LOG_BYTES) return;

        string oldest = path + "." + MAX_LOG_FILES;
        if (File.Exists(oldest)) File.Delete(oldest);
        for (int i = MAX_LOG_FILES - 1; i >= 1; i--)
        {
            string current = path + "." + i;
            string next = path + "." + (i + 1);
            if (File.Exists(current))
            {
                if (File.Exists(next)) File.Delete(next);
                File.Move(current, next);
            }
        }
        File.Move(path, path + ".1");
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
