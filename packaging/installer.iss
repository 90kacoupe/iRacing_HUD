; Inno Setup script for the Sim Racing HUD installer.
; Built by the GitHub release workflow:  ISCC /DAppVersion=1.2.3 packaging\installer.iss
; Installs per user (no admin prompt), so updates can run quietly from inside the app.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Sim Racing HUD"
#define AppExe "SimRacingHUD.exe"
#define AppGuid "6E1B7A52-3C1D-4C55-9C2E-2B9F4E7D8A11"

[Setup]
AppId={{{#AppGuid}}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=90kacoupe
AppPublisherURL=https://github.com/90kacoupe/iRacing_HUD
AppUpdatesURL=https://github.com/90kacoupe/iRacing_HUD/releases
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SimRacingHUD-Setup-{#AppVersion}
SetupIconFile=hud.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start with Windows (waits in the tray; overlays only show while you drive)"; Check: not IsUpgrade
Name: "desktopicon"; Description: "Desktop shortcut"; Flags: unchecked; Check: not IsUpgrade

[InstallDelete]
; Clear out the old libraries on an update so nothing stale is left behind. Settings are elsewhere.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\SimRacingHUD\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\{#AppName} (demo)"; Filename: "{app}\{#AppExe}"; Parameters: "--demo"; Comment: "Simulated data, no iRacing needed"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; WorkingDir: "{app}"; Tasks: startup

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#AppExe}"; Flags: runhidden; RunOnceId: "StopHUD"

[UninstallDelete]
Type: files; Name: "{userstartup}\{#AppName}.lnk"
Type: files; Name: "{userstartup}\{#AppName}.bat"

[Code]
function IsUpgrade: Boolean;
begin
  Result := RegKeyExists(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{' + '{#AppGuid}' + '}_is1');
end;
