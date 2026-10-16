# Contributing to FireMedia

FireMedia uses native Python/PyQt6 widgets with libmpv and FFmpeg. Contributions
are welcome through issues and pull requests. Native code is GPL-3.0-or-later;
the archived web prototype retains its MIT license. Submitted changes should
use the license of the files they modify. Include attribution and compatible
licenses for new third-party material; do not copy proprietary player assets.

## Development

Use Python 3.10+ with PyQt6 6.6+, NumPy, libmpv and FFmpeg. Restricted mods
also require Linux/libseccomp2. Python packaging uses Python 3.11+ tooling;
Windows build scripts target Python 3.12 x64. Install Python dependencies in a
virtual environment with `python -m pip install -e .` and run `python -m firemedia`.
System libmpv/FFmpeg must still be available. See [packaging](packaging/README.md).

Run the native tests on Linux:

```sh
QT_QPA_PLATFORM=offscreen FIREMEDIA_TEST_DBUS=1 dbus-run-session -- python3 -m unittest discover -s tests -v
```

Do not run MPRIS tests against your normal desktop session bus. For visual/video
changes, use `tools/verify_video.py` on a real desktop inside `dbus-run-session`.
Use generated media fixtures rather than private or copyrighted media in tests.
Windows and Flatpak changes need their own platform checks; a Linux test passing
does not demonstrate a Windows/Flatpak desktop build works.

Keep playback, decoding, update requests, and mod work off the UI thread. Hidden
or minimized players must not run effect loops. Preserve existing playlists and
presets when schemas change. Never weaken the mod boundary to work around a
platform limitation: unsupported restriction setup must fail closed.

## Pull requests

Describe the user-visible problem, resulting behavior, and relevant validation.
Include screenshots for UI changes and state platform limitations honestly.
Keep generated `dist/`, `build/`, vendored DLLs, state/playlists, and signing keys
out of Git. Avoid unrelated formatting changes. Add regression tests for behavior
changes when they provide meaningful coverage.

Version changes belong in `firemedia/__init__.py`. Do not edit generated package
metadata or hardcode a second installer version. Release/update work follows
[the release guide](docs/RELEASING.md) and [update design](docs/UPDATES.md).
