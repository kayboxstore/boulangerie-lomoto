#define MyAppName "Boulangerie Lomoto Démo"
#define MyAppVersion "1.3.22"
#define MyAppPublisher "Kay Box Store"
#define MyAppExeName "Boulangerie Lomoto Demo.exe"
#define MyAppIdEscaped "{{7C0A2A65-0E34-4F7D-9C12-70D719F1E3D2}"
#define MyOutputBaseFilename "BoulangerieLomotoDemoSetup"

[Setup]
AppId={#MyAppIdEscaped}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=output\{#MyAppVersion}-demo
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
Source: "..\dist\Boulangerie Lomoto Demo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName}"; Flags: nowait postinstall skipifsilent shellexec; Verb: "runas"
