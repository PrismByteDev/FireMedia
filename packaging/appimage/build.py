"""Bundle the desktop app, playback libraries and pinned type-2 AppImage runtime."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root))
from firemedia import __version__
from tools.build_source import build_source

TOOLS={
    'appimagetool-x86_64.AppImage':('https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage','ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0'),
    'runtime-x86_64':('https://github.com/AppImage/type2-runtime/releases/download/20251108/runtime-x86_64','2fca8b443c92510f1483a883f60061ad09b46b978b2631c807cd873a47ec260d')}

def main():
    os.chdir(root);vendor=root/'vendor/appimage';vendor.mkdir(parents=True,exist_ok=True)
    for name,(url,digest) in TOOLS.items():
        path=vendor/name
        if not path.exists():
            with urllib.request.urlopen(url,timeout=30) as response,path.open('wb') as output:shutil.copyfileobj(response,output)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise SystemExit('AppImage build-tool hash mismatch: '+name)
        path.chmod(0o755)
    subprocess.run([sys.executable,'-m','PyInstaller','--clean','--noconfirm','packaging/appimage/FireMedia.spec'],check=True)
    appdir=root/'build/FireMedia.AppDir';shutil.rmtree(appdir,ignore_errors=True);(appdir/'usr/bin').mkdir(parents=True)
    shutil.copytree(root/'dist/FireMedia',appdir/'usr/bin',dirs_exist_ok=True)
    build_source(appdir/'usr/bin/FireMedia-source.zip')
    (appdir/'AppRun').write_text('#!/bin/sh\nexec "$APPDIR/usr/bin/FireMedia" "$@"\n');(appdir/'AppRun').chmod(0o755)
    desktop=(root/'firemedia.desktop').read_text().replace('Exec=firemedia','Exec=FireMedia')
    (appdir/'firemedia.desktop').write_text(desktop)
    shutil.copy2(root/'firemedia/assets/firemedia.svg',appdir/'firemedia.svg')
    shutil.copy2(root/'firemedia/assets/logo128.png',appdir/'.DirIcon')
    output=root/'dist'/f'FireMedia-{__version__}-x86_64.AppImage'
    env=dict(os.environ,ARCH='x86_64',APPIMAGE_EXTRACT_AND_RUN='1')
    subprocess.run([str(vendor/'appimagetool-x86_64.AppImage'),'--runtime-file',str(vendor/'runtime-x86_64'),str(appdir),str(output)],check=True,env=env)
    subprocess.run([str(output),'--version'],check=True,env=env)
    print(output)

if __name__=='__main__':main()
