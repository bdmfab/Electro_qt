; Inno Setup 6 script: iscc packaging\electro_qt.iss   (after PyInstaller has made dist\Electro_qt)
#define AppName "Electro_qt"
#ifndef AppVersion
  #define AppVersion "0.24.0"
#endif

[Setup]
AppId={{6C1B0E5A-52E2-4B8E-9E55-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=Electro_qt_Setup
Compression=lzma2
SolidCompression=yes
SetupIconFile=..\electro\ui\resources\icon.ico
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; Settings and the block library live in the user's profile (%APPDATA%\Electro_qt, registry), not here,
; so an upgrade or uninstall never touches them.

[Files]
Source: "..\dist\Electro_qt\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\Electro_qt.exe"
Name: "{group}\{#AppName} manual"; Filename: "{app}\docs\Electro_qt_Manual.pdf"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Electro_qt.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop icon"; Flags: unchecked

[Run]
Filename: "{app}\Electro_qt.exe"; Description: "Start {#AppName}"; Flags: nowait postinstall skipifsilent
