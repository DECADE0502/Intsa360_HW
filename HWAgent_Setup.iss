#define MyAppName "Insta360硬件提效平台"
#ifndef MyAppVersion
  #define MyAppVersion "0.3.2"
#endif
#define MyAppPublisher "Insta360"
#define MyAppExeName "Insta360_HW.exe"
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

[Languages]
Name: "chinesesimp"; MessagesFile: "installer\ChineseSimplified.isl"

[Files]
Source: "{#ReleaseDir}\scripts\lifecycle\SetupTransaction.ps1"; DestName: "SetupTransaction.ps1"; Flags: dontcopy
Source: "{#ReleaseDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Excludes: "data\*,config\local.json,plugins\user\*"

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
  MAINTENANCE_REPAIR = 0;
  MAINTENANCE_UNINSTALL = 1;
  MAINTENANCE_CANCEL = 2;

var
  PreserveUserData: Boolean;
  UninstallCleanupRan: Boolean;
  ExistingInstallDetected: Boolean;
  ExistingRuntimeHealthy: Boolean;
  ExistingVersion: String;
  ExistingInstallDir: String;
  ExistingUninstaller: String;
  ExistingInstallPage: TInputOptionWizardPage;
  MaintenanceCloseRequested: Boolean;
  MaintenanceUninstallRequested: Boolean;
  SetupTransactionHelper: String;
  SetupTransactionStarted: Boolean;
  SetupLifecycleSucceeded: Boolean;

function DetectExistingInstall(): Boolean;
var
  FoundRegistry: Boolean;
  RegisteredUninstaller: String;
begin
  ExistingVersion := '';
  ExistingInstallDir := '';
  ExistingUninstaller := '';
  FoundRegistry := RegKeyExists(HKLM64, UninstallKey);
  if not FoundRegistry then
    FoundRegistry := RegKeyExists(HKLM32, UninstallKey);

  if FoundRegistry then begin
    if not RegQueryStringValue(HKLM64, UninstallKey, 'InstallLocation', ExistingInstallDir) then
      RegQueryStringValue(HKLM32, UninstallKey, 'InstallLocation', ExistingInstallDir);
    if not RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', ExistingVersion) then
      RegQueryStringValue(HKLM32, UninstallKey, 'DisplayVersion', ExistingVersion);
  end;
  if ExistingInstallDir = '' then
    ExistingInstallDir := ExpandConstant('{autopf}\Insta360\HWAgent');

  ExistingUninstaller := AddBackslash(ExistingInstallDir) + 'unins000.exe';
  if FoundRegistry and (not FileExists(ExistingUninstaller)) then begin
    RegisteredUninstaller := '';
    if not RegQueryStringValue(HKLM64, UninstallKey, 'UninstallString', RegisteredUninstaller) then
      RegQueryStringValue(HKLM32, UninstallKey, 'UninstallString', RegisteredUninstaller);
    if RegisteredUninstaller <> '' then
      ExistingUninstaller := RemoveQuotes(RegisteredUninstaller);
  end;

  Result := FoundRegistry or DirExists(ExistingInstallDir);
  if not Result then
    Exit;

  if ExistingVersion = '' then
    ExistingVersion := '未知';
  ExistingRuntimeHealthy :=
    FileExists(AddBackslash(ExistingInstallDir) + 'Insta360_HW.exe') and
    FileExists(AddBackslash(ExistingInstallDir) + 'VERSION') and
    FileExists(AddBackslash(ExistingInstallDir) + 'install_manifest.json') and
    FileExists(AddBackslash(ExistingInstallDir) + 'scripts\lifecycle\Install.ps1') and
    FileExists(ExistingUninstaller);
end;

procedure InitializeWizard();
var
  Detail: String;
  RepairLabel: String;
begin
  ExistingInstallDetected := DetectExistingInstall();
  if ExistingInstallDetected then begin
    if not ExistingRuntimeHealthy then begin
      Detail :=
        '已检测到已安装版本 ' + ExistingVersion + '。' + #13#10 + #13#10 +
        '安装记录存在，但程序文件不完整。建议先执行修复/重装，以恢复完整程序和标准卸载器。';
    end else if ExistingVersion = '{#MyAppVersion}' then begin
      Detail :=
        '已检测到已安装版本 ' + ExistingVersion + '。' + #13#10 + #13#10 +
        '当前安装包版本相同，可以修复/重装，也可以直接卸载。';
    end else begin
      Detail :=
        '已检测到已安装版本 ' + ExistingVersion + '。' + #13#10 + #13#10 +
        '可以安装版本 {#MyAppVersion}，也可以直接卸载当前版本。';
    end;
  end else begin
    Detail := '未检测到已有安装，将执行全新安装。';
  end;

  RepairLabel := '修复/重装 Insta360硬件提效平台 {#MyAppVersion}（保留用户数据）';
  ExistingInstallPage := CreateInputOptionPage(
    wpWelcome,
    '维护 Insta360硬件提效平台',
    Detail,
    '请选择要执行的操作：',
    True,
    False);
  ExistingInstallPage.Add(RepairLabel);
  ExistingInstallPage.Add('卸载 Insta360硬件提效平台（将先修复卸载组件）');
  ExistingInstallPage.Add('取消，不做任何更改');
  ExistingInstallPage.SelectedValueIndex := MAINTENANCE_REPAIR;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = ExistingInstallPage.ID) and (not ExistingInstallDetected);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (not ExistingInstallDetected) or (CurPageID <> ExistingInstallPage.ID) then
    Exit;

  case ExistingInstallPage.SelectedValueIndex of
    MAINTENANCE_REPAIR:
      begin
        MaintenanceUninstallRequested := False;
        Result := True;
      end;
    MAINTENANCE_UNINSTALL:
      begin
        MaintenanceUninstallRequested := True;
        Result := True;
      end;
    MAINTENANCE_CANCEL:
      begin
        Result := False;
        MaintenanceUninstallRequested := False;
        MaintenanceCloseRequested := True;
        WizardForm.Close;
      end;
  end;
end;

function ShouldLaunchPlatform(): Boolean;
begin
  Result := not MaintenanceUninstallRequested;
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

function RunSetupTransaction(const Action: String): Integer;
var
  ResultCode: Integer;
  Parameters: String;
begin
  if SetupTransactionHelper = '' then begin
    try
      ExtractTemporaryFile('SetupTransaction.ps1');
      SetupTransactionHelper := ExpandConstant('{tmp}\SetupTransaction.ps1');
    except
      Result := 9002;
      Exit;
    end;
  end;

  Parameters :=
    '-Action ' + Action + ' ' +
    '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
    '-StateRoot "' + StateRoot() + '"';
  if not Exec(
    'powershell.exe',
    '-NoProfile -ExecutionPolicy Bypass -File "' + SetupTransactionHelper + '" ' + Parameters,
    ExpandConstant('{tmp}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode) then
    ResultCode := 9001;
  Result := ResultCode;
end;

function RunSetupLifecycle(const ScriptPath, Parameters, StatusText: String): Integer;
var
  ResultCode: Integer;
begin
  WizardForm.StatusLabel.Caption := StatusText;
  WizardForm.ProgressGauge.Visible := True;
  WizardForm.ProgressGauge.Style := npbstMarquee;
  try
    if not Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" ' + Parameters,
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode) then
      ResultCode := 9001;
  finally
    WizardForm.ProgressGauge.Style := npbstNormal;
  end;
  Result := ResultCode;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExistingRecovery: String;
  ExistingLifecycle: String;
  ExistingWrapper: String;
  Parameters: String;
  ResultCode: Integer;
begin
  Result := '';
  NeedsRestart := False;
  ExistingRecovery := ExpandConstant('{app}\scripts\lifecycle\Recover.ps1');
  ExistingLifecycle := ExpandConstant('{app}\scripts\lifecycle\Install.ps1');
  ExistingWrapper := ExpandConstant('{app}\uninstall.ps1');
  WizardForm.StatusLabel.Caption := '正在停止旧版本并迁移用户数据...';

  ResultCode := RunSetupTransaction('Recover');
  if ResultCode <> 0 then begin
    Result :=
      '检测到未完成的安装，但自动恢复失败，未对现有版本执行任何新操作。错误码：' +
      IntToStr(ResultCode) + #13#10 +
      '请重新启动电脑后再次运行 Setup。';
    Exit;
  end;
  SetupTransactionStarted := False;

  ResultCode := 0;
  if FileExists(ExistingRecovery) then begin
    Parameters :=
      '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
      '-StateRoot "' + StateRoot() + '" -NoRestart';
    if not Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExistingRecovery + '" ' + Parameters,
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode) then
      ResultCode := 9001;
    if ResultCode <> 0 then begin
      Result :=
        '检测到未完成的更新，但自动恢复失败，安装尚未开始。' + #13#10 +
        '请重新启动电脑后再试，或将 %LOCALAPPDATA%\Insta360_HW 中的日志发送给维护人员。';
      Exit;
    end;
  end;

  ResultCode := RunSetupTransaction('Begin');
  if ResultCode <> 0 then begin
    RunSetupTransaction('Rollback');
    Result :=
      '无法创建旧版本安全备份，安装尚未开始。错误码：' + IntToStr(ResultCode) + #13#10 +
      '请确认磁盘空间充足后重试。';
    Exit;
  end;
  SetupTransactionStarted := True;

  if FileExists(ExistingLifecycle) then begin
    Parameters :=
      '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
      '-StateRoot "' + StateRoot() + '" -PrepareUpgrade -NoStart -SkipCadence';
    if not Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExistingLifecycle + '" ' + Parameters,
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode) then
      ResultCode := 9001;
  end else if FileExists(ExistingWrapper) then begin
    Parameters :=
      '-PreUpgrade -InstallDir "' + ExpandConstant('{app}') + '" ' +
      '-StateRoot "' + StateRoot() + '"';
    if not Exec(
      'powershell.exe',
      '-NoProfile -ExecutionPolicy Bypass -File "' + ExistingWrapper + '" ' + Parameters,
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode) then
      ResultCode := 9001;
  end else begin
    ResultCode := 0;
  end;

  if ResultCode <> 0 then begin
    Result :=
      '无法安全停止旧版本或迁移用户数据，安装尚未开始。' + #13#10 +
      '请关闭平台后重试，并查看 %LOCALAPPDATA%\Insta360_HW\data\reports\runtime 中的日志。';
    Exit;
  end;

  WizardForm.StatusLabel.Caption := '正在准备全新运行时文件...';
  ResultCode := RunSetupTransaction('PrepareReplace');
  if ResultCode <> 0 then begin
    Result :=
      '无法安全替换旧版本文件，Setup 将恢复原版本。错误码：' + IntToStr(ResultCode) + #13#10 +
      '请关闭平台后重试。';
    Exit;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Parameters: String;
  LifecycleStatus: String;
begin
  if CurStep = ssPostInstall then begin
    Parameters :=
      '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
      '-StateRoot "' + StateRoot() + '"';
    if MaintenanceUninstallRequested then begin
      Parameters := Parameters + ' -NoStart -SkipCadence';
      LifecycleStatus := '正在刷新并验证标准卸载组件...';
    end else begin
      LifecycleStatus := '正在初始化用户数据、部署 Cadence 集成并验证安装...';
    end;
    ResultCode := RunSetupLifecycle(
      ExpandConstant('{app}\scripts\lifecycle\Install.ps1'),
      Parameters,
      LifecycleStatus);
    if ResultCode <> 0 then
      RaiseException(
        '安装后验证失败，错误码：' + IntToStr(ResultCode) +
        '。Setup 将恢复原版本。' + #13#10 +
        '详细日志：%LOCALAPPDATA%\Insta360_HW\logs\install_latest.log');

    ResultCode := RunSetupTransaction('Commit');
    if ResultCode <> 0 then
      RaiseException(
        '安装事务提交失败，错误码：' + IntToStr(ResultCode) +
        '。Setup 将自动恢复旧版本。');
    SetupLifecycleSucceeded := True;
  end;
end;

procedure DeinitializeSetup();
var
  ResultCode: Integer;
begin
  if SetupTransactionStarted and (not SetupLifecycleSucceeded) then begin
    ResultCode := RunSetupTransaction('Rollback');
    if ResultCode <> 0 then
      MsgBox(
        '安装未完成，自动恢复旧版本失败。错误码：' + IntToStr(ResultCode) + #13#10 +
        '请重新启动电脑后再次运行 Setup，Setup 会优先继续恢复。',
        mbError,
        MB_OK);
  end;

  if SetupLifecycleSucceeded and MaintenanceUninstallRequested then begin
    if not Exec(
      ExpandConstant('{uninstallexe}'),
      '',
      ExpandConstant('{app}'),
      SW_SHOWNORMAL,
      ewNoWait,
      ResultCode) then
      MsgBox(
        '卸载组件已修复，但无法启动标准卸载器。系统错误码：' + IntToStr(ResultCode) +
        '。请从 Windows“已安装的应用”启动卸载。',
        mbError,
        MB_OK);
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
    MsgBox(
      '卸载参数冲突：/PURGEDATA 与 /PRESERVEDATA 不能同时使用。',
      mbError,
      MB_OK);
    Result := False;
    Exit;
  end else if PurgeRequested then begin
    PreserveUserData := False;
  end else if PreserveRequested or UninstallSilent then begin
    PreserveUserData := True;
  end else begin
    PreserveUserData :=
      MsgBox(
        '是否保留历史记录、已处理文件、本机配置和用户插件？' + #13#10 + #13#10 +
        '选择“是”：删除程序和 Cadence 集成，保留用户数据，重装后可继续使用。' + #13#10 +
        '选择“否”：同时永久删除所有 Insta360_HW 本机数据。',
        mbConfirmation,
        MB_YESNO) = IDYES;
  end;
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UninstallRecovery: String;
  RecoveryParameters: String;
  RecoveryCode: Integer;
  ScriptPath: String;
  Parameters: String;
  Mode: String;
  ResultCode: Integer;
begin
  if (CurUninstallStep = usUninstall) and not UninstallCleanupRan then begin
    UninstallCleanupRan := True;
    if PreserveUserData then
      Mode := 'PreserveData'
    else
      Mode := 'PurgeData';

    UninstallRecovery := ExpandConstant('{app}\scripts\lifecycle\Recover.ps1');
    if FileExists(UninstallRecovery) then begin
      RecoveryParameters :=
        '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
        '-StateRoot "' + StateRoot() + '" -NoRestart';
      UninstallProgressForm.ProgressBar.Position := 10;
      UninstallProgressForm.StatusLabel.Caption := '正在检查并恢复未完成的更新...';
      if not Exec(
        'powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + UninstallRecovery + '" ' + RecoveryParameters,
        ExpandConstant('{app}'),
        SW_HIDE,
        ewWaitUntilTerminated,
        RecoveryCode) then
        RecoveryCode := 9001;
      if RecoveryCode <> 0 then begin
        MsgBox(
          '检测到未完成的更新，但自动恢复失败。程序文件尚未删除。错误码：' + IntToStr(RecoveryCode),
          mbError,
          MB_OK);
        RaiseException('Lifecycle recovery failed before uninstall');
      end;
    end;

    ScriptPath := ExpandConstant('{app}\scripts\lifecycle\Uninstall.ps1');
    if not FileExists(ScriptPath) then begin
      MsgBox(
        '卸载组件缺失，无法确认 Cadence 集成已安全移除。请先使用 Setup 执行修复安装，再重新卸载。',
        mbError,
        MB_OK);
      RaiseException('Lifecycle uninstall component is missing');
    end;

    Parameters :=
      '-InstallRoot "' + ExpandConstant('{app}') + '" ' +
      '-StateRoot "' + StateRoot() + '" -Mode ' + Mode;
    UninstallProgressForm.StatusLabel.Caption := '正在停止平台并移除 Cadence 集成...';
    UninstallProgressForm.ProgressBar.Style := npbstMarquee;
    try
      if not Exec(
        'powershell.exe',
        '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" ' + Parameters,
        ExpandConstant('{app}'),
        SW_HIDE,
        ewWaitUntilTerminated,
        ResultCode) then
        ResultCode := 9001;
    finally
      UninstallProgressForm.ProgressBar.Style := npbstNormal;
    end;

    if ResultCode <> 0 then begin
      MsgBox(
        '卸载准备失败，程序文件尚未删除。错误码：' + IntToStr(ResultCode) + #13#10 +
        '详细日志：%LOCALAPPDATA%\Insta360_HW\logs\uninstall_latest.log',
        mbError,
        MB_OK);
      RaiseException('Lifecycle cleanup failed');
    end;
    UninstallProgressForm.ProgressBar.Position := 75;
    UninstallProgressForm.StatusLabel.Caption := '正在删除程序文件和快捷方式...';
  end;

  if CurUninstallStep = usPostUninstall then begin
    UninstallProgressForm.ProgressBar.Position := 100;
    if not UninstallSilent then
      MsgBox('卸载完成。点击“确定”关闭卸载程序。', mbInformation, MB_OK);
  end;
end;
