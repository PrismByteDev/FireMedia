# FireMedia desktop packages

FireMedia is already a native Qt application. Packaging adds installation,
launchers, and (on Windows) a bundled Python/Qt runtime. The version comes from `firemedia.__version__`.

## Debian / Ubuntu

Build on Linux using Python 3.11+ and `dpkg-deb`:

```sh
python3 packaging/linux/build-deb.py
sudo apt install ./dist/firemedia_0.2.0_all.deb
```

Open **FireMedia** in the application menu. APT installs Python, Qt, NumPy,
libmpv, FFmpeg, and libseccomp2 as distribution dependencies. This `.deb` is for Debian/Ubuntu
releases providing PyQt6 6.6+ and libmpv2. It is not an AppImage or a package for
all Linux distributions. Remove it with `sudo apt remove firemedia`; personal
settings/playlists are preserved. Building does not install or alter the host.

## Windows 10/11 x64

Build on Windows, including inside a KVM Windows guest. Python is only needed
on the build machine; recipients use the bundled application.

1. Install **64-bit Python 3.12** with the Python launcher (`py`).
2. Copy the project to a writable Windows folder and open PowerShell there.
3. Fetch the playback dependencies with:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\packaging\windows\fetch-playback.ps1
   ```

   This downloads the baseline x64 libmpv build linked by mpv.io and FFmpeg's
   release essentials build from Gyan, checks published hashes when available,
   and retains supplied license/readme files. Review the source information
   before public redistribution. Downloads require an internet connection.

   Alternatively, create `vendor/windows/`. Place a **64-bit libmpv** DLL
   (`libmpv-2.dll`, `mpv-2.dll`, or `mpv-1.dll`) and any dependent DLLs alongside
   a **64-bit `ffmpeg.exe`** in that folder. Use a matching baseline x86-64 build,
   avoiding AVX2/v3-specific builds unless all target CPUs support them.
   [mpv's installation page](https://mpv.io/installation/) links to Windows
   libmpv builds; [FFmpeg's download page](https://ffmpeg.org/download.html)
   links to Windows binaries. A standalone `mpv.exe` is not a libmpv DLL.
4. Add the playback builds' licenses, notices, source links, and build/version
   information to `vendor/windows/licenses/`. Preserve their supplied notices.
5. Run:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1
   ```

The output is `dist/FireMedia/FireMedia.exe` plus
`dist/FireMedia-windows-x64.zip`. Share the **entire folder or ZIP**, including
`_internal`; copying just the executable will not work. A virtual environment
named `.venv-build` isolates build dependencies. No system Python changes or
administrator privileges are needed by this script.

For a setup wizard and Start-menu shortcut, install
[Inno Setup 6](https://jrsoftware.org/isinfo.php), run
`powershell -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1 -Installer`.
This passes the version from `firemedia.__version__` to the installer compiler. The resulting
`dist/FireMedia-0.2.0-windows-x64-setup.exe` installs per user and includes an
uninstaller. A desktop shortcut is optional. Signing installers is a separate
release step; these build recipes do not apply a publisher signature.

Windows path handling supports drive-letter paths, file URLs, UNC paths, and
relative playlist paths. Shift+Save falls back to absolute paths for media on
a different drive. Visualizer FFmpeg subprocesses hide their console windows.
KDE/MPRIS integration remains Linux-only; Windows system media controls and
Windows power-saver detection have not been implemented. Restricted Python mod execution is Linux-only and fails closed on Windows. The rest of the new themes/cover/wave/channel features require testing in a rebuilt Windows package. Playback, video,
visualization, drag/drop, and settings require testing on a Windows desktop.

### KVM testing

On the Linux host, `python3 packaging/windows/make-build-kit.py` creates
`dist/FireMedia-source.zip` and, if `genisoimage` is installed,
`dist/FireMedia-windows-build-kit.iso`. In virt-manager, open the VM's hardware
details, select its CD-ROM, and choose that ISO. Inside Windows, open the disc
and follow `START-HERE.txt`. The helper `BUILD-WINDOWS.cmd` downloads playback
dependencies and builds the portable app after Python 3.12 x64 is installed.

A Windows VM can build the Windows executable. Copy the project ZIP through an
existing shared folder, SPICE file transfer (if guest tools support it), or SSH.
Copy the source to the guest's local disk before building. No VM disk editing
or VM configuration changes are needed. Test a song, video, seek, subtitles,
playlist import/export, and reopening the app with saved settings. The embedded
video renderer requires desktop OpenGL 3.2; a VM with only the basic display
driver may need an OpenGL-capable driver or Mesa software OpenGL. Packaging
cannot supply host GPU acceleration on its own.

## Release contents and licensing

FireMedia is GPL-3.0-or-later. Distribute corresponding FireMedia source with
releases and satisfy the license/source obligations of the exact PyQt6/Qt,
NumPy, mpv, FFmpeg, and codec builds being shipped. Their bundled copies and
notices belong in the release. The Windows spec requires a nonempty playback
license directory but does not certify its contents or license compliance.

PyInstaller builds an application for the OS on which it runs. The Windows
package must be built on Windows: see
[PyInstaller's operating-mode documentation](https://pyinstaller.org/en/stable/operating-mode.html).


## GitHub builds, Flathub, and planned updates

See [the release guide](../docs/RELEASING.md) for CI and draft releases. The
versioned source exporter is `python3 tools/build_source.py`; it omits local
builds, credentials, vendor binaries, and app state. Windows portable/installer
builds include this FireMedia source archive and build-environment information.

[Flathub preparation](flatpak/README.md) targets other Linux distributions.
The [automatic update design](../docs/UPDATES.md) records the requested modes;
it is not implemented in the current installer. No background update task is
registered by these build recipes.
