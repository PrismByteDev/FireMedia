#!/usr/bin/env python3
"""Build a dependency-based Debian/Ubuntu package without root or pip installs."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys
import re

root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from firemedia import __version__ as version
debian_version=re.sub(r'(a|b|rc)(\d+)$',r'~\1\2',version)
output = root / 'dist' / f'firemedia_{version}_all.deb'
output.parent.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix='firemedia-deb-') as temporary:
    stage = Path(temporary)
    share = stage / 'usr/share/firemedia'
    share.mkdir(parents=True)
    shutil.copytree(root / 'firemedia', share / 'firemedia', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    launcher = stage / 'usr/bin/firemedia'
    launcher.parent.mkdir(parents=True)
    launcher.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/firemedia/launch.py "$@"\n')
    launcher.chmod(0o755)
    shutil.copy2(root / 'packaging/launch.py', share / 'launch.py')
    for source, destination in [
        ('firemedia.desktop', 'usr/share/applications/firemedia.desktop'),
        ('firemedia/assets/firemedia.svg', 'usr/share/icons/hicolor/scalable/apps/firemedia.svg'),
        ('docs/PLUGINS.md', 'usr/share/doc/firemedia/PLUGINS.md'),
        ('docs/VISUALIZER.md', 'usr/share/doc/firemedia/VISUALIZER.md'),
        ('docs/THEMES.md', 'usr/share/doc/firemedia/THEMES.md'),
        ('docs/UPDATES.md', 'usr/share/doc/firemedia/UPDATES.md'),
        ('CHANGELOG.md', 'usr/share/doc/firemedia/CHANGELOG.md'),
        ('LICENSE', 'usr/share/doc/firemedia/copyright')]:
        target = stage / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / source, target)
    shutil.copytree(root / 'examples/plugins', stage / 'usr/share/doc/firemedia/examples/plugins')
    control = stage / 'DEBIAN/control'
    control.parent.mkdir()
    control.write_text(f'''Package: firemedia
Version: {debian_version}
Section: sound
Priority: optional
Architecture: all
Maintainer: FireMedia contributors <firemedia@localhost>
Depends: python3 (>= 3.10), python3-pyqt6 (>= 6.6), python3-numpy, python3-cryptography, libmpv2, ffmpeg, libseccomp2
Description: Native Qt media player with music fireworks
 Audio and video playback, physics-driven visualization, playlists,
 equalization, and customizable art subtitles.
''')
    subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(stage), str(output)], check=True)
print(output)
