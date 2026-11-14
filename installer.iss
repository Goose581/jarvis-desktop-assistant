#ifndef MyAppVersion
  #define MyAppVersion "1.6.4"
#endif
#define MyAppName "J.A.R.V.I.S."

[Setup]
AppId={{A19D93F8-DCB4-4D38-9D1B-3A2DF1B8C501}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Goose581
DefaultDirName={localappdata}\Programs\JARVIS
DefaultGroupName=JARVIS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output
OutputBaseFilename=JARVIS-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayName=J.A.R.V.I.S. Desktop Assistant
UninstallDisplayIcon={app}\JARVIS-Launcher.exe
SetupLogging=yes
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\JARVIS-Launcher.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\update_config.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\JARVIS\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; The official, Authenticode-verified Ollama setup is embedded in the single JARVIS-Setup.exe.
Source: "vendor\OllamaSetup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{autoprograms}\JARVIS\J.A.R.V.I.S."; Filename: "{app}\JARVIS-Launcher.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\J.A.R.V.I.S."; Filename: "{app}\JARVIS-Launcher.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
; Install Ollama for the current Windows user only when it is not already present.
; Ollama's own Windows installer supports these silent, non-admin switches.
Filename: "{tmp}\OllamaSetup.exe"; Parameters: "/VERYSILENT /NORESTART /SUPPRESSMSGBOXES"; StatusMsg: "Installing the local Ollama AI engine..."; Flags: runhidden waituntilterminated; Check: not IsOllamaInstalled
Filename: "{app}\JARVIS-Launcher.exe"; Description: "Launch J.A.R.V.I.S."; Flags: postinstall nowait skipifsilent

[Code]
function IsOllamaInstalled(): Boolean;
var
  ResultCode: Integer;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe'));
  if not Result then
  begin
    if Exec(ExpandConstant('{sys}\where.exe'), 'ollama.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      Result := (ResultCode = 0);
  end;
end;
