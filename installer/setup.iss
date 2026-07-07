#ifndef MyAppName
  #define MyAppName "Boulangerie Lomoto"
#endif
#ifndef MyAppVersion
#define MyAppVersion "1.5.3"
#endif
#ifndef MyAppPublisher
  #define MyAppPublisher "GIS"
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
#ifndef MySourceDir
  #define MySourceDir "..\dist\Boulangerie Lomoto"
#endif
#ifndef MyAppDataDirName
  #define MyAppDataDirName "BoulangerieLomoto"
#endif
#ifndef MyWindowsServiceName
  #define MyWindowsServiceName "BoulangerieLomotoCentralServer"
#endif
#ifndef MyServiceExeName
  #define MyServiceExeName "Boulangerie Lomoto Service.exe"
#endif
#ifndef MyFirewallRuleName
  #define MyFirewallRuleName "Boulangerie Lomoto Web Pro 8787"
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
Name: "servermode"; Description: "PC serveur principal - héberge la base et l'accès Web"; GroupDescription: "Type d'installation :"; Flags: exclusive
Name: "clientmode"; Description: "Poste client - se connecte au serveur principal existant"; GroupDescription: "Type d'installation :"; Flags: exclusive unchecked

[Files]
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\deploy\email-settings.example.json"; DestDir: "{commonappdata}\{#MyAppDataDirName}"; DestName: "email-settings.example.json"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\sauvegarde-automatique-quotidienne.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\sauvegarde-externe-hebdomadaire.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\surveiller-service-lomoto.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\installer-taches-production-lomoto.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\tester-restauration-sauvegarde-lomoto.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode
Source: "..\scripts\verifier-taches-production-lomoto.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion; Tasks: servermode

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyFirewallRuleName}"""; Flags: runhidden; Tasks: servermode
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\scripts\installer-taches-production-lomoto.ps1"" -NoElevate"; Flags: runhidden; Tasks: servermode
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec; Verb: "runas"

[Code]
const
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppIdValue}_is1';
  WindowsServiceName = '{#MyWindowsServiceName}';
  MainExeImageName = '{#MyAppExeName}';
  ServiceExeImageName = '{#MyServiceExeName}';
  FirewallRuleName = '{#MyFirewallRuleName}';
  ServerMarkerName = 'server-installation.flag';

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
var
  ResultCode: Integer;
begin
  if not IsWindowsServiceInstalled() then
  begin
    Exec(
      ExpandConstant('{app}\' + ServiceExeImageName),
      '--startup auto install',
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
  end;
  RunHiddenCommand('sc.exe config "' + WindowsServiceName + '" start= auto');
  RunHiddenCommand('sc.exe start "' + WindowsServiceName + '"');
  Sleep(2000);
end;

procedure ConfigureInstallationMode();
var
  MarkerPath: String;
begin
  MarkerPath := ExpandConstant('{app}\' + ServerMarkerName);
  if WizardIsTaskSelected('servermode') then
  begin
    SaveStringToFile(MarkerPath, 'server', False);
    RestartWindowsServiceIfNeeded();
  end
  else
  begin
    DeleteFile(MarkerPath);
    RunHiddenCommand('sc.exe stop "' + WindowsServiceName + '"');
    RunHiddenCommand('sc.exe delete "' + WindowsServiceName + '"');
    RunHiddenCommand('netsh.exe advfirewall firewall delete rule name="' + FirewallRuleName + '"');
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
    ConfigureInstallationMode();
end;
