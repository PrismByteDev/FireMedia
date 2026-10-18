"""Short-lived updater for installer tasks, AppImage timers, and GUI requests."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from . import __version__
from .update_core import (AUTO_MODES, INTERVAL, RELEASES, atomic_json, current_version, discover,
                          install_appimage, install_windows, package_kind, read_json, update_lock, version)
from .update_platform import (configure_background, default_config, native_notification)
from .runtime import subprocess_options


def check(config, kind, target, running=__version__, *, force=False, install=False):
    with update_lock(config):
        state = read_json(config); mode = state.get('mode', 'notify')
        if mode == 'disabled' and not force: return {'status': 'disabled'}
        if kind == 'windows': running = current_version(target)
        if kind == 'appimage': running = state.get('installed_version', running)
        if kind == 'flatpak': return check_flatpak(config, running, force)
        payload, state = discover(config, force=force)
        if payload is None: return {'status': 'idle', 'message': 'No new signed release available.'}
        release = payload['version']
        if version(release) <= version(running): return {'status': 'current', 'message': 'FireMedia is up to date.'}
        status = 'available'
        if kind in ('windows', 'appimage') and (install or mode in ('background', 'launch')):
            asset = 'windows-x64' if kind == 'windows' else 'appimage-x64'
            if asset not in payload['assets']: raise ValueError('This release has no update package for your platform')
            if kind == 'windows': install_windows(target, payload)
            else: install_appimage(target, payload)
            state['installed_version'] = release; status = 'installed'
        marker = release + ':' + status
        if state.get('notified') != marker:
            action = 'restart' if status == 'installed' else 'install' if kind in ('windows', 'appimage') else 'view'
            message = (f'FireMedia {release} is installed. Restart FireMedia to use it.' if status == 'installed'
                       else f'FireMedia {release} is available.' + (' Choose Update to install it.' if action == 'install' else ' Open Releases to download it.'))
            if kind=='appimage' and status=='available':message=f'FireMedia {release} is available. Open FireMedia Settings → Updates to install it.'
            delivered = native_notification('FireMedia update', message, action if sys.platform == 'win32' else 'view')
            if delivered: state['notified'] = marker
        atomic_json(config, state)
        return {'status': status, 'version': release, 'url': RELEASES,
                'message': f'FireMedia {release} ' + ('installed. Restart to apply.' if status == 'installed' else 'is available.')}


def check_flatpak(config, running, force):
    """Only announce a version published in Flathub's appstream metadata."""
    from .update_core import APP_ID, fetch
    state = read_json(config)
    if not force and time.time() - state.get('checked', 0) < INTERVAL: return {'status': 'idle'}
    state['checked'] = time.time(); atomic_json(config, state)
    raw, _ = fetch(f'https://flathub.org/api/v2/appstream/{APP_ID}', limit=512 * 1024)
    metadata = json.loads(raw)
    candidates = [str(r.get('version', '')) for r in metadata.get('releases', []) if isinstance(r, dict) and r.get('type','stable')=='stable']
    candidates = [v for v in candidates if _stable_newer(v, running)]
    if not candidates: return {'status': 'current', 'message': 'No newer Flathub version available.'}
    release = max(candidates, key=version)
    notify=state.get('notified')!=release
    state['notified']=release;atomic_json(config,state)
    return {'status': 'available', 'version': release,
            'notify':notify,'url': f'https://flathub.org/apps/{APP_ID}', 'message': f'FireMedia {release} is available in your software center.'}


def _stable_newer(candidate, running):
    try: return version(candidate)[3] == 3 and version(candidate) > version(running)
    except ValueError: return False


def helper_root():
    root = Path(sys.executable).resolve().parent
    if read_json(root / 'install.json').get('format') != 'FireMediaInstall': raise ValueError('Not a FireMedia installation')
    return root


def launch(root, arguments=()):
    release = current_version(root); executable = Path(root) / 'versions' / release / 'FireMedia.exe'
    if not executable.is_file(): raise ValueError('Installed version is incomplete; run the installer to repair it')
    subprocess.Popen([str(executable), *arguments], **subprocess_options())


def restart(root, config):
    """Ask only authenticated live FireMedia sessions to save/exit. Never kill."""
    sessions = Path(config).parent / 'update-sessions'; handles = []
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]; kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    try:
        for path in sessions.glob('*.json'):
            if path.name.endswith('.restart.json'): continue
            session = read_json(path); pid = session.get('pid'); nonce = session.get('nonce', '')
            if type(pid) is not int or len(nonce) != 64: continue
            handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
            if not handle: path.unlink(missing_ok=True); continue
            buffer = ctypes.create_unicode_buffer(32768); length = ctypes.c_uint32(len(buffer))
            valid = kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length))
            if not valid or not Path(buffer.value).resolve().is_relative_to((Path(root) / 'versions').resolve()):
                kernel.CloseHandle(handle); continue
            handles.append(handle)
            atomic_json(path.with_suffix('.restart.json'), {'nonce': nonce, 'version': current_version(root)})
        for handle in handles:
            if kernel.WaitForSingleObject(handle, 45000) != 0: raise ValueError('FireMedia is still busy. Close it and reopen to finish restarting.')
        launch(root, ['--resume-update'] if handles else [])
    finally:
        for handle in handles: kernel.CloseHandle(handle)


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if any(arg.startswith('firemedia-update:') for arg in argv) and (len(argv)!=1 or argv[0] not in ('firemedia-update:install','firemedia-update:restart')):
        return 1
    parser = argparse.ArgumentParser(description='FireMedia update helper')
    parser.add_argument('command', nargs='?', default='launch'); parser.add_argument('extra', nargs='*')
    parser.add_argument('--config', type=Path, default=None)
    parser.add_argument('--manual', action='store_true'); parser.add_argument('--install', action='store_true')
    args, media = parser.parse_known_args(argv); config = args.config or default_config()
    try:
        if sys.platform == 'win32': kind, target = 'windows', helper_root()
        else: kind, target = package_kind()
        if args.command.startswith('firemedia-update:'):
            action = args.command.removeprefix('firemedia-update:').rstrip('/')
            if action not in ('install', 'restart'): raise ValueError('Unknown notification action')
            args.command = action
        if args.command == 'launch': launch(target, [*args.extra, *media]); return 0
        if args.command == 'initialize':
            release=args.extra[0];version(release)
            if not (target/'versions'/release/'FireMedia.exe').is_file():raise ValueError('Incomplete installer payload')
            with update_lock(config):
                try:old=current_version(target)
                except ValueError:old=None
                if old is None or version(release)>version(old):atomic_json(target/'current.json',{'version':release,'previous':old})
            return 0
        if args.command == 'restart': restart(target, config); return 0
        if args.command == 'configure':
            with update_lock(config):
                state = read_json(config); mode = args.extra[0] if args.extra else state.get('mode', 'notify')
                if mode not in AUTO_MODES: raise ValueError('Unknown update mode')
                configure_background(kind, target, mode == 'background', config)
                state['mode'] = mode; atomic_json(config, state)
            return 0
        if args.command == 'disable-task': configure_background(kind, target, False, config); return 0
        if args.command not in ('check', 'install'): raise ValueError('Unknown updater command')
        result = check(config, kind, target, force=args.manual or args.command == 'install', install=args.install or args.command == 'install')
        if sys.stdout: print(json.dumps(result))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        atomic_json(Path(config).with_name('update-status.json'), {'status': 'error', 'message': str(error), 'time': time.time()})
        if sys.stderr: print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__': raise SystemExit(main())
