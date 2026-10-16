; Compile with Inno Setup 6 after build.ps1 succeeds.
#ifndef AppVersion
  #error Pass /DAppVersion=<version> from firemedia.__version__
#endif
#ifndef AppNumericVersion
  #error Pass /DAppNumericVersion=<major.minor.patch.0> from build.ps1
#endif
[Setup]
AppId={{7C2DA172-3186-46D7-A08A-C24BB32401C0}
AppName=FireMedia
AppVersion={#AppVersion}
VersionInfoVersion={#AppNumericVersion}
AppPublisher=FireMedia contributors
DefaultDirName={localappdata}\Programs\FireMedia
DefaultGroupName=FireMedia
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=FireMedia-{#AppVersion}-windows-x64-setup
SetupIconFile=firemedia.ico
UninstallDisplayIcon={app}\FireMedia.exe
LicenseFile=..\..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\..\dist\FireMedia\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\FireMedia"; Filename: "{app}\FireMedia.exe"
Name: "{autodesktop}\FireMedia"; Filename: "{app}\FireMedia.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FireMedia.exe"; Description: "Launch FireMedia"; Flags: nowait postinstall skipifsilent
