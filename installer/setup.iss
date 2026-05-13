#define MyAppName "Boulangerie Lomoto"
#define MyAppVersion "1.0.9"
#define MyAppPublisher "Kay Box Store"
#define MyAppExeName "Boulangerie Lomoto.exe"
#define MyAppIdEscaped "{{D8D3424B-4C91-4C10-A7F5-84AB2F483F11}"
#define MyAppIdValue "{D8D3424B-4C91-4C10-A7F5-84AB2F483F11}"

[Setup]
AppId={#MyAppIdEscaped}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=output
OutputBaseFilename=BoulangerieLomotoSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Creer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\Boulangerie Lomoto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  UninstallRegKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppIdValue}_is1';

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
      'La version ' + InstalledVersion + ' est deja installee.' + #13#10#13#10 +
      'Voulez-vous la mettre a jour vers la version {#MyAppVersion} ?' + #13#10#13#10 +
      'Oui : lancer la mise a jour.' + #13#10 +
      'Non : conserver la version deja installee.';
  end
  else
  if VersionComparison = 0 then
  begin
    PromptText :=
      'La version {#MyAppVersion} est deja installee.' + #13#10#13#10 +
      'Voulez-vous la reinstaller avec ce setup ?' + #13#10#13#10 +
      'Oui : remplacer la version actuelle.' + #13#10 +
      'Non : continuer a utiliser la version deja installee.';
  end
  else
  begin
    PromptText :=
      'Une version plus recente (' + InstalledVersion + ') est deja installee.' + #13#10#13#10 +
      'Voulez-vous la remplacer par cette version {#MyAppVersion} ?' + #13#10#13#10 +
      'Oui : installer cette version a la place.' + #13#10 +
      'Non : continuer a utiliser la version deja installee.';
  end;

  if MsgBox(PromptText, mbConfirmation, MB_YESNO) = IDNO then
    Result := False;
end;
