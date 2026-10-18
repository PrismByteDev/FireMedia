; Compile with Inno Setup 6 after build.ps1 succeeds.
#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef AppNumericVersion
  #error Pass /DAppNumericVersion=<major.minor.patch.0>
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
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "mediafiles"; Description: "Register FireMedia in Open With for media files (Windows lets you choose the default app)"; Flags: unchecked

[Files]
Source: "..\..\dist\FireMedia\*"; DestDir: "{app}\versions\{#AppVersion}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\dist\FireMediaUpdate.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\FireMediaUpdate.exe"; DestDir: "{app}"; DestName: "FireMedia.exe"; Flags: ignoreversion
Source: "install.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\FireMedia"; Filename: "{app}\FireMedia.exe"; Parameters: "launch"; AppUserModelID: "PrismByteDev.FireMedia"
Name: "{autodesktop}\FireMedia"; Filename: "{app}\FireMedia.exe"; Parameters: "launch"; Tasks: desktopicon; AppUserModelID: "PrismByteDev.FireMedia"

[Registry]
Root: HKCU; Subkey: "Software\Classes\firemedia-update"; ValueType: string; ValueData: "URL:FireMedia Update"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\firemedia-update"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\firemedia-update\shell\open\command"; ValueType: string; ValueData: """{app}\FireMediaUpdate.exe"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\PrismByteDev.FireMedia"; ValueType: string; ValueName: "DisplayName"; ValueData: "FireMedia"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AppUserModelId\PrismByteDev.FireMedia"; ValueType: string; ValueName: "IconUri"; ValueData: "{app}\FireMedia.exe"
Root: HKCU; Subkey: "Software\Classes\FireMedia.Media"; ValueType: string; ValueData: "FireMedia media file"; Tasks: mediafiles; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\FireMedia.Media\DefaultIcon"; ValueType: string; ValueData: "{app}\FireMedia.exe,0"; Tasks: mediafiles
Root: HKCU; Subkey: "Software\Classes\FireMedia.Media\shell\open\command"; ValueType: string; ValueData: """{app}\FireMedia.exe"" launch ""%1"""; Tasks: mediafiles
Root: HKCU; Subkey: "Software\Classes\.mp3\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.flac\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.wav\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.ogg\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.mp4\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.mkv\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.webm\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.m3u\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\.m3u8\OpenWithProgids"; ValueType: string; ValueName: "FireMedia.Media"; ValueData: ""; Tasks: mediafiles; Flags: uninsdeletevalue

[Run]
Filename: "{app}\FireMedia.exe"; Parameters: "launch"; Description: "Launch FireMedia"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{app}\FireMediaUpdate.exe"; Parameters: "disable-task"; Flags: runhidden waituntilterminated

[UninstallDelete]
Type: filesandordirs; Name: "{app}\versions"
Type: files; Name: "{app}\current.json"

[Code]
var UpdatesPage: TInputOptionWizardPage;
procedure InitializeWizard;
begin
  UpdatesPage := CreateInputOptionPage(wpSelectTasks, 'FireMedia updates',
    'Choose how FireMedia checks for updates',
    'Background updates run every ten minutes while you are signed in, even when FireMedia is closed. Playback continues until you restart. Notify is the default; you can change this in Settings.', True, False);
  UpdatesPage.Add('Background updates');
  UpdatesPage.Add('Update on launch');
  UpdatesPage.Add('Notify me before updating');
  UpdatesPage.Add('Disabled');
  UpdatesPage.SelectedValueIndex := 2;
end;
procedure CurStepChanged(CurStep: TSetupStep);
var Code: Integer; Mode, Params: String;
begin
  if CurStep = ssPostInstall then begin
    if not Exec(ExpandConstant('{app}\FireMediaUpdate.exe'), 'initialize {#AppVersion}', '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      RaiseException('Could not initialize FireMedia. Run setup again to repair the installation.');
    Mode := '';
    if not WizardSilent then begin
      case UpdatesPage.SelectedValueIndex of
        0: Mode := 'background';
        1: Mode := 'launch';
        2: Mode := 'notify';
        3: Mode := 'disabled';
      end;
    end;
    Params := 'configure ' + Mode;
    if not Exec(ExpandConstant('{app}\FireMediaUpdate.exe'), Params, '', SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
      MsgBox('FireMedia installed, but background update setup failed. Choose an update mode in Settings to retry.', mbInformation, MB_OK);
  end;
end;
