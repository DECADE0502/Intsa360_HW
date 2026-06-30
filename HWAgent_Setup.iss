#define MyAppName "Insta360_HW"
#define MyAppVersion "0.2.5"
#define MyAppPublisher "Insta360"
#define ReleaseDir "..\HWAgent_release"
#define IconFile "..\HWAgent_release\app\frontend\assets\insta360_icon.ico"

[Setup]
AppId={{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Insta360\HWAgent
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename=Insta360_HW_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\Insta360_HW.exe
SetupIconFile={#IconFile}
ShowLanguageDialog=no
LanguageDetectionMethod=none
CloseApplications=no
RestartIfNeededByRun=no

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[InstallDelete]
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\cadence"
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\tools"
Type: files; Name: "{app}\Insta360_HW.exe"

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "data\*,uploads\*,outputs\*,history\*,config\local.json,plugins\user\*"

[Icons]
Name: "{group}\Insta360_HW"; Filename: "{app}\Insta360_HW.exe"; WorkingDir: "{app}"
Name: "{group}\卸载 Insta360_HW"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Insta360_HW"; Filename: "{app}\Insta360_HW.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项:"

[Run]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\oneclick_install.ps1"" -Silent -NoStart"; \
    WorkingDir: "{app}"; \
    StatusMsg: "正在初始化平台配置与 Cadence 集成..."; \
    Flags: runhidden

[UninstallRun]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"" -Mode Detach -InstallDir ""{app}"" -Force"; \
    WorkingDir: "{app}"; \
    Flags: runhidden; RunOnceId: "StopService"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  AlreadyInstalled: Boolean;
  ActionPage: TInputOptionWizardPage;
  // Marquee progress page shown while the existing version is being uninstalled.
  UninstallProgressPage: TOutputProgressWizardPage;
  // When True, the wizard closes itself silently (no "Exit Setup?" prompt).
  // Set right before WizardForm.Close for programmatic exits.
  ForceSilentClose: Boolean;

const
  // Index into ActionPage.Values for the three radio options. Kept as named
  // constants so the single-select radio semantics read clearly at each call
  // site — Inno's radio buttons enforce mutual exclusion, but the logic below
  // still checks one index per branch.
  OPT_REINSTALL = 0;
  OPT_UNINSTALL = 1;
  OPT_CANCEL    = 2;

function GetUninstallRegPath(): String;
begin
  Result := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1';
end;

function GetUninstallString(): String;
var
  sUnInst: String;
begin
  Result := '';
  sUnInst := '';
  if RegQueryStringValue(HKLM, GetUninstallRegPath(), 'UninstallString', sUnInst) then
    Result := sUnInst;
  if (Result = '') and RegQueryStringValue(HKCU, GetUninstallRegPath(), 'UninstallString', sUnInst) then
    Result := sUnInst;
end;

function GetInstallLocation(): String;
var
  sInstallLocation: String;
begin
  Result := '';
  sInstallLocation := '';
  if RegQueryStringValue(HKLM, GetUninstallRegPath(), 'InstallLocation', sInstallLocation) then
    Result := sInstallLocation;
  if (Result = '') and RegQueryStringValue(HKCU, GetUninstallRegPath(), 'InstallLocation', sInstallLocation) then
    Result := sInstallLocation;
end;

function UninstallExeExists(UninstallString: String): Boolean;
var
  exePath: String;
begin
  exePath := RemoveQuotes(UninstallString);
  Result := (exePath <> '') and FileExists(exePath);
end;

procedure CleanupBrokenInstallRegistration();
var
  uninst: String;
  installDir: String;
begin
  uninst := GetUninstallString();
  if (uninst = '') or UninstallExeExists(uninst) then
    Exit;

  installDir := RemoveBackslashUnlessRoot(GetInstallLocation());
  if (installDir <> '') and DirExists(installDir) then begin
    DelTree(installDir, True, True, True);
  end;

  RegDeleteKeyIncludingSubkeys(HKLM, GetUninstallRegPath());
  RegDeleteKeyIncludingSubkeys(HKCU, GetUninstallRegPath());
end;

procedure InitializeWizard();
begin
  CleanupBrokenInstallRegistration();
  AlreadyInstalled := (GetUninstallString() <> '');
  if AlreadyInstalled then begin
    // The 5th arg (Exclusive) is True -> radio buttons, exactly one selectable.
    ActionPage := CreateInputOptionPage(wpWelcome,
      '检测到已安装版本',
      '请选择要执行的操作:',
      '以下选项决定本次安装程序的行为', True, False);
    ActionPage.Add('重新安装（覆盖现有版本）');
    ActionPage.Add('卸载现有版本');
    ActionPage.Add('取消');
    ActionPage.Values[OPT_REINSTALL] := True;
  end;

  // A marquee (indeterminate) progress page for the uninstall phase. We cannot
  // know how long removal takes, so an animated bar + status text is the right
  // signal — far better than a frozen window. Created unconditionally; only
  // shown when the user picks Uninstall.
  UninstallProgressPage := CreateOutputProgressPage('正在卸载现有版本', '');
end;

// Suppress the "Exit Setup?" confirmation when we close the wizard
// programmatically (via ForceSilentClose). Without this, calling
// WizardForm.Close on the Uninstall/Cancel paths pops the "are you sure you
// want to exit" box, which made uninstall look like it was cancelled.
procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if ForceSilentClose then begin
    Confirm := False;  // skip the "Exit Setup?" message box
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // For the Uninstall and Cancel choices we never reach the normal install
  // pages; only Reinstall continues through the standard wizard flow.
  if AlreadyInstalled and Assigned(ActionPage) then begin
    if (PageID <> ActionPage.ID) and
       (ActionPage.Values[OPT_UNINSTALL] or ActionPage.Values[OPT_CANCEL]) then
      Result := True;
  end;
end;

// Launch the existing uninstaller as a fully detached process, then close this
// installer immediately. The uninstaller copies itself to TEMP and runs that
// copy, so it survives this installer exiting. We do NOT wait here: waiting
// blocked the wizard window (looked frozen) for up to 60s. Detaching means the
// user sees the installer close promptly while removal finishes on its own.
procedure CloseWizardSilently();
begin
  ForceSilentClose := True;
  WizardForm.Close();
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Uninst: String;
  UninstExe: String;
  ResultCode: Integer;
  Waited: Integer;
begin
  Result := True;
  if not (AlreadyInstalled and Assigned(ActionPage) and (CurPageID = ActionPage.ID)) then
    Exit;

  // Cancel: close the whole installer silently, no exit prompt.
  if ActionPage.Values[OPT_CANCEL] then begin
    CloseWizardSilently();
    Result := False;
    Exit;
  end;

  // Uninstall: show a marquee progress page, run the existing uninstaller,
  // poll until it truly finishes (registry key gone), then close the wizard.
  // This gives the user a visible "uninstalling..." state and a clean finish
  // instead of either a frozen window or a silent disappearance.
  if ActionPage.Values[OPT_UNINSTALL] then begin
    Uninst := GetUninstallString();
    if Uninst <> '' then begin
      UninstExe := RemoveQuotes(Uninst);
      if not FileExists(UninstExe) then begin
        CleanupBrokenInstallRegistration();
        CloseWizardSilently();
        Result := False;
        Exit;
      end;

      // Show the progress page with an animated bar + status text.
      UninstallProgressPage.SetText('正在卸载现有版本，请稍候...', '');
      UninstallProgressPage.SetProgress(0, 100);
      UninstallProgressPage.Show();

      try
        // VERYSILENT: the uninstaller shows no window of its own.
        // ewNoWait: the stub exits immediately (it relaunches a TEMP copy);
        // we poll below instead of trusting ewWaitUntilTerminated.
        Exec(UninstExe, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
             SW_HIDE, ewNoWait, ResultCode);

        // Poll until the registered uninstall key disappears — the reliable
        // signal that the TEMP copy has finished deleting files. Calling
        // SetText each iteration forces the progress page to repaint, so the
        // bar animates and the window stays responsive (max ~60s).
        Waited := 0;
        while (GetUninstallString() <> '') and (Waited < 150) do begin
          UninstallProgressPage.SetText(
            '正在卸载现有版本，请稍候...' + #13#10 + '（删除程序文件与集成）', '');
          Sleep(100);
          Waited := Waited + 1;
        end;

        // Give file handles a moment to release, then signal completion.
        Sleep(500);
        UninstallProgressPage.SetText('卸载完成。', '');
        Sleep(800);
      finally
        UninstallProgressPage.Hide();
      end;
    end;
    // Uninstall is done — close the installer cleanly.
    CloseWizardSilently();
    Result := False;
    Exit;
  end;

  // Reinstall: fall through to the normal install flow.
end;


// After the uninstaller has removed its own files, also delete the now-empty
// publisher parent directory ({app} = ...\Insta360\HWAgent, so its parent is
// ...\Insta360). Inno only removes dirs it created; the publisher folder would
// otherwise linger. Only delete it when it contains nothing besides HWAgent,
// so we never touch an unrelated sibling install.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ParentDir: String;
  FindRec: TFindRec;
  Safe: Boolean;
  ResultCode: Integer;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;

  // {app} already resolved; drop the trailing HWAgent to get ...\Insta360.
  ParentDir := ExtractFilePath(ExpandConstant('{app}'));
  ParentDir := RemoveBackslashUnlessRoot(ParentDir);
  if (ParentDir = '') or not DirExists(ParentDir) then
    Exit;

  // Walk the parent dir; safe to remove only if every entry is 'HWAgent'
  // (case-insensitive). Anything else (another product, a stray file) aborts.
  Safe := True;
  if FindFirst(AddBackslash(ParentDir) + '*', FindRec) then begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then begin
          if LowerCase(FindRec.Name) <> 'hwagent' then begin
            Safe := False;
            Break;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;

  if Safe then begin
    // DelTree removes the dir tree; True recurses. We already confirmed only
    // HWAgent remains (and Inno just deleted its contents), so this is the
    // final cleanup of the empty publisher folder.
    DelTree(ParentDir, True, True, True);
  end;
end;
