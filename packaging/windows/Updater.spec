from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata
root=Path(SPECPATH).resolve().parents[1]
a=Analysis([str(root/'packaging/update_launch.py')],pathex=[str(root)],binaries=[],
           datas=[(str(root/'firemedia/update_keys.json'),'firemedia')]+copy_metadata('cryptography',recursive=True),
           hiddenimports=[],excludes=['PyQt6','numpy'],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='FireMediaUpdate',console=False,
        icon=str(root/'packaging/windows/firemedia.ico'),upx=False)
