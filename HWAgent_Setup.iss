#define MyAppName "Insta360硬件提效平台"
#ifndef MyAppVersion
  #define MyAppVersion "0.4.2"
#endif
#define MyAppPublisher "Insta360"
#define MyAppExeName "Insta360_HW.exe"
#ifndef ReleaseDir
  #define ReleaseDir "..\HWAgent_release"
#endif
#ifndef IconFile
  #define IconFile "..\HWAgent_release\app\frontend\assets\insta360_icon.ico"
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir ".."
#endif

[Setup]
AppId={{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Insta360\HWAgent
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#InstallerOutputDir}
OutputBaseFilename=Insta360_HW_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
Uninstallable=yes
CreateUninstallRegKey=yes
SetupIconFile={#IconFile}
ShowLanguageDialog=no
LanguageDetectionMethod=none
CloseApplications=yes
RestartApplications=no
RestartIfNeededByRun=no
ChangesAssociations=yes
SetupLogging=yes
UsePreviousAppDir=yes
AllowCancelDuringInstall=no

[Languages]
Name: "chinesesimp"; MessagesFile: "installer\ChineseSimplified.isl"

[Files]
Source: "{#ReleaseDir}\*"; DestDir: "{tmp}\Insta360_HW_payload"; Flags: recursesubdirs createallsubdirs ignoreversion deleteafterinstall
Source: "{#ReleaseDir}\scripts\lifecycle_v3\SetupRunner.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle_v3\SetupRecover.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle_v3\Contract.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle_v3\Runtime.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle_v3\Recover.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle_v3\Uninstall.ps1"; DestDir: "{app}\maintenance"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\remove_cadence_loader.ps1"; DestDir: "{app}\maintenance\scripts"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lib\*.ps1"; DestDir: "{app}\maintenance\scripts\lib"; Flags: ignoreversion
Source: "{#ReleaseDir}\scripts\lifecycle\*.ps1"; DestDir: "{app}\maintenance\legacy_lifecycle"; Flags: ignoreversion

[Registry]
Root: HKLM; Subkey: "Software\Classes\insta360-hw"; ValueType: string; ValueName: ""; ValueData: "URL:Insta360_HW reconnect protocol"; Flags: uninsdeletekey
Root: HKLM; Subkey: "Software\Classes\insta360-hw"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKLM; Subkey: "Software\Classes\insta360-hw"; ValueType: string; ValueName: "Owner"; ValueData: "Insta360_HW"
Root: HKLM; Subkey: "Software\Classes\insta360-hw\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"",0"
Root: HKLM; Subkey: "Software\Classes\insta360-hw\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加选项："

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked; Check: ShouldLaunchPlatform

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{B7F3AC9E-2D5E-4A8C-9F6E-1A3D4E5F6B72}_is1';

var
  PreserveUserData: Boolean;
  UninstallCleanupRan: Boolean;
  ExistingInstallDetected: Boolean;
  ExistingRuntimeHealthy: Boolean;
  ExistingVersion: String;
  ExistingInstallDir: String;
  ExistingUninstaller: String;
  ExistingInstallPage: TInputOptionWizardPage;
  UpgradeIndex: Integer;
  RepairIndex: Integer;
  ReinstallIndex: Integer;
  UninstallIndex: Integer;
  CancelIndex: Integer;
  SelectedInstallAction: String;
  MaintenanceCloseRequested: Boolean;
  MaintenanceUninstallAfterRepair: Boolean;
  SetupLifecycleSucceeded: Boolean;

function ReadJsonString(const FileName, Key: String; var Value: String): Boolean;
var
  Text: AnsiString;
  KeyPosition: Integer;
  ColonPosition: Integer;
  QuotePosition: Integer;
begin
  Result := False;
  Value := '';
  if not LoadStringFromFile(FileName, Text) then
    Exit;
  KeyPosition := Pos('"' + Key + '"', Text);
  if KeyPosition = 0 then
    Exit;
  Delete(Text, 1, KeyPosition + Length(Key) + 1);
  ColonPosition := Pos(':', Text);
  if ColonPosition = 0 then
    Exit;
  Delete(Text, 1, ColonPosition);
  Text := TrimLeft(Text);
  if (Length(Text) = 0) or (Text[1] <> #34) then
    Exit;
  Delete(Text, 1, 1);
  QuotePosition := Pos('"', Text);
  if QuotePosition = 0 then
    Exit;
  Value := Copy(Text, 1, QuotePosition - 1);
  Result := True;
end;

function ReadJsonInteger(const FileName, Key: String; var Value: Integer): Boolean;
var
  Text: AnsiString;
  KeyPosition: Integer;
  ColonPosition: Integer;
  DigitCount: Integer;
begin
  Result := False;
  Value := 0;
  if not LoadStringFromFile(FileName, Text) then
    Exit;
  KeyPosition := Pos('"' + Key + '"', Text);
  if KeyPosition = 0 then
    Exit;
  Delete(Text, 1, KeyPosition + Length(Key) + 1);
  ColonPosition := Pos(':', Text);
  if ColonPosition = 0 then
    Exit;
  Delete(Text, 1, ColonPosition);
  Text := TrimLeft(Text);
  DigitCount := 0;
  while (DigitCount < Length(Text)) and (Text[DigitCount + 1] >= '0') and
    (Text[DigitCount + 1] <= '9') do
    DigitCount := DigitCount + 1;
  if DigitCount = 0 then
    Exit;
  Value := StrToIntDef(Copy(Text, 1, DigitCount), -1);
  Result := Value >= 0;
end;

function ExtractExecutablePath(const CommandLine: String): String;
var
  Text: String;
  EndQuote: Integer;
  SpacePosition: Integer;
begin
  Text := Trim(CommandLine);
  Result := '';
  if Text = '' then
    Exit;
  if Text[1] = #34 then begin
    Delete(Text, 1, 1);
    EndQuote := Pos('"', Text);
    if EndQuote > 0 then
      Result := Copy(Text, 1, EndQuote - 1);
  end else begin
    SpacePosition := Pos(' ', Text);
    if SpacePosition = 0 then
      Result := Text
    else
      Result := Copy(Text, 1, SpacePosition - 1);
  end;
end;

function ResolveActiveRuntime(const InstallDir: String; var RuntimeDir: String): Boolean;
var
  Pointer: String;
begin
  Result := False;
  RuntimeDir := '';
  if not ReadJsonString(AddBackslash(InstallDir) + 'installation.json', 'active_runtime', Pointer) then
    Exit;
  if (Pos('runtime/', Lowercase(Pointer)) <> 1) or (Pos('..', Pointer) > 0) or (Pos('\', Pointer) > 0) then
    Exit;
  StringChangeEx(Pointer, '/', '\', True);
  RuntimeDir := AddBackslash(InstallDir) + Pointer;
  Result := DirExists(RuntimeDir);
end;

function ReadRuntimeVersion(const RuntimeDir: String; var Version: String): Boolean;
var
  Text: AnsiString;
begin
  Version := '';
  Result := ReadJsonString(AddBackslash(RuntimeDir) + 'install_manifest.json', 'version', Version);
  if Result and (Version <> '') then
    Exit;
  Result := False;
  if LoadStringFromFile(AddBackslash(RuntimeDir) + 'VERSION', Text) then begin
    Version := Trim(Text);
    Result := Version <> '';
  end;
end;

function DetectExistingInstall(): Boolean;
var
  FoundRegistry: Boolean;
  RegisteredCommand: String;
  RegisteredVersion: String;
  ActiveRuntime: String;
  ActiveRuntimeResolved: Boolean;
  DefaultInstallDir: String;
begin
  ExistingVersion := '';
  ExistingInstallDir := '';
  ExistingUninstaller := '';
  ExistingRuntimeHealthy := False;
  RegisteredVersion := '';
  DefaultInstallDir := ExpandConstant('{autopf}\Insta360\HWAgent');
  FoundRegistry := RegKeyExists(HKLM64, UninstallKey);
  if not FoundRegistry then
    FoundRegistry := RegKeyExists(HKLM32, UninstallKey);

  if FoundRegistry then begin
    if not RegQueryStringValue(HKLM64, UninstallKey, 'InstallLocation', ExistingInstallDir) then
      RegQueryStringValue(HKLM32, UninstallKey, 'InstallLocation', ExistingInstallDir);
    if not RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', RegisteredVersion) then
      RegQueryStringValue(HKLM32, UninstallKey, 'DisplayVersion', RegisteredVersion);
    RegisteredCommand := '';
    if not RegQueryStringValue(HKLM64, UninstallKey, 'UninstallString', RegisteredCommand) then
      RegQueryStringValue(HKLM32, UninstallKey, 'UninstallString', RegisteredCommand);
    ExistingUninstaller := ExtractExecutablePath(RegisteredCommand);
  end;

  if ExistingInstallDir = '' then
    ExistingInstallDir := DefaultInstallDir;
  Result := FoundRegistry or FileExists(AddBackslash(ExistingInstallDir) + 'installation.json');
  if not Result then
    Exit;

  if ExistingUninstaller = '' then
    ExistingUninstaller := AddBackslash(ExistingInstallDir) + 'unins000.exe';
  ActiveRuntimeResolved := ResolveActiveRuntime(ExistingInstallDir, ActiveRuntime);
  if ActiveRuntimeResolved then
    ReadRuntimeVersion(ActiveRuntime, ExistingVersion)
  else
    ReadRuntimeVersion(ExistingInstallDir, ExistingVersion);
  if ExistingVersion = '' then
    ExistingVersion := RegisteredVersion;
  if ExistingVersion = '' then
    ExistingVersion := '未知';

  ExistingRuntimeHealthy := ActiveRuntimeResolved and
    FileExists(AddBackslash(ExistingInstallDir) + 'Insta360_HW.exe') and
    FileExists(AddBackslash(ActiveRuntime) + 'VERSION') and
    FileExists(AddBackslash(ActiveRuntime) + 'scripts\lifecycle_v3\Install.ps1') and
    FileExists(AddBackslash(ActiveRuntime) + 'scripts\lifecycle_v3\Uninstall.ps1') and
    FileExists(ExistingUninstaller);
end;

procedure RestoreExistingDisplayVersion();
begin
  if (not ExistingInstallDetected) or (ExistingVersion = '') or (ExistingVersion = '未知') then
    Exit;
  if RegKeyExists(HKLM64, UninstallKey) then
    RegWriteStringValue(HKLM64, UninstallKey, 'DisplayVersion', ExistingVersion);
  if RegKeyExists(HKLM32, UninstallKey) then
    RegWriteStringValue(HKLM32, UninstallKey, 'DisplayVersion', ExistingVersion);
end;

function NumericVersionCore(const Version: String): String;
var
  DashPosition: Integer;
  PlusPosition: Integer;
  CutPosition: Integer;
begin
  Result := Version;
  DashPosition := Pos('-', Result);
  PlusPosition := Pos('+', Result);
  CutPosition := 0;
  if DashPosition > 0 then
    CutPosition := DashPosition;
  if (PlusPosition > 0) and ((CutPosition = 0) or (PlusPosition < CutPosition)) then
    CutPosition := PlusPosition;
  if CutPosition > 0 then
    Result := Copy(Result, 1, CutPosition - 1);
end;

function TakeVersionPart(var Version: String): Integer;
var
  DotPosition: Integer;
  Part: String;
begin
  DotPosition := Pos('.', Version);
  if DotPosition = 0 then begin
    Part := Version;
    Version := '';
  end else begin
    Part := Copy(Version, 1, DotPosition - 1);
    Delete(Version, 1, DotPosition);
  end;
  Result := StrToIntDef(Part, 0);
end;

function CompareSemanticVersion(const Left, Right: String): Integer;
var
  LeftCore: String;
  RightCore: String;
  Index: Integer;
  LeftPart: Integer;
  RightPart: Integer;
begin
  LeftCore := NumericVersionCore(Left);
  RightCore := NumericVersionCore(Right);
  Result := 0;
  for Index := 1 to 3 do begin
    LeftPart := TakeVersionPart(LeftCore);
    RightPart := TakeVersionPart(RightCore);
    if LeftPart < RightPart then begin Result := -1; Exit; end;
    if LeftPart > RightPart then begin Result := 1; Exit; end;
  end;
end;

procedure AddMaintenanceOption(const Caption: String; var OptionIndex, OptionCount: Integer);
begin
  OptionIndex := OptionCount;
  ExistingInstallPage.Add(Caption);
  OptionCount := OptionCount + 1;
end;

procedure InitializeWizard();
var
  Detail: String;
  OptionCount: Integer;
  VersionComparison: Integer;
begin
  SelectedInstallAction := 'Install';
  UpgradeIndex := -1;
  RepairIndex := -1;
  ReinstallIndex := -1;
  UninstallIndex := -1;
  CancelIndex := -1;
  ExistingInstallDetected := DetectExistingInstall();
  if ExistingInstallDetected then
    WizardForm.DirEdit.Text := ExistingInstallDir;

  if ExistingInstallDetected then begin
    if not ExistingRuntimeHealthy then
      Detail := '检测到版本 ' + ExistingVersion + '，但入口、运行时或标准卸载器不完整。'
    else
      Detail := '已检测到版本 ' + ExistingVersion + '，安装目录将固定为：' + ExistingInstallDir;
  end else
    Detail := '未检测到已有安装，将执行全新安装。';

  ExistingInstallPage := CreateInputOptionPage(
    wpWelcome,
    '维护 Insta360硬件提效平台',
    Detail,
    '请选择要执行的操作：',
    True,
    False);
  OptionCount := 0;
  if ExistingInstallDetected then begin
    if ExistingVersion = '未知' then begin
      AddMaintenanceOption('修复当前安装（使用本安装包恢复完整程序）', RepairIndex, OptionCount);
      AddMaintenanceOption('重新安装 {#MyAppVersion}（用户数据不受影响）', ReinstallIndex, OptionCount);
    end else begin
      VersionComparison := CompareSemanticVersion('{#MyAppVersion}', ExistingVersion);
      if VersionComparison > 0 then
        AddMaintenanceOption('升级到 {#MyAppVersion}（保留旧运行时用于回退）', UpgradeIndex, OptionCount)
      else if VersionComparison = 0 then begin
        AddMaintenanceOption('修复当前安装（校验并恢复入口、运行时和 Cadence 集成）', RepairIndex, OptionCount);
        AddMaintenanceOption('重新安装 {#MyAppVersion}（重新写入程序文件）', ReinstallIndex, OptionCount);
      end else
        ExistingInstallPage.SubCaptionLabel.Caption :=
          Detail + #13#10 + '此 Setup 比已安装版本旧，已禁止隐式降级。请使用相同或更新版本的 Setup。';
    end;
    AddMaintenanceOption('卸载 Insta360硬件提效平台', UninstallIndex, OptionCount);
    AddMaintenanceOption('取消，不做任何更改', CancelIndex, OptionCount);
    ExistingInstallPage.SelectedValueIndex := 0;
  end;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ((PageID = ExistingInstallPage.ID) and (not ExistingInstallDetected)) or
    ((PageID = wpSelectDir) and ExistingInstallDetected);
end;

function StartExistingUninstaller(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if not FileExists(ExistingUninstaller) then
    Exit;
  Result := Exec(
    ExistingUninstaller,
    '',
    ExistingInstallDir,
    SW_SHOWNORMAL,
    ewNoWait,
    ResultCode);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Selected: Integer;
  VersionComparison: Integer;
begin
  Result := True;
  if (not ExistingInstallDetected) or (CurPageID <> ExistingInstallPage.ID) then
    Exit;
  Selected := ExistingInstallPage.SelectedValueIndex;
  if Selected = UpgradeIndex then
    SelectedInstallAction := 'Upgrade'
  else if Selected = RepairIndex then
    SelectedInstallAction := 'Repair'
  else if Selected = ReinstallIndex then
    SelectedInstallAction := 'Reinstall'
  else if Selected = UninstallIndex then begin
    if StartExistingUninstaller() then begin
      MaintenanceCloseRequested := True;
      Result := False;
      WizardForm.Close;
      Exit;
    end;
    VersionComparison := CompareSemanticVersion('{#MyAppVersion}', ExistingVersion);
    if (ExistingVersion <> '未知') and (VersionComparison < 0) then begin
      MsgBox('标准卸载器缺失，且此 Setup 版本较旧，无法安全修复卸载组件。请使用相同或更新版本的 Setup。', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    MaintenanceUninstallAfterRepair := True;
    if ExistingVersion = '未知' then
      SelectedInstallAction := 'Repair'
    else if VersionComparison > 0 then
      SelectedInstallAction := 'Upgrade'
    else
      SelectedInstallAction := 'Reinstall';
  end else if Selected = CancelIndex then begin
    MaintenanceCloseRequested := True;
    Result := False;
    WizardForm.Close;
  end;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if MaintenanceCloseRequested then begin
    Cancel := True;
    Confirm := False;
  end;
end;

function StateRoot(): String;
begin
  Result := ExpandConstant('{localappdata}\Insta360_HW');
end;

function ProgressText(const Stage: String): String;
begin
  if Stage = 'recovering_interrupted_setup' then Result := '正在恢复上次中断的安装'
  else if Stage = 'recovering_legacy_setup' then Result := '正在恢复旧版安装事务'
  else if Stage = 'recovering_legacy_update' then Result := '正在恢复旧版更新事务'
  else if Stage = 'recovering_interrupted_operation' then Result := '正在恢复上次未完成的操作'
  else if Stage = 'validating_payload' then Result := '正在校验安装包'
  else if Stage = 'acquiring_lifecycle' then Result := '正在等待其他平台操作完成'
  else if Stage = 'migrating_user_state' then Result := '正在迁移并保护用户数据'
  else if Stage = 'copying_runtime' then Result := '正在写入版本化运行时'
  else if Stage = 'snapshotting_integration' then Result := '正在备份 Cadence 集成'
  else if Stage = 'activating_runtime' then Result := '正在切换活动版本'
  else if Stage = 'deploying_cadence' then Result := '正在部署 Cadence 集成'
  else if Stage = 'verifying_service' then Result := '正在启动并验证平台服务'
  else if Stage = 'stopping_service' then Result := '正在停止平台服务'
  else if Stage = 'removing_cadence' then Result := '正在移除 Cadence 集成'
  else if Stage = 'removing_recovery' then Result := '正在清理恢复任务'
  else if Stage = 'cleaning_state' then Result := '正在清理平台状态'
  else if Stage = 'purging_user_data' then Result := '正在删除用户数据'
  else if Stage = 'completed' then Result := '操作已完成'
  else Result := '正在处理，请稍候';
end;

function ScaleProgress(const Percent, Maximum: Integer): Integer;
var
  BoundedPercent: Integer;
begin
  BoundedPercent := Percent;
  if BoundedPercent < 0 then BoundedPercent := 0;
  if BoundedPercent > 100 then BoundedPercent := 100;
  if Maximum <= 0 then
    Result := 0
  else
    Result := (BoundedPercent * Maximum) div 100;
end;

function RunLifecycleAsync(
  const Operation, EntryPath, ActionOrMode: String;
  const IsUninstall: Boolean): Integer;
var
  RunnerPath: String;
  ProgressPath: String;
  ResultPath: String;
  Parameters: String;
  Started: Boolean;
  ProcessCode: Integer;
  ProgressValue: Integer;
  Stage: String;
  ResultText: AnsiString;
begin
  Result := 9001;
  RunnerPath := ExpandConstant('{app}\maintenance\SetupRunner.ps1');
  if not FileExists(RunnerPath) then
    Exit;
  ProgressPath := GenerateUniqueName(ExpandConstant('{tmp}'), '.progress.json');
  ResultPath := GenerateUniqueName(ExpandConstant('{tmp}'), '.result.txt');
  Parameters :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + RunnerPath + '" ' +
    '-Operation ' + Operation + ' ' +
    '-EntryPath "' + EntryPath + '" ' +
    '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
    '-StateRoot "' + StateRoot() + '" ' +
    '-ProgressPath "' + ProgressPath + '" ' +
    '-ResultPath "' + ResultPath + '" ';
  if Operation = 'Install' then
    Parameters := Parameters +
      '-PayloadRoot "' + ExpandConstant('{tmp}\Insta360_HW_payload') + '" ' +
      '-Action ' + ActionOrMode
  else
    Parameters := Parameters + '-Mode ' + ActionOrMode;

  Started := Exec('powershell.exe', Parameters, ExpandConstant('{app}'), SW_HIDE, ewNoWait, ProcessCode);
  if not Started then begin
    Result := 9001;
    Exit;
  end;

  while not FileExists(ResultPath) do begin
    if FileExists(ProgressPath) then begin
      if not ReadJsonInteger(ProgressPath, 'progress', ProgressValue) then
        ProgressValue := 0;
      ReadJsonString(ProgressPath, 'stage', Stage);
      if IsUninstall then begin
        UninstallProgressForm.ProgressBar.Position :=
          ScaleProgress(ProgressValue, UninstallProgressForm.ProgressBar.Max);
        UninstallProgressForm.StatusLabel.Caption := ProgressText(Stage);
        UninstallProgressForm.Refresh;
      end else begin
        WizardForm.ProgressGauge.Style := npbstNormal;
        WizardForm.ProgressGauge.Position :=
          ScaleProgress(ProgressValue, WizardForm.ProgressGauge.Max);
        WizardForm.StatusLabel.Caption := ProgressText(Stage);
        WizardForm.Refresh;
      end;
    end;
    Sleep(150);
  end;
  if LoadStringFromFile(ResultPath, ResultText) then
    Result := StrToIntDef(Trim(ResultText), 9001);
  DeleteFile(ProgressPath);
  DeleteFile(ResultPath);
end;

function ShouldLaunchPlatform(): Boolean;
begin
  Result := SetupLifecycleSucceeded and (not MaintenanceUninstallAfterRepair);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  InstallEntry: String;
begin
  if CurStep = ssPostInstall then begin
    InstallEntry := ExpandConstant('{tmp}\Insta360_HW_payload\scripts\lifecycle_v3\Install.ps1');
    ResultCode := RunLifecycleAsync('Install', InstallEntry, SelectedInstallAction, False);
    if ResultCode <> 0 then begin
      RestoreExistingDisplayVersion();
      RaiseException(
        '安装验证失败，错误码：' + IntToStr(ResultCode) + '。原版本已自动回退。' + #13#10 +
        '详细日志：%LOCALAPPDATA%\Insta360_HW\logs\install_latest.log');
    end;
    SetupLifecycleSucceeded := True;
  end;
end;

procedure DeinitializeSetup();
var
  ResultCode: Integer;
begin
  if SetupLifecycleSucceeded and MaintenanceUninstallAfterRepair then begin
    if not Exec(ExpandConstant('{uninstallexe}'), '', ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, ResultCode) then
      MsgBox('卸载组件已恢复，但无法启动。请从 Windows“已安装的应用”启动卸载。', mbError, MB_OK);
  end;
end;

function HasUninstallParameter(const Name: String): Boolean;
var
  Index: Integer;
begin
  Result := False;
  for Index := 1 to ParamCount do begin
    if CompareText(ParamStr(Index), Name) = 0 then begin
      Result := True;
      Exit;
    end;
  end;
end;

function InitializeUninstall(): Boolean;
var
  PurgeRequested: Boolean;
  PreserveRequested: Boolean;
begin
  PurgeRequested := HasUninstallParameter('/PURGEDATA');
  PreserveRequested := HasUninstallParameter('/PRESERVEDATA');
  if PurgeRequested and PreserveRequested then begin
    MsgBox('卸载参数冲突：/PURGEDATA 与 /PRESERVEDATA 不能同时使用。', mbError, MB_OK);
    Result := False;
    Exit;
  end;
  PreserveUserData := False;
  if PreserveRequested then
    PreserveUserData := True
  else if (not PurgeRequested) and (not UninstallSilent) then
    PreserveUserData := MsgBox(
      '默认卸载会删除程序、Cadence 集成、历史记录、处理文件、本机配置和用户插件。' + #13#10 + #13#10 +
      '是否改为保留用户数据？选择“是”将只删除程序和 Cadence 集成。',
      mbConfirmation,
      MB_YESNO or MB_DEFBUTTON2) = IDYES;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ScriptPath: String;
  Mode: String;
  ResultCode: Integer;
begin
  if (CurUninstallStep = usUninstall) and (not UninstallCleanupRan) then begin
    UninstallCleanupRan := True;
    if PreserveUserData then Mode := 'PreserveData' else Mode := 'PurgeData';
    ScriptPath := ExpandConstant('{app}\maintenance\Uninstall.ps1');
    UninstallProgressForm.ProgressBar.Position :=
      ScaleProgress(2, UninstallProgressForm.ProgressBar.Max);
    UninstallProgressForm.StatusLabel.Caption := '正在准备卸载';
    ResultCode := RunLifecycleAsync('Uninstall', ScriptPath, Mode, True);
    if ResultCode <> 0 then begin
      MsgBox(
        '卸载准备失败，程序文件尚未删除。错误码：' + IntToStr(ResultCode) + #13#10 +
        '详细日志：%LOCALAPPDATA%\Insta360_HW\logs\uninstall_latest.log',
        mbError,
        MB_OK);
      RaiseException('Lifecycle cleanup failed');
    end;
    UninstallProgressForm.ProgressBar.Position :=
      ScaleProgress(92, UninstallProgressForm.ProgressBar.Max);
    UninstallProgressForm.StatusLabel.Caption := '正在删除程序文件和快捷方式';
  end;

  if CurUninstallStep = usPostUninstall then begin
    UninstallProgressForm.ProgressBar.Position :=
      ScaleProgress(100, UninstallProgressForm.ProgressBar.Max);
    UninstallProgressForm.StatusLabel.Caption := '卸载完成';
    if not UninstallSilent then
      MsgBox('卸载完成。点击“确定”关闭卸载程序。', mbInformation, MB_OK);
  end;
end;
