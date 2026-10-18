"""Per-user integration. No shell commands or downloaded code are evaluated."""
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime
from xml.sax.saxutils import escape

from .update_core import read_json, atomic_json, RELEASES
from .runtime import subprocess_options

TASK = 'FireMedia Updates'
AUMID = 'PrismByteDev.FireMedia'


def default_config():
    if sys.platform == 'win32':
        return Path(os.environ['APPDATA']) / 'FireMedia' / 'FireMedia' / 'updates.json'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'FireMedia' / 'FireMedia' / 'updates.json'


def run(args, **kwargs):
    return subprocess.run(args, check=True, timeout=25, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          **subprocess_options(), **kwargs)


def background_supported(kind):
    if kind == 'windows': return True
    if kind != 'appimage': return False
    try:
        run(['systemctl', '--user', 'show-environment'])
        return True
    except (OSError, subprocess.SubprocessError): return False


def systemd_quote(value):
    return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('\n', '\\n').replace('\r', '\\r') + '"'


def configure_background(kind, target, enabled, config=None):
    if kind == 'windows':
        if not enabled:
            # Deleting an absent task is harmless; no other task is touched.
            subprocess.run(['schtasks.exe', '/Delete', '/TN', TASK, '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=20, **subprocess_options())
            return
        user = os.environ.get('USERDOMAIN', '') + '\\' + getpass.getuser()
        executable = Path(target) / 'FireMediaUpdate.exe'
        start = datetime.now().replace(microsecond=0).isoformat()
        xml = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<Triggers><TimeTrigger><Repetition><Interval>PT10M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>{start}</StartBoundary><Enabled>true</Enabled></TimeTrigger><LogonTrigger><Enabled>true</Enabled><UserId>{escape(user)}</UserId></LogonTrigger></Triggers>
<Principals><Principal id="User"><UserId>{escape(user)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT10M</ExecutionTimeLimit></Settings>
<Actions Context="User"><Exec><Command>{escape(str(executable))}</Command><Arguments>check</Arguments><WorkingDirectory>{escape(str(target))}</WorkingDirectory></Exec></Actions></Task>'''
        fd, name = tempfile.mkstemp(suffix='.xml')
        try:
            with os.fdopen(fd, 'w', encoding='utf-16') as stream: stream.write(xml)
            run(['schtasks.exe', '/Create', '/TN', TASK, '/XML', name, '/F'])
        finally: Path(name).unlink(missing_ok=True)
    elif kind == 'appimage':
        directory = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'systemd/user'
        directory.mkdir(parents=True, exist_ok=True)
        timer = directory / 'firemedia-update.timer'; service = directory / 'firemedia-update.service'
        if enabled:
            if not background_supported(kind): raise ValueError('Background updates require a running systemd user session')
            service.write_text('[Unit]\nDescription=Check FireMedia updates\n[Service]\nType=oneshot\nExecStart=' + systemd_quote(target) + ' --update-worker\n', encoding='utf-8')
            timer.write_text('[Unit]\nDescription=Check FireMedia updates every ten minutes\n[Timer]\nOnStartupSec=30s\nOnUnitActiveSec=10min\nPersistent=false\n[Install]\nWantedBy=timers.target\n', encoding='utf-8')
            run(['systemctl', '--user', 'daemon-reload']); run(['systemctl', '--user', 'enable', '--now', 'firemedia-update.timer'])
        else:
            if timer.exists():
                run(['systemctl', '--user', 'disable', '--now', 'firemedia-update.timer'])
                timer.unlink(missing_ok=True); service.unlink(missing_ok=True)
                run(['systemctl', '--user', 'daemon-reload'])


def windows_notification(title, message, action='view'):
    """WinRT toast with a registered app identity and protocol/HTTPS activation."""
    import xml.etree.ElementTree as ET
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Classes\AppUserModelId\PrismByteDev.FireMedia') as identity:
        winreg.SetValueEx(identity,'DisplayName',0,winreg.REG_SZ,'FireMedia')
    if action not in ('view', 'install', 'restart'): raise ValueError('Invalid notification action')
    uri = RELEASES if action == 'view' else 'firemedia-update:' + action
    toast = ET.Element('toast', {'activationType': 'protocol', 'launch': uri})
    visual = ET.SubElement(toast, 'visual'); binding = ET.SubElement(visual, 'binding', {'template': 'ToastGeneric'})
    ET.SubElement(binding, 'text').text = title; ET.SubElement(binding, 'text').text = message
    actions = ET.SubElement(toast, 'actions')
    ET.SubElement(actions, 'action', {'content': {'view': 'View release', 'install': 'Update', 'restart': 'Restart FireMedia'}[action],
                                   'activationType': 'protocol', 'arguments': uri})
    # The script is fixed. Untrusted text is passed as XML on stdin, never code.
    script = '''$ErrorActionPreference='Stop';
[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime] > $null;
[Windows.Data.Xml.Dom.XmlDocument,Windows.Data.Xml.Dom.XmlDocument,ContentType=WindowsRuntime] > $null;
$xml=New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml([Console]::In.ReadToEnd());
$toast=[Windows.UI.Notifications.ToastNotification]::new($xml); $toast.Tag='updates'; $toast.Group='FireMedia';
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('PrismByteDev.FireMedia').Show($toast);'''
    run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
        input=ET.tostring(toast, encoding='unicode'), text=True, encoding='utf-8')


def native_notification(title, message, action='view'):
    try:
        if sys.platform == 'win32': windows_notification(title, message, action)
        else: run(['notify-send', '--app-name=FireMedia', '--icon=firemedia', title, message])
        return True
    except (OSError, ValueError, subprocess.SubprocessError): return False


def appimage_desktop(image):
    directory = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'applications'
    directory.mkdir(parents=True, exist_ok=True)
    import shutil
    icon=directory.parent/'icons/hicolor/128x128/apps/firemedia.png';icon.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(Path(__file__).parent/'assets/logo128.png',icon)
    command = str(Path(image).absolute()).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
    if '\n' in command or '\r' in command: raise ValueError('AppImage path contains a newline')
    mime = 'audio/mpeg;audio/flac;audio/ogg;audio/x-wav;video/mp4;video/x-matroska;video/webm;application/vnd.apple.mpegurl;audio/x-mpegurl;'
    (directory / (AUMID + '.desktop')).write_text(f'[Desktop Entry]\nType=Application\nName=FireMedia\nExec="{command}" %U\nIcon=firemedia\nTerminal=false\nCategories=AudioVideo;Player;\nMimeType={mime}\n', encoding='utf-8')
    try: run(['update-desktop-database', str(directory)])
    except (OSError, subprocess.SubprocessError): pass
