#!/usr/bin/env python3
"""Create a source ZIP and optional virtual CD for building in a Windows VM."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
from tools.build_source import build_source
dist = root / 'dist';dist.mkdir(exist_ok=True)
archive = dist / 'FireMedia-source.zip'
build_source(archive)
print(archive)
if shutil.which('genisoimage'):
    with tempfile.TemporaryDirectory(prefix='firemedia-cd-') as temporary:
        stage = Path(temporary)
        shutil.copy2(archive, stage / archive.name)
        shutil.copy2(root / 'packaging/windows/START-HERE.txt', stage / 'START-HERE.txt')
        iso = dist / 'FireMedia-windows-build-kit.iso'
        subprocess.run(['genisoimage', '-quiet', '-J', '-r', '-V', 'FIREMEDIA', '-o', str(iso), str(stage)], check=True)
        print(iso)
