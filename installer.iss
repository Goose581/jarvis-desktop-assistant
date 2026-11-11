#define MyAppName "J.A.R.V.I.S."
#define MyAppVersion "1.0.0"

[Setup]
AppId={{A19D93F8-DCB4-4D38-9D1B-3A2DF1B8C501}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\JARVIS
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=JARVIS-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\JARVIS-Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\update_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\JARVIS\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\J.A.R.V.I.S."; Filename: "{app}\JARVIS-Launcher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\J.A.R.V.I.S."; Filename: "{app}\JARVIS-Launcher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\JARVIS-Launcher.exe"; Description: "Launch J.A.R.V.I.S."; Flags: postinstall nowait skipifsilent
