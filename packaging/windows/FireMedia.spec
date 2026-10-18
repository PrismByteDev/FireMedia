# Build on Windows from the repository root; vendor DLLs are not downloaded here.
from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

root = Path(SPECPATH).resolve().parents[1]
vendor = root / 'vendor' / 'windows'
dlls = list(vendor.glob('*.dll'))
if not any(p.name.lower() in ('libmpv-2.dll', 'mpv-2.dll', 'mpv-1.dll') for p in dlls):
    raise SystemExit('Place a 64-bit libmpv build and its dependent DLLs in vendor/windows.')
if not (vendor / 'ffmpeg.exe').is_file():
    raise SystemExit('Place a 64-bit ffmpeg.exe in vendor/windows.')
if not (vendor / 'licenses').is_dir() or not any((vendor / 'licenses').iterdir()):
    raise SystemExit('Include license/source information for your playback builds in vendor/windows/licenses.')

analysis = Analysis([str(root / 'packaging' / 'launch.py')], pathex=[str(root)],
    binaries=[(str(p), '.') for p in dlls] + [(str(vendor / 'ffmpeg.exe'), '.')],
    datas=[(str(root / 'firemedia' / 'assets'), 'firemedia/assets'),
           (str(root / 'LICENSE'), '.'), (str(root / 'docs'), 'docs'),
           (str(vendor / 'licenses'), 'licenses/playback')]
          + [(str(root / 'firemedia' / 'update_keys.json'), 'firemedia')]
          + copy_metadata('PyQt6', recursive=True) + copy_metadata('numpy') + copy_metadata('cryptography', recursive=True),
    hiddenimports=[], excludes=['PyQt6.QtDBus', 'firemedia.mpris'], noarchive=False)
pyz = PYZ(analysis.pure)
exe = EXE(pyz, analysis.scripts, [], exclude_binaries=True, name='FireMedia',
          console=False, debug=False, strip=False, upx=False,
          icon=str(root / 'packaging' / 'windows' / 'firemedia.ico'))
app = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name='FireMedia')
