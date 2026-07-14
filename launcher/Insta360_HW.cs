using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[DataContract]
internal sealed class ServiceIdentity
{
    [DataMember(Name = "schema")] public int Schema { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "pid")] public int Pid { get; set; }
    [DataMember(Name = "port")] public int Port { get; set; }
    [DataMember(Name = "executable")] public string Executable { get; set; }
    [DataMember(Name = "root")] public string Root { get; set; }
    [DataMember(Name = "state_root")] public string StateRoot { get; set; }
    [DataMember(Name = "version")] public string Version { get; set; }
    [DataMember(Name = "instance_token")] public string InstanceToken { get; set; }
}

[DataContract]
internal sealed class HealthIdentity
{
    [DataMember(Name = "status")] public string Status { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "root")] public string Root { get; set; }
    [DataMember(Name = "state_root")] public string StateRoot { get; set; }
    [DataMember(Name = "version")] public string Version { get; set; }
    [DataMember(Name = "instance_token")] public string InstanceToken { get; set; }
    [DataMember(Name = "pid")] public int Pid { get; set; }
}

[DataContract]
internal sealed class InstallationMetadata
{
    [DataMember(Name = "schema_version")] public int SchemaVersion { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "layout")] public string Layout { get; set; }
    [DataMember(Name = "active_runtime")] public string ActiveRuntime { get; set; }
}

[DataContract]
internal sealed class RuntimeManifest
{
    [DataMember(Name = "schema")] public int Schema { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "layout")] public string Layout { get; set; }
    [DataMember(Name = "version")] public string Version { get; set; }
    [DataMember(Name = "revision")] public string Revision { get; set; }
}

[DataContract]
internal sealed class RecoveryJournal
{
    [DataMember(Name = "schema")] public int Schema { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "phase")] public string Phase { get; set; }
    [DataMember(Name = "install_root")] public string InstallRoot { get; set; }
    [DataMember(Name = "state_root")] public string StateRoot { get; set; }
}

[DataContract]
internal sealed class ProtectedRecoveryDescriptor
{
    [DataMember(Name = "schema")] public int Schema { get; set; }
    [DataMember(Name = "product")] public string Product { get; set; }
    [DataMember(Name = "job_id")] public string JobId { get; set; }
    [DataMember(Name = "install_root")] public string InstallRoot { get; set; }
    [DataMember(Name = "state_root")] public string StateRoot { get; set; }
    [DataMember(Name = "old_relative")] public string OldRelative { get; set; }
    [DataMember(Name = "new_relative")] public string NewRelative { get; set; }
    [DataMember(Name = "outcome")] public string Outcome { get; set; }
}

internal static class Program
{
    private const string MutexName = "Local\\Insta360_HW.Launcher";
    private const string ReconnectProtocolUrl = "insta360-hw://reconnect";
    private const int MaxLogBytes = 512 * 1024;
    private const int MaxLogFiles = 5;
    private const int ScriptTimeoutMilliseconds = 120000;
    private static readonly Regex RuntimePointerPattern = new Regex(
        @"^runtime/((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?\+[0-9a-fA-F]{40})$",
        RegexOptions.CultureInvariant);

    [STAThread]
    private static int Main(string[] args)
    {
        string installRoot = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
        string stateRoot = ResolveStateRoot(installRoot);
        Environment.SetEnvironmentVariable("INSTA360_HW_STATE_ROOT", stateRoot, EnvironmentVariableTarget.Process);
        bool reconnect = IsReconnectRequest(args);

        bool createdNew;
        using (var mutex = new Mutex(true, MutexName, out createdNew))
        {
            if (!createdNew)
            {
                WriteLog(stateRoot, "Another launcher instance is starting the platform.");
                string existingUrl;
                for (int attempt = 0; attempt < 25; attempt++)
                {
                    string activeRuntime = ResolveActiveRuntime(installRoot);
                    if (TryGetHealthyPlatform(activeRuntime, stateRoot, out existingUrl))
                    {
                        if (!reconnect) OpenPlatformUrl(existingUrl);
                        return 0;
                    }
                    Thread.Sleep(200);
                }
                return 0;
            }

            try
            {
                WriteLog(stateRoot, "Launcher started. install=" + installRoot + " state=" + stateRoot);
                int recoveryCode = RunRecovery(installRoot, stateRoot);
                if (recoveryCode != 0)
                {
                    if (recoveryCode == 23)
                    {
                        throw new InvalidOperationException("平台正在完成版本切换，请稍候片刻再重新打开。");
                    }
                    throw new InvalidOperationException("Interrupted update recovery failed with exit code " + recoveryCode + ".");
                }

                string runtimeRoot = ResolveActiveRuntime(installRoot);
                WriteLog(stateRoot, "Resolved active runtime=" + runtimeRoot);
                string launchScript = Path.Combine(runtimeRoot, "launch_tool_suite.ps1");
                string launchArgs = BuildLaunchArgs(args, reconnect, stateRoot);
                int exitCode = RunPowerShellHidden(runtimeRoot, launchScript, launchArgs, stateRoot);
                if (exitCode != 0)
                {
                    throw new InvalidOperationException("Platform service launch failed with exit code " + exitCode + ".");
                }
                return 0;
            }
            catch (Exception ex)
            {
                WriteLog(stateRoot, "Startup failed: " + ex);
                MessageBox.Show(
                    "Insta360_HW 启动失败。\n\n" + ex.Message + "\n\n日志：" + LogPath(stateRoot),
                    "Insta360_HW",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 1;
            }
        }
    }

    private static string ResolveStateRoot(string installRoot)
    {
        string explicitRoot = Environment.GetEnvironmentVariable("INSTA360_HW_STATE_ROOT") ?? "";
        if (!string.IsNullOrWhiteSpace(explicitRoot)) return Path.GetFullPath(explicitRoot).TrimEnd('\\');
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        bool installed = File.Exists(Path.Combine(installRoot, "installation.json")) ||
            File.Exists(Path.Combine(installRoot, "install_manifest.json"));
        if (installed && !string.IsNullOrWhiteSpace(local))
        {
            return Path.Combine(local, "Insta360_HW");
        }
        return installRoot;
    }

    private static string ResolveActiveRuntime(string installRoot)
    {
        string metadataPath = Path.Combine(installRoot, "installation.json");
        if (!File.Exists(metadataPath)) return installRoot;
        InstallationMetadata metadata = ReadJson<InstallationMetadata>(metadataPath);
        if (metadata == null || metadata.SchemaVersion != 3 || metadata.Product != "Insta360_HW" ||
            metadata.Layout != "versioned-runtime-v3" || string.IsNullOrWhiteSpace(metadata.ActiveRuntime))
        {
            throw new InvalidOperationException("Installation metadata is invalid.");
        }
        Match match = RuntimePointerPattern.Match(metadata.ActiveRuntime);
        string runtimeRoot = ResolveRuntimePointerPath(installRoot, metadata.ActiveRuntime, "active runtime");
        if (!Directory.Exists(runtimeRoot))
        {
            throw new InvalidOperationException("Active runtime directory is missing or outside the installation.");
        }
        RuntimeManifest manifest = ReadJson<RuntimeManifest>(Path.Combine(runtimeRoot, "install_manifest.json"));
        string version = ReadText(Path.Combine(runtimeRoot, "VERSION"));
        string revision = ReadText(Path.Combine(runtimeRoot, "REVISION")).ToLowerInvariant();
        if (manifest == null || manifest.Schema != 3 || manifest.Product != "Insta360_HW" ||
            manifest.Layout != "runtime-v3" || manifest.Version != version ||
            string.IsNullOrWhiteSpace(manifest.Revision) || manifest.Revision.ToLowerInvariant() != revision ||
            !string.Equals(match.Groups[1].Value, version + "+" + revision, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Active runtime identity is invalid.");
        }
        return runtimeRoot;
    }

    private static string ResolveRuntimePointerPath(string installRoot, string relative, string label)
    {
        if (string.IsNullOrWhiteSpace(relative) || relative.IndexOf('\\') >= 0 ||
            !RuntimePointerPattern.IsMatch(relative))
        {
            throw new InvalidOperationException(label + " pointer is invalid.");
        }
        string runtimeParent = Path.GetFullPath(Path.Combine(installRoot, "runtime")).TrimEnd('\\');
        string runtimeRoot = Path.GetFullPath(Path.Combine(installRoot, relative.Replace('/', '\\'))).TrimEnd('\\');
        if (!runtimeRoot.StartsWith(runtimeParent + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(label + " pointer escapes the installation.");
        }
        return runtimeRoot;
    }

    private static int RunRecovery(string installRoot, string stateRoot)
    {
        string protectedScript;
        string recoveryJobId;
        var recoveredJobs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        while (FindPendingV3Recovery(installRoot, stateRoot, out protectedScript, out recoveryJobId))
        {
            if (!recoveredJobs.Add(recoveryJobId))
            {
                throw new InvalidOperationException("Lifecycle recovery completed without clearing its protected transaction.");
            }
            string taskName = "Insta360_HW_Recovery_" + recoveryJobId;
            string protectedArgs = "-InstallRoot " + Quote(installRoot) + " -StateRoot " + Quote(stateRoot) +
                " -JobId " + Quote(recoveryJobId) + " -RecoveryTaskName " + Quote(taskName) + " -NoRestart";
            int recoveryCode = RunPowerShellElevated(
                Path.GetDirectoryName(protectedScript), protectedScript, protectedArgs);
            if (recoveryCode != 0) return recoveryCode;
        }
        if (File.Exists(Path.Combine(installRoot, "installation.json")))
        {
            ResolveActiveRuntime(installRoot);
            return 0;
        }
        string runtimeRoot = installRoot;
        string script = Path.Combine(runtimeRoot, "scripts", "lifecycle", "Recover.ps1");
        if (!File.Exists(script)) return 0;
        string args = "-InstallRoot " + Quote(runtimeRoot) + " -StateRoot " + Quote(stateRoot) + " -NoRestart";
        return RunPowerShellHidden(runtimeRoot, script, args, stateRoot);
    }

    private static bool FindPendingV3Recovery(
        string installRoot,
        string stateRoot,
        out string recoveryScript,
        out string recoveryJobId)
    {
        recoveryScript = "";
        recoveryJobId = "";
        string recoveryRoot = Path.Combine(installRoot, ".recovery");
        if (!Directory.Exists(recoveryRoot)) return false;
        foreach (string directory in Directory.GetDirectories(recoveryRoot))
        {
            var directoryInfo = new DirectoryInfo(directory);
            if ((directoryInfo.Attributes & FileAttributes.ReparsePoint) != 0) continue;
            ProtectedRecoveryDescriptor descriptor = ReadJson<ProtectedRecoveryDescriptor>(
                Path.Combine(directory, "transaction.json"));
            if (descriptor == null || descriptor.Schema != 3 || descriptor.Product != "Insta360_HW") continue;
            if (string.IsNullOrWhiteSpace(descriptor.JobId) ||
                !Regex.IsMatch(descriptor.JobId, "^[0-9a-fA-F]{32}$") ||
                !string.Equals(directoryInfo.Name, descriptor.JobId, StringComparison.OrdinalIgnoreCase)) continue;
            if (!SamePath(descriptor.InstallRoot, installRoot) || !SamePath(descriptor.StateRoot, stateRoot)) continue;
            bool completed = string.Equals(descriptor.Outcome, "completed", StringComparison.Ordinal);
            if (!completed && !string.Equals(descriptor.Outcome, "pending", StringComparison.Ordinal)) continue;

            string recoveryRuntime = ResolveRuntimePointerPath(
                installRoot,
                completed ? descriptor.NewRelative : descriptor.OldRelative,
                "recovery runtime");
            string script = Path.Combine(recoveryRuntime, "scripts", "lifecycle_v3", "Recover.ps1");
            if (!File.Exists(script) && completed)
            {
                recoveryRuntime = ResolveRuntimePointerPath(installRoot, descriptor.OldRelative, "fallback recovery runtime");
                script = Path.Combine(recoveryRuntime, "scripts", "lifecycle_v3", "Recover.ps1");
            }
            if (!File.Exists(script)) continue;
            recoveryScript = script;
            recoveryJobId = descriptor.JobId.ToLowerInvariant();
            return true;
        }
        return false;
    }

    private static int RunPowerShellElevated(string workingDir, string script, string extraArgs)
    {
        if (!File.Exists(script)) throw new FileNotFoundException("Missing platform recovery script", script);
        string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        string powershell = Path.Combine(windows, "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
        if (!File.Exists(powershell)) throw new FileNotFoundException("Missing system Windows PowerShell", powershell);
        var info = new ProcessStartInfo
        {
            FileName = powershell,
            Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(script) + " " + extraArgs,
            WorkingDirectory = workingDir,
            UseShellExecute = true,
            Verb = "runas",
            WindowStyle = ProcessWindowStyle.Hidden,
        };
        using (var process = Process.Start(info))
        {
            if (process == null) return 1;
            if (!process.WaitForExit(ScriptTimeoutMilliseconds))
            {
                try { process.Kill(); } catch { }
                return 1460;
            }
            return process.ExitCode;
        }
    }

    private static int RunPowerShellHidden(string workingDir, string script, string extraArgs, string stateRoot)
    {
        if (!File.Exists(script)) throw new FileNotFoundException("Missing platform script", script);
        var info = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            Arguments = "-NoProfile -ExecutionPolicy Bypass -File " + Quote(script) + " " + extraArgs,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            WindowStyle = ProcessWindowStyle.Hidden,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        info.EnvironmentVariables["INSTA360_HW_STATE_ROOT"] = stateRoot;
        using (var process = Process.Start(info))
        {
            if (process == null) return 1;
            Task<string> stdoutTask = process.StandardOutput.ReadToEndAsync();
            Task<string> stderrTask = process.StandardError.ReadToEndAsync();
            if (!process.WaitForExit(ScriptTimeoutMilliseconds))
            {
                try { process.Kill(); } catch { }
                WriteLog(stateRoot, "PowerShell command timed out: " + script);
                return 1460;
            }
            Task.WaitAll(stdoutTask, stderrTask);
            string stdout = stdoutTask.Result;
            string stderr = stderrTask.Result;
            if (!string.IsNullOrWhiteSpace(stdout)) WriteLog(stateRoot, "[stdout] " + stdout.Trim());
            if (!string.IsNullOrWhiteSpace(stderr)) WriteLog(stateRoot, "[stderr] " + stderr.Trim());
            return process.ExitCode;
        }
    }

    private static bool TryGetHealthyPlatform(string root, string stateRoot, out string url)
    {
        url = "";
        ServiceIdentity identity = ReadJson<ServiceIdentity>(Path.Combine(stateRoot, "runtime", "service.json"));
        if (!IsCompleteIdentity(identity, root, stateRoot)) return false;

        try
        {
            using (Process process = Process.GetProcessById(identity.Pid))
            {
                string actualExecutable = process.MainModule == null ? "" : process.MainModule.FileName;
                if (!SamePath(identity.Executable, actualExecutable)) return false;
            }
        }
        catch { return false; }

        try
        {
            var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:" + identity.Port + "/api/health");
            request.Timeout = 900;
            request.ReadWriteTimeout = 900;
            using (var response = (HttpWebResponse)request.GetResponse())
            using (var stream = response.GetResponseStream())
            {
                var serializer = new DataContractJsonSerializer(typeof(HealthIdentity));
                var health = (HealthIdentity)serializer.ReadObject(stream);
                if (health == null || health.Status != "ok" || health.Product != "Insta360_HW") return false;
                if (health.Pid != identity.Pid || health.InstanceToken != identity.InstanceToken) return false;
                if (health.Version != identity.Version) return false;
                if (!SamePath(root, health.Root)) return false;
                if (!SamePath(stateRoot, health.StateRoot)) return false;
                url = "http://127.0.0.1:" + identity.Port;
                return true;
            }
        }
        catch { return false; }
    }

    private static bool IsCompleteIdentity(ServiceIdentity identity, string root, string stateRoot)
    {
        if (identity == null || identity.Schema != 2 || identity.Product != "Insta360_HW") return false;
        if (identity.Pid <= 0 || identity.Port <= 0 || identity.Port > 65535) return false;
        if (string.IsNullOrWhiteSpace(identity.Executable) || !File.Exists(identity.Executable)) return false;
        if (string.IsNullOrWhiteSpace(identity.InstanceToken) || identity.InstanceToken.Length != 32) return false;
        if (!SamePath(root, identity.Root) || !SamePath(stateRoot, identity.StateRoot)) return false;
        string version = ReadText(Path.Combine(root, "VERSION"));
        return !string.IsNullOrWhiteSpace(version) && version == identity.Version;
    }

    private static T ReadJson<T>(string path) where T : class
    {
        try
        {
            if (!File.Exists(path)) return null;
            using (var stream = File.OpenRead(path))
            {
                var serializer = new DataContractJsonSerializer(typeof(T));
                return serializer.ReadObject(stream) as T;
            }
        }
        catch { return null; }
    }

    private static string ReadText(string path)
    {
        try { return File.ReadAllText(path, Encoding.UTF8).Trim(); }
        catch { return ""; }
    }

    private static bool SamePath(string left, string right)
    {
        if (string.IsNullOrWhiteSpace(left) || string.IsNullOrWhiteSpace(right)) return false;
        try
        {
            return string.Equals(
                Path.GetFullPath(left).TrimEnd('\\'),
                Path.GetFullPath(right).TrimEnd('\\'),
                StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    private static string BuildLaunchArgs(string[] args, bool reconnect, string stateRoot)
    {
        var values = new System.Collections.Generic.List<string>();
        foreach (string arg in args)
        {
            if (arg == null || arg.StartsWith(ReconnectProtocolUrl, StringComparison.OrdinalIgnoreCase)) continue;
            values.Add(Quote(arg));
        }
        if (reconnect)
        {
            values.Add("-Restart");
            values.Add("-NoOpen");
        }
        values.Add("-StateRoot");
        values.Add(Quote(stateRoot));
        return string.Join(" ", values.ToArray());
    }

    private static bool IsReconnectRequest(string[] args)
    {
        foreach (string arg in args)
        {
            if (arg != null && arg.StartsWith(ReconnectProtocolUrl, StringComparison.OrdinalIgnoreCase)) return true;
        }
        return false;
    }

    private static string Quote(string value)
    {
        return "\"" + (value ?? "").Replace("\"", "`\"") + "\"";
    }

    private static void OpenPlatformUrl(string url)
    {
        Process.Start(new ProcessStartInfo { FileName = url, UseShellExecute = true });
    }

    private static string LogPath(string stateRoot)
    {
        return Path.Combine(stateRoot, "logs", "launcher.log");
    }

    private static void WriteLog(string stateRoot, string message)
    {
        try
        {
            string path = LogPath(stateRoot);
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            RotateIfNeeded(path);
            File.AppendAllText(path, DateTime.Now.ToString("s") + " " + message + Environment.NewLine, Encoding.UTF8);
        }
        catch { }
    }

    private static void RotateIfNeeded(string path)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length < MaxLogBytes) return;
        string oldest = path + "." + MaxLogFiles;
        if (File.Exists(oldest)) File.Delete(oldest);
        for (int index = MaxLogFiles - 1; index >= 1; index--)
        {
            string current = path + "." + index;
            string next = path + "." + (index + 1);
            if (!File.Exists(current)) continue;
            if (File.Exists(next)) File.Delete(next);
            File.Move(current, next);
        }
        File.Move(path, path + ".1");
    }
}
