; Installeur Windows ADMI (Inno Setup).
; Prérequis : avoir construit dist\ADMI\ avec PyInstaller (pyinstaller admi.spec),
; puis compiler ce script avec Inno Setup :  ISCC.exe windows\ADMI.iss
; Résultat : dist\ADMI-Setup.exe

#define AppName "ADMI"
#define AppVersion "1.0.0"
#define AppPublisher "ADMI"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=ADMI-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "..\dist\ADMI\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\ADMI"; Filename: "{app}\ADMI.exe"
Name: "{autodesktop}\ADMI"; Filename: "{app}\ADMI.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ADMI.exe"; Description: "Lancer ADMI"; Flags: nowait postinstall skipifsilent
