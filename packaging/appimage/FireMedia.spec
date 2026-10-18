"""Build on Ubuntu 22.04 for a glibc 2.35 baseline."""
from pathlib import Path
import re
import subprocess
from PyInstaller.utils.hooks import copy_metadata
root=Path(SPECPATH).resolve().parents[1]
cache=subprocess.check_output(['/sbin/ldconfig','-p'],text=True)
def library(name):
    matches=re.findall(r'\s'+re.escape(name)+r'\.so[^\s]*\s+\(.*?\) => (\S+)',cache)
    if not matches:raise SystemExit('Install '+name+' before building the AppImage')
    return matches[0]
a=Analysis([str(root/'packaging/launch.py')],pathex=[str(root)],
    binaries=[(library('libmpv'),'.'),(library('libseccomp'),'.'),('/usr/bin/ffmpeg','.')],
    datas=[(str(root/'firemedia/assets'),'firemedia/assets'),(str(root/'firemedia/update_keys.json'),'firemedia'),
           (str(root/'firemedia/mod_worker.py'),'firemedia'),(str(root/'LICENSE'),'.'),(str(root/'docs'),'docs')]
          +copy_metadata('PyQt6',recursive=True)+copy_metadata('numpy')+copy_metadata('cryptography',recursive=True),
    hiddenimports=['PyQt6.QtDBus'],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='FireMedia',console=True,upx=False)
app=COLLECT(exe,a.binaries,a.datas,name='FireMedia',upx=False)
