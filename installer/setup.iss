#ifndef MyAppName
  #define MyAppName "Boulangerie Lomoto"
#endif
#ifndef MyAppVersion
#define MyAppVersion "1.3.15"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "Kay Box Store"
#endif
#ifndef MyAppExeName
  #define MyAppExeName "Boulangerie Lomoto.exe"
#endif
#ifndef MyAppIdEscaped
  #define MyAppIdEscaped "{{D8D3424B-4C91-4C10-A7F5-84AB2F483F11}"
#endif
#ifndef MyAppIdValue
  #define MyAppIdValue "{D8D3424B-4C91-4C10-A7F5-84AB2F483F11}"
#endif
#ifndef MyOutputBaseFilename
  #define MyOutputBaseFilename "BoulangerieLomotoSetup"
#endif

[Setup]
AppId={#MyAppIdEscaped}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=output\{#MyAppVersion}
OutputBaseFilename={#MyOutputBaseFilename}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\boulangerie_app\assets\logo-boulangerie-lomoto.ico
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\Boulangerie Lomoto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec; Verb: "runas"

[Code]
const
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppIdValue}_is1';
  WindowsServiceName = 'BoulangerieLomotoCentralServer';
  MainExeImageName = 'Boulangerie Lomoto.exe';
  ServiceExeImageName = 'Boulangerie Lomoto Service.exe';

var
  RestartWindowsServiceAfterInstall: Boolean;

function RunHiddenCommand(const Parameters: String): Integer;
var
  ResultCode: Integer;
begin
  if Exec(ExpandConstant('{cmd}'), '/C ' + Parameters, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    Result := ResultCode
  else
    Result := -1;
end;

function IsWindowsServiceInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\' + WindowsServiceName);
end;

procedure StopInstalledProcesses();
begin
  RestartWindowsServiceAfterInstall := IsWindowsServiceInstalled();

  RunHiddenCommand('sc.exe stop "' + WindowsServiceName + '"');
  Sleep(3000);
  RunHiddenCommand('taskkill /F /T /IM "' + ServiceExeImageName + '"');
  RunHiddenCommand('taskkill /F /T /IM "' + MainExeImageName + '"');
  Sleep(1500);
end;

procedure RestartWindowsServiceIfNeeded();
begin
  if RestartWindowsServiceAfterInstall then
  begin
    RunHiddenCommand('sc.exe start "' + WindowsServiceName + '"');
    Sleep(2000);
  end;
end;

function GetInstalledVersion(var Version: String): Boolean;
begin
  Result :=
    RegQueryStringValue(HKLM, UninstallRegKey, 'DisplayVersion', Version) or
    RegQueryStringValue(HKCU, UninstallRegKey, 'DisplayVersion', Version);
end;

function NextVersionPart(var VersionText: String): Integer;
var
  DotPos: Integer;
  PartText: String;
begin
  DotPos := Pos('.', VersionText);
  if DotPos > 0 then
  begin
    PartText := Copy(VersionText, 1, DotPos - 1);
    Delete(VersionText, 1, DotPos);
  end
  else
  begin
    PartText := VersionText;
    VersionText := '';
  end;

  if PartText = '' then
    Result := 0
  else
    Result := StrToIntDef(PartText, 0);
end;

function CompareVersionStrings(Version1, Version2: String): Integer;
var
  Part1, Part2: Integer;
begin
  Version1 := Trim(Version1);
  Version2 := Trim(Version2);

  while (Version1 <> '') or (Version2 <> '') do
  begin
    Part1 := NextVersionPart(Version1);
    Part2 := NextVersionPart(Version2);

    if Part1 < Part2 then
    begin
      Result := -1;
      Exit;
    end;

    if Part1 > Part2 then
    begin
      Result := 1;
      Exit;
    end;
  end;

  Result := 0;
end;

function InitializeSetup(): Boolean;
var
  InstalledVersion: String;
  VersionComparison: Integer;
  PromptText: String;
begin
  Result := True;

  if not GetInstalledVersion(InstalledVersion) then
    Exit;

  VersionComparison := CompareVersionStrings(InstalledVersion, '{#MyAppVersion}');

  if VersionComparison < 0 then
  begin
    PromptText :=
      'La version ' + InstalledVersion + ' est déjà installée.' + #13#10#13#10 +
      'Voulez-vous la mettre ? jour vers la version {#MyAppVersion} ?' + #13#10#13#10 +
      'Oui : lancer la mise à jour.' + #13#10 +
      'Non : conserver la version déjà installée.';
  end
  else
  if VersionComparison = 0 then
  begin
    PromptText :=
      'La version {#MyAppVersion} est déjà installée.' + #13#10#13#10 +
      'Voulez-vous la réinstaller avec ce setup ?' + #13#10#13#10 +
      'Oui : remplacer la version actuelle.' + #13#10 +
      'Non : continuer a utiliser la version déjà installée.';
  end
  else
  begin
    PromptText :=
      'Une version plus récente (' + InstalledVersion + ') est déjà installée.' + #13#10#13#10 +
      'Voulez-vous la remplacer par cette version {#MyAppVersion} ?' + #13#10#13#10 +
      'Oui : installer cette version ? la place.' + #13#10 +
      'Non : continuer a utiliser la version déjà installée.';
  end;

  if MsgBox(PromptText, mbConfirmation, MB_YESNO) = IDNO then
    Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StopInstalledProcesses()
  else if CurStep = ssPostInstall then
    RestartWindowsServiceIfNeeded();
end;
