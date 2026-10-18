"""Authenticated update discovery and atomic installation; no GUI imports."""
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from zipfile import ZipFile

REPOSITORY = 'PrismByteDev/FireMedia'
# Public release labels can differ from the numeric package version only when
# explicitly bound here. Update ordering always uses the package version.
RELEASE_ALIASES = {'vBETA.0.0': '0.3.0'}
RELEASES = f'https://github.com/{REPOSITORY}/releases/latest'
FEED = RELEASES + '/download/update.json'
APP_ID = 'io.github.PrismByteDev.FireMedia'
INTERVAL = 600
MODES = ('notify', 'disabled')
AUTO_MODES = ('background', 'launch', 'notify', 'disabled')
MAX_PACKAGE = 1024 * 1024 * 1024


def version(value):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?', str(value))
    if not match: raise ValueError('Invalid update version')
    major, minor, patch, suffix, number = match.groups()
    return (int(major), int(minor), int(patch), {'a': 0, 'b': 1, 'rc': 2, None: 3}[suffix], int(number or 0))


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode('ascii')


def read_json(path, default=None):
    try:
        path = Path(path)
        if path.stat().st_size > 512 * 1024: raise ValueError('Update state too large')
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else (default or {})
    except (OSError, ValueError): return dict(default or {})


def atomic_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=True); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


@contextmanager
def update_lock(config):
    """One check/install/configuration at a time, released by the OS on crash."""
    path = Path(config).with_suffix('.lock'); path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0); stream.write(b'0'); stream.flush(); stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try: yield
        finally:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else: fcntl.flock(stream, fcntl.LOCK_UN)


def allowed_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in
            ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com', 'api.github.com', 'flathub.org')
            and not parsed.username and not parsed.password and parsed.port in (None, 443))


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl): raise ValueError('Update redirect to an unapproved host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, *, limit=256 * 1024, etag=None, destination=None, expected_size=None):
    if not allowed_url(url): raise ValueError('Unapproved update URL')
    headers = {'User-Agent': 'FireMedia-Updater/1', 'Accept': 'application/json' if destination is None else 'application/octet-stream'}
    if etag: headers['If-None-Match'] = etag
    context=ssl.create_default_context()
    # Frozen Python can inherit its build host's OpenSSL certificate path.
    # Use the target distro's trust store rather than disabling TLS validation.
    if not context.get_ca_certs():
        for store in ('/etc/ssl/certs/ca-certificates.crt','/etc/pki/tls/certs/ca-bundle.crt','/etc/ssl/cert.pem'):
            if Path(store).is_file():context.load_verify_locations(store);break
    opener = urllib.request.build_opener(SafeRedirect,urllib.request.HTTPSHandler(context=context))
    try: response = opener.open(urllib.request.Request(url, headers=headers), timeout=20)
    except urllib.error.HTTPError as error:
        if error.code == 304: return None, etag
        raise
    with response:
        size = response.headers.get('Content-Length')
        if size and (int(size) > limit or (expected_size is not None and int(size) != expected_size)):
            raise ValueError('Unexpected update download size')
        data = bytearray(); total = 0; started = time.monotonic()
        stream = Path(destination).open('wb') if destination is not None else None
        try:
            while True:
                block = response.read(64 * 1024)
                if not block: break
                total += len(block)
                if total > limit or time.monotonic() - started > 300: raise ValueError('Update download limit exceeded')
                if stream: stream.write(block)
                else: data.extend(block)
            if expected_size is not None and total != expected_size: raise ValueError('Incomplete update download')
            if stream: stream.flush(); os.fsync(stream.fileno())
        finally:
            if stream: stream.close()
        return (bytes(data) if destination is None else total), response.headers.get('ETag', '')


def verify_manifest(envelope, *, keys=None, now=None, minimum_sequence=0):
    """All trust decisions happen before any path is used or package downloaded."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    if keys is None: keys = read_json(Path(__file__).with_name('update_keys.json'))
    if not isinstance(envelope, dict): raise ValueError('Invalid update envelope')
    payload = envelope.get('payload')
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(keys[envelope['key_id']]))
        key.verify(base64.b64decode(envelope['signature'], validate=True), canonical(payload))
    except (KeyError, TypeError, ValueError, InvalidSignature) as error: raise ValueError('Update signature rejected') from error
    now = int(time.time() if now is None else now)
    if not isinstance(payload, dict) or payload.get('format') != 'FireMediaUpdate' or payload.get('schema') != 1:
        raise ValueError('Unsupported update metadata')
    if payload.get('repository') != REPOSITORY or payload.get('channel') != 'stable' or payload.get('min_updater') != 1:
        raise ValueError('Update is for a different repository/channel/updater')
    release = payload.get('version'); parsed = version(release)
    if parsed[3] != 3: raise ValueError('Prerelease ignored by stable updater')
    tag = payload.get('tag', 'v' + release)
    if not isinstance(tag, str) or (tag != 'v' + release and RELEASE_ALIASES.get(tag) != release):
        raise ValueError('Update tag does not match its package version')
    for field in ('issued', 'expires', 'sequence'):
        if type(payload.get(field)) is not int: raise ValueError('Invalid update timestamp/sequence')
    if not payload['issued'] <= now + 300 < payload['expires'] or payload['expires'] - payload['issued'] > 370 * 86400:
        raise ValueError('Update metadata is expired or not yet valid')
    if payload['sequence'] < minimum_sequence: raise ValueError('Replayed update metadata')
    if not isinstance(payload.get('assets'), dict): raise ValueError('Missing update assets')
    for platform, asset in payload['assets'].items():
        if platform not in ('windows-x64', 'appimage-x64') or not isinstance(asset, dict): raise ValueError('Unknown update platform')
        filename = f'FireMedia-{release}-windows-x64.zip' if platform == 'windows-x64' else f'FireMedia-{release}-x86_64.AppImage'
        if asset.get('url') != f'https://github.com/{REPOSITORY}/releases/download/{tag}/{filename}': raise ValueError('Wrong update asset identity')
        if type(asset.get('size')) is not int or not 0 < asset['size'] <= MAX_PACKAGE: raise ValueError('Invalid package size')
        if not re.fullmatch('[a-f0-9]{64}', str(asset.get('sha256'))): raise ValueError('Invalid package hash')
    return payload


def discover(config, *, force=False):
    state = read_json(config)
    if not force and time.time() - state.get('checked', 0) < INTERVAL: return None, state
    state['checked'] = time.time(); atomic_json(config, state)
    try:
        raw, etag = fetch(FEED, etag=state.get('etag'))
        envelope = json.loads(raw) if raw is not None else state.get('envelope')
        payload = verify_manifest(envelope, minimum_sequence=state.get('sequence', 0))
    except urllib.error.HTTPError as error:
        if error.code == 404: return None, state  # No published stable signed release yet.
        raise
    state.update(envelope=envelope, etag=etag, sequence=payload['sequence'])
    atomic_json(config, state)
    return payload, state


def download_package(asset, path):
    fetch(asset['url'], destination=path, limit=asset['size'], expected_size=asset['size'])
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    if digest.hexdigest() != asset['sha256']: raise ValueError('Update package hash mismatch')


def extract_windows(archive, destination):
    """Reject traversal, links, aliases, duplicate paths, and oversized archives."""
    destination = Path(destination); destination.mkdir(parents=True)
    total = 0; seen = set()
    with ZipFile(archive) as package:
        if len(package.infolist()) > 15000: raise ValueError('Too many update files')
        for entry in package.infolist():
            name = entry.filename.replace('\\', '/'); path = PurePosixPath(name)
            if path.is_absolute() or not path.parts or path.parts[0] != 'FireMedia' or any(
                    p in ('.', '..') or ':' in p or p.endswith((' ', '.')) or
                    re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p) for p in name.split('/') if p):
                raise ValueError('Unsafe update archive path')
            if name.startswith('/') or '//' in name or stat.S_ISLNK(entry.external_attr >> 16): raise ValueError('Unsafe update entry')
            key = '/'.join(path.parts[1:]).casefold()
            if not key: continue
            if key in seen: raise ValueError('Duplicate update path')
            seen.add(key); total += entry.file_size
            if total > 3 * MAX_PACKAGE or entry.file_size > MAX_PACKAGE: raise ValueError('Update extraction limit exceeded')
            target = destination.joinpath(*path.parts[1:])
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(entry) as source, target.open('xb') as output: shutil.copyfileobj(source, output)
    if not (destination / 'FireMedia.exe').is_file() or not (destination / '_internal').is_dir():
        raise ValueError('Incomplete FireMedia package')


def current_version(root):
    value = read_json(Path(root) / 'current.json').get('version', '')
    version(value)
    return value


def install_windows(root, payload):
    root = Path(root); release = payload['version']; version(release)
    current = current_version(root)
    if version(release) <= version(current): return False
    versions = root / 'versions'; versions.mkdir(exist_ok=True)
    destination = versions / release
    # A completed version is immutable. Never overwrite a process's files.
    if destination.exists(): raise ValueError('Version folder already exists; repair with the installer')
    with tempfile.TemporaryDirectory(prefix='.update-', dir=versions) as temporary:
        stage = Path(temporary); archive = stage / 'download.zip'
        download_package(payload['assets']['windows-x64'], archive)
        extract_windows(archive, stage / 'app')
        os.replace(stage / 'app', destination)
    atomic_json(root / 'current.json', {'version': release, 'previous': current})
    return True


def install_appimage(image, payload):
    image = Path(image).absolute()
    if image.is_symlink() or not image.is_file(): raise ValueError('AppImage must be a regular local file')
    fd, name = tempfile.mkstemp(dir=image.parent, prefix='.' + image.name + '.update-'); os.close(fd)
    stage = Path(name)
    try:
        download_package(payload['assets']['appimage-x64'], stage)
        with stage.open('rb') as stream: header = stream.read(12)
        if header[:4] != b'\x7fELF' or header[8:11] != b'AI\x02': raise ValueError('Not a type-2 AppImage')
        stage.chmod(image.stat().st_mode | stat.S_IXUSR)
        backup = image.with_name(image.name + '.previous')
        # Hard-link the old inode before the atomic swap; mounted players stay alive.
        backup.unlink(missing_ok=True); os.link(image, backup)
        os.replace(stage, image)
    finally: stage.unlink(missing_ok=True)


def package_kind():
    if os.environ.get('FLATPAK_ID') == APP_ID: return 'flatpak', None
    if sys.platform == 'win32' and getattr(sys, 'frozen', False):
        root = Path(sys.executable).resolve().parent.parent.parent
        if (root / 'install.json').is_file() and (root / 'FireMediaUpdate.exe').is_file(): return 'windows', root
        return 'portable', None
    if sys.platform.startswith('linux') and os.environ.get('APPIMAGE'):
        return 'appimage', Path(os.environ['APPIMAGE']).absolute()
    return 'manual', None
