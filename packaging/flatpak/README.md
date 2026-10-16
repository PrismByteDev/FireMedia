# Flatpak / Flathub preparation

Target app ID: `io.github.PrismByteDev.FireMedia`.

Status: **packaging plan and metadata only**. There is no tested Flatpak build or
Flathub listing yet. A GitHub release or `.deb` is not a Flathub publication.

Use `org.kde.Platform` / `org.kde.Sdk` with the matching maintained
`com.riverbankcomputing.PyQt.BaseApp` branch. Pin/checksum source modules for
NumPy, libmpv and its playback dependencies, FFmpeg, and libseccomp. Confirm
Qt OpenGLWidgets and Qt D-Bus are available. Prefer source modules appropriate
for each architecture over downloading Windows/PyPI Qt bundles into Flatpak.

The manifest must install:

- the native Python application and launcher;
- `io.github.PrismByteDev.FireMedia.desktop` derived from the existing entry;
- the supplied icon under that ID and the supplied AppStream metadata;
- applicable GPL/dependency notices and corresponding build/source information.

Initially test x86_64; add aarch64 after the same playback/rendering checks pass.
Configure the initial submission's architecture support explicitly.

Planned permissions: Wayland and fallback X11, GPU rendering, PulseAudio,
network for streams/update discovery, read-only music/video directories, and
the MPRIS bus name. Use file/directory and notification portals. Check external
drives, directory cover discovery, SRT autoload, and relative playlists under
portal grants; access to one chosen file does not imply access to its siblings.
Do not allow host execution just to update the app.

Before submission, validate AppStream/desktop metadata, pin a real release tag
and commit in the manifest, and run real playback plus minimize/restore tests
inside the sandbox. Verify the seccomp mod runner; unavailable restrictions must
leave plugins disabled. MPRIS DesktopEntry must use the installed app ID.

Flathub submission requires its own review. Follow the current
[submission requirements](https://docs.flathub.org/docs/for-app-authors/requirements),
including disclosure of AI-assisted code, documentation, and packaging where
required. The app's Linux update UI only notifies and opens the software center;
installation remains under Flatpak/the user's control. See the
[update-system plan](../../docs/UPDATES.md).
