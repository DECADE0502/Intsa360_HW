#define MyAppName "Insta360_HW"
#define MyAppVersion "0.2.20"
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
CloseApplications=yes
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
Name: "{group}\Uninstall Insta360_HW"; Filename: "{uninstallexe}"
Name: "{commondesktop}\Insta360_HW"; Filename: "{app}\Insta360_HW.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create desktop shortcut"; GroupDescription: "Additional options:"

[Run]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\oneclick_install.ps1"" -Silent -NoStart"; \
    WorkingDir: "{app}"; \
    StatusMsg: "Initializing platform configuration and Cadence integration..."; \
    Flags: runhidden

[UninstallRun]
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\uninstall.ps1"" -Mode Detach -InstallDir ""{app}"" -Force"; \
    WorkingDir: "{app}"; \
    Flags: runhidden; RunOnceId: "StopService"

[Code]
var
  AlreadyInstalled: Boolean;
  ActionPage: TInputOptionWizardPage;
  // Marquee progress page shown while the existing version is being uninstalled.
  UninstallProgressPage: TOutputProgressWizardPage;
  // When True, the wizard closes itself silently (no "Exit Setup?" prompt).
  // Set right before WizardForm.Close for programmatic exits.
  ForceSilentClose: Boolean;
  // Set by InitializeUninstall when the user chooses to keep user data. When
  // True, StashUserDataForKeepMode moves data\, config\local.json and
  // plugins\user out of {app} into %LOCALAPPDATA%\Insta360_HW\keep_data\ BEFORE
  // Inno starts deleting the install tree. Inno's [UninstallDelete] is
  // additive-only (it can add more deletions, not carve out exclusions), so
  // moving the data out of {app} is the only reliable way to preserve it.
  UninstallKeepData: Boolean;

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

function PopVersionPart(var V: String): Integer;
var
  Dot: Integer;
  Part: String;
begin
  Dot := Pos('.', V);
  if Dot > 0 then begin
    Part := Copy(V, 1, Dot - 1);
    Delete(V, 1, Dot);
  end else begin
    Part := V;
    V := '';
  end;
  Result := StrToIntDef(Part, 0);
end;

function CompareSemver(A, B: String): Integer;
var
  I: Integer;
  PA: Integer;
  PB: Integer;
begin
  Result := 0;
  for I := 1 to 3 do begin
    PA := PopVersionPart(A);
    PB := PopVersionPart(B);
    if PA < PB then begin
      Result := -1;
      Exit;
    end;
    if PA > PB then begin
      Result := 1;
      Exit;
    end;
  end;
end;

function InitializeSetup(): Boolean;
var
  Installed: String;
begin
  Result := True;
  CleanupBrokenInstallRegistration();
  Installed := '';
  if RegQueryStringValue(HKLM, GetUninstallRegPath(), 'DisplayVersion', Installed) or
     RegQueryStringValue(HKCU, GetUninstallRegPath(), 'DisplayVersion', Installed) then begin
    if CompareSemver(Installed, '{#MyAppVersion}') > 0 then begin
      Result := (MsgBox('A newer version ' + Installed + ' is already installed. Continue downgrading to {#MyAppVersion}?', mbConfirmation, MB_YESNO) = IDYES);
    end;
  end;
end;

procedure InitializeWizard();
begin
  AlreadyInstalled := (GetUninstallString() <> '');
  if AlreadyInstalled then begin
    // The 5th arg (Exclusive) is True -> radio buttons, exactly one selectable.
    ActionPage := CreateInputOptionPage(wpWelcome,
      'Existing installation detected',
      'Choose what you want to do:',
      'These options control this setup run.', True, False);
    ActionPage.Add('Reinstall and keep local data');
    ActionPage.Add('Uninstall existing version');
    ActionPage.Add('Cancel');
    ActionPage.Values[OPT_REINSTALL] := True;
  end;

  // A marquee (indeterminate) progress page for the uninstall phase. We cannot
  // know how long removal takes, so an animated bar + status text is the right
  // signal — far better than a frozen window. Created unconditionally; only
  // shown when the user picks Uninstall.
  UninstallProgressPage := CreateOutputProgressPage('Uninstalling existing version', '');
end;

function StopHwAgentServices(): Boolean;
var
  ResultCode: Integer;
begin
  Exec('powershell.exe',
       '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}') + '\uninstall.ps1" -PreUpgrade -InstallDir "' + ExpandConstant('{app}') + '" -Force',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if AlreadyInstalled then begin
    if not StopHwAgentServices() then
      Result := 'Failed to stop existing Insta360 HW services. Please close the platform and retry.';
  end;
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
      UninstallProgressPage.SetText('Uninstalling existing version. Please wait...', '');
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
            'Uninstalling existing version. Please wait...' + #13#10 + '(Removing program files and Cadence integration)', '');
          Sleep(100);
          Waited := Waited + 1;
        end;

        // Give file handles a moment to release, then signal completion.
        Sleep(500);
        UninstallProgressPage.SetText('Uninstall complete.', '');
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


// Move user-editable state (data\, config\local.json, plugins\user) out of the
// install tree and into %LOCALAPPDATA%\Insta360_HW\keep_data\<timestamp>\
// BEFORE Inno starts deleting {app}. Inno runs [UninstallDelete] after its own
// file removal and that list is additive (adds more deletions), so an
// "exclude" isn't possible — we have to physically relocate the data. Called
// from InitializeUninstall, which fires before [UninstallRun] and before file
// deletion, giving us a clean window to stash. Defined before its caller
// because Inno's Pascal doesn't do forward declarations gracefully.
//
// The destination is timestamped (yyyyMMdd_HHmmss subdir) so that a repeat
// uninstall never collides with an earlier keep_data\ tree — Move-Item -Force
// on a non-empty destination directory FAILS on Windows PowerShell 5.1 and
// $ErrorActionPreference='Continue' would swallow the error, silently losing
// the user's new data. The timestamp guarantees a fresh, empty destination
// each run.
//
// ResultCode is checked by the caller: on non-zero (PowerShell failed to
// launch, or the stash script itself hit an unrecoverable error) the caller
// clears UninstallKeepData and surfaces a MsgBox so the user knows their data
// may not have been preserved before Inno wipes {app}.
procedure StashUserDataForKeepMode(var ResultCode: Integer);
var
  StashCmd: String;
begin
  StashCmd :=
    '-NoProfile -ExecutionPolicy Bypass -Command "'
    + '$ErrorActionPreference = ''Continue''; '
    + '$stamp = Get-Date -Format ''yyyyMMdd_HHmmss''; '
    + '$src = ''' + ExpandConstant('{app}') + '''; '
    + '$dst = Join-Path $env:LOCALAPPDATA (Join-Path ''Insta360_HW\keep_data'' $stamp); '
    + 'New-Item -ItemType Directory -Force -Path $dst | Out-Null; '
    + 'foreach ($p in @(''data'', ''config\local.json'', ''plugins\user'')) { '
    + '  $s = Join-Path $src $p; '
    + '  if (Test-Path -LiteralPath $s) { '
    + '    $d = Join-Path $dst $p; '
    + '    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $d) | Out-Null; '
    + '    Move-Item -Force -LiteralPath $s -Destination $d '
    + '  } '
    + '}"';
  Exec('powershell.exe', StashCmd, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Ask the user whether to preserve local data before uninstalling. Answering
// Yes stashes data\, config\local.json and plugins\user to
// %LOCALAPPDATA%\Insta360_HW\keep_data\<timestamp>\ RIGHT NOW — before
// [UninstallRun] or any Inno-side file deletion runs — so a subsequent
// reinstall / another user can copy the files back manually. Answering No
// leaves the tree untouched and Inno wipes {app} completely.
//
// On stash failure we surface a MsgBox and clear UninstallKeepData so any
// downstream consumer (and the user) knows preservation did not succeed —
// otherwise Inno silently wipes {app} and the user has no idea their data is
// gone. On success we show an informational MsgBox pointing at the stash
// location so recovery is discoverable.
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  UninstallKeepData := (MsgBox(
    '是否保留用户数据?' + #13#10 + #13#10 +
    '  是 (Yes) = 保留 data\、config\local.json、plugins\user' + #13#10 +
    '            (备份到 %LOCALAPPDATA%\Insta360_HW\keep_data\<时间戳>\)' + #13#10 +
    '  否 (No)  = 完全清除',
    mbConfirmation, MB_YESNO) = IDYES);

  if UninstallKeepData then begin
    ResultCode := 0;
    StashUserDataForKeepMode(ResultCode);
    if ResultCode <> 0 then begin
      MsgBox('数据保留失败 (PowerShell 返回码 ' + IntToStr(ResultCode) + ')' + #13#10 +
             '卸载将继续但用户数据可能已丢失。查看 %LOCALAPPDATA%\Insta360_HW\keep_data\ 确认。',
             mbError, MB_OK);
      UninstallKeepData := False;
    end else begin
      MsgBox('用户数据已备份至 %LOCALAPPDATA%\Insta360_HW\keep_data\<时间戳>\' + #13#10 +
             '如需恢复请手动复制回安装目录。',
             mbInformation, MB_OK);
    end;
  end;
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

