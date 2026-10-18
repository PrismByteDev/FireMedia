"""M3U/M3U8 resolution and atomic local state storage."""
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse
import json
import os
import tempfile
from .sources import source_scheme, file_uri_path

MEDIA_EXTENSIONS = {'.mp3', '.wav', '.flac', '.ogg', '.opus', '.m4a', '.aac', '.wma',
                    '.mp4', '.mkv', '.webm', '.mov', '.avi', '.m4v', '.ts', '.mpeg', '.mpg'}
PLAYLIST_EXTENSIONS = {'.m3u', '.m3u8'}

@dataclass
class Track:
    source: str
    title: str
    duration: float = -1

    @classmethod
    def from_source(cls, source, title='', duration=-1):
        parsed = urlparse(str(source))
        if parsed.scheme == 'file':
            source = file_uri_path(source)
        elif not source_scheme(source):
            source = str(Path(source).expanduser().resolve())
        name = Path(unquote(urlparse(source).path)).stem or str(source)
        return cls(str(source), title or name, duration)


def parse_playlist(path):
    """Local playlists are lists; HLS manifests remain single stream sources."""
    path = Path(path).resolve()
    text = path.read_bytes().decode('utf-8-sig', errors='replace')
    lines = text.splitlines()
    if any(line.strip().startswith(('#EXT-X-TARGETDURATION:', '#EXT-X-STREAM-INF:',
                                      '#EXT-X-MEDIA-SEQUENCE:', '#EXT-X-I-FRAME-STREAM-INF:')) for line in lines):
        # Keep the base path intact so libmpv resolves relative segments/variants.
        return [Track.from_source(str(path))]
    tracks, title, duration = [], '', -1
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if line.startswith('#EXTINF:'):
            info, _, title = line[8:].partition(',')
            try:
                duration = float(info)
            except ValueError:
                duration = -1
            continue
        if line.startswith('#'):
            continue
        parsed = urlparse(line)
        scheme = source_scheme(line)
        if scheme not in ('', 'file', 'http', 'https'):
            continue
        if not scheme:
            resolved=(path.parent / line).resolve()
            decoded=(path.parent / unquote(line)).resolve()
            line=str(decoded if not resolved.exists() and decoded.exists() else resolved)
        tracks.append(Track.from_source(line, title, duration))
        title, duration = '', -1
    return tracks


def expand_sources(sources, visited=None):
    visited = set() if visited is None else visited
    tracks = []
    for source in sources:
        parsed = urlparse(str(source))
        if parsed.scheme in ('http', 'https'):
            # Remote M3U8 may be live HLS; let the media backend resolve it.
            tracks.append(Track.from_source(str(source)))
            continue
        path = Path(file_uri_path(source) if parsed.scheme == 'file' else source).expanduser().resolve()
        if path in visited:
            continue
        visited.add(path)
        if path.is_dir():
            children = sorted(p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in MEDIA_EXTENSIONS)
            tracks.extend(expand_sources(children, visited))
        elif path.suffix.lower() in PLAYLIST_EXTENSIONS:
            for entry in parse_playlist(path):
                entry_path = Path(entry.source)
                if entry_path == path or urlparse(entry.source).scheme in ('http', 'https'):
                    tracks.append(entry)
                elif entry_path.suffix.lower() in PLAYLIST_EXTENSIONS:
                    tracks.extend(expand_sources([entry.source], visited))
                else:
                    tracks.append(entry)
        elif path.is_file():
            tracks.append(Track.from_source(str(path)))
    return tracks


def write_playlist(path, tracks, relative=False):
    path = Path(path).resolve()
    lines = ['#EXTM3U']
    for track in tracks:
        source = track.source
        if not source_scheme(source):
            source = str(Path(source).expanduser().resolve())
            if relative:
                # Forward slashes keep relative M3U files portable across OSes.
                try: source = Path(os.path.relpath(source, path.parent)).as_posix()
                except ValueError: pass  # Different Windows drives need absolute paths.
        source = source.replace('\r', '').replace('\n', '')
        title = track.title.replace('\r', ' ').replace('\n', ' ')
        lines.extend([f'#EXTINF:{track.duration:g},{title}', source])
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix='.firemedia-', suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_state(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}
