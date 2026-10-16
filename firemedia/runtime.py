"""Locate bundled playback tools without depending on the working directory."""
import ctypes
import ctypes.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Keep DLL directory handles alive for dependent libraries loaded later by mpv.
_dll_directories = []


def runtime_directories():
    if getattr(sys, 'frozen', False):
        return [Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent)), Path(sys.executable).parent]
    return [Path(__file__).resolve().parent.parent / 'vendor' / 'windows'] if sys.platform == 'win32' else []


def find_tool(name):
    filename = name + '.exe' if sys.platform == 'win32' else name
    for directory in runtime_directories():
        candidate = directory / filename
        if candidate.is_file():
            return str(candidate)
    return shutil.which(filename)


def load_mpv():
    if sys.platform == 'win32':
        for directory in runtime_directories():
            if directory.is_dir():
                _dll_directories.append(os.add_dll_directory(str(directory)))
            for name in ('libmpv-2.dll', 'mpv-2.dll', 'mpv-1.dll'):
                candidate = directory / name
                if candidate.is_file():
                    return ctypes.CDLL(str(candidate))
        library = ctypes.util.find_library('mpv-2') or ctypes.util.find_library('mpv-1')
        if not library:
            raise OSError('libmpv is missing. Use the complete FireMedia Windows folder, including its playback DLLs.')
    else:
        library = ctypes.util.find_library('mpv')
        if not library:
            raise OSError('libmpv is missing. Install libmpv2 (Debian/Ubuntu) or mpv-libs (Fedora).')
    return ctypes.CDLL(library)


def subprocess_options():
    # A windowed app must not flash a console each time analysis starts/seeks.
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
