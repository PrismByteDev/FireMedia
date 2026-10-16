# Automatic update design

Status: **planned, not yet implemented**. This document records the requested
behavior and the implementation sequence. Existing FireMedia builds do not
check for updates, install a scheduled task, or replace themselves.

Project/release location: `PrismByteDev/FireMedia` on GitHub. GitHub preparation
includes build workflows and draft releases. `release-info.json` is an unsigned
build inventory, **not** a trusted auto-install manifest.

## Windows installer

Settings → Updates offers these modes. The installer also offers the choice;
the proposed initial selection is Notify, with background installation opt-in.
The chosen mode persists across upgrades and can be changed later.

| Mode | App closed | On launch / app running | Installation |
|---|---|---|---|
| Background updates | Check every 10 minutes while the user is signed in | Same updater; no duplicate checks | Download and install silently. A running player keeps its current version; a Windows notification says an update is installed and offers Restart. |
| Update on launch | No scheduled checks | Check on launch, then every 10 minutes while running | Install available updates without an approval prompt. Prefer a ready new version at launch; if a download is still running, open the current version and notify when a restart is needed. |
| Notify | No scheduled checks | Check on launch and every 10 minutes while running | Windows notification asks whether to update. Installation starts only after the user chooses Update. |
| Disabled | No checks | No automatic checks | No automatic download/install. An explicit Check now remains available. |

Background mode uses a **per-user Task Scheduler task**, repeating every ten
minutes with a logon trigger. It runs without administrator privileges and only
while that user is signed in; it is not a system service or an always-running
polling process. Sleep/offline periods do not cause a backlog. A failed check
waits until the next interval. A shared lock prevents task/app/installer races.
Changing away from Background removes/disables the task. Uninstall removes it.

Use native **Windows notifications**, with a stable application identity,
Start-menu shortcut, and activation handler. Actions are Update, Restart, and
View release as appropriate. Windows owns notification permissions/quiet hours.
If delivery is unavailable, show the same status in Settings/in the app.
Coalesce notifications by release version; never issue one toast every ten
minutes for an already-announced release.

### Install while FireMedia is running

Do not overwrite the executable, Python runtime, Qt DLLs, or playback DLLs used
by an open process. Move from the current single-folder installer to:

```text
%LOCALAPPDATA%/Programs/FireMedia/
  FireMedia.exe                 stable launcher
  FireMediaUpdate.exe           installed update/task entry point
  current.json                  atomically selected version, no commands/URLs
  versions/
    0.2.0/                      current process can keep using this directory
    0.3.0/                      staged, verified replacement
```

The helper downloads to a temporary directory on the same volume, verifies the
signed metadata, length, hash, package identity, and extraction limits, then
installs a complete version directory. It atomically changes the launcher pointer
only after the directory is complete. New launches use the new version; a running
old player remains functional. The notification says **installed; restart to
apply**, rather than implying that a running process has changed its code.

Restart uses local authenticated IPC: save queue/settings, acknowledge shutdown,
wait for the old process to exit, then start the installed version. Do not pass
paths or commands from a notification or release description to a shell.
Keep the last working version for rollback. Clean it up only after a successful
new launch and after confirming no process still uses it. Updater/launcher
replacement needs its own staged handoff, never an in-use DLL overwrite.

Migrate existing per-user Inno Setup installs without moving user state or media.
Keep the existing installer AppId. User data remains in Qt's application-data
directory, separate from version folders. Schema changes must preserve a backup
and support the retained version before automatic rollback is enabled.

## Windows portable

Only **Notify** and **Disabled** are offered. Notify checks on launch and every
ten minutes while FireMedia is running, using Windows notifications. Its action
opens the project's GitHub Releases page. It does not download, overwrite,
extract, or install an update. There is no scheduled task in portable mode.

An explicit packaging marker distinguishes installer/portable builds; do not
infer this from whether a directory is writable. Copying an EXE alone is not a
supported portable installation.

## Linux / Flathub

Flathub is the intended distribution-independent installation/update route.
App ID: **`io.github.PrismByteDev.FireMedia`**. Keep the `.deb` recipe for users
who prefer it. FireMedia's Linux update modes are **Notify** and **Disabled**.

Notify checks while the app is running (on launch, then ten-minute intervals).
For Flatpak, compare with the version actually available on Flathub, not merely
the newest GitHub tag: Flathub publication may lag a GitHub release. Use the
desktop notification portal and an Open software center / View Flathub action.
The user or their system's software manager performs the update. FireMedia
does not invoke `sudo`, `pkexec`, a host shell, or an unattended Flatpak update.
The software manager's own auto-update policy is independent of this setting.

For `.deb`/source installs, Notify can link to the release and explain the
appropriate package-manager/manual update route. Disabled does not change
the system package manager's configuration. No FireMedia background task is
installed on Linux.

Flathub work includes a tested Flatpak manifest, pinned dependency sources,
AppStream/desktop/icon metadata, file/notification portal handling, MPRIS,
media-device/OpenGL access, and local/relative-playlist checks. Use KDE's
maintained runtime and PyQt BaseApp rather than bundling an unrelated Qt runtime.
Keep filesystem permissions limited to read-only music/video directories plus
explicit portal grants; do not request general host execution. Verify the
existing mod worker's seccomp restrictions inside Flatpak; fail closed if nested
restriction setup fails. See [Flatpak preparation](../packaging/flatpak/README.md).

## Discovery, trust, and failures

All channels use HTTPS, bounded responses, request timeouts, and version-aware
comparison. Stable installations ignore drafts/prereleases and older versions.
Cache discovery metadata and use conditional requests. Prefer small release
assets/CDN metadata over giving every installation a ten-minute GitHub API poll;
do not embed an access token to bypass API rate limits.
No media paths, playlist names, or listening history are sent. Requests expose
normal network metadata to GitHub/Flathub; Disabled makes no update requests.

The Windows installer helper must authenticate an update **before** silent
installation. Plan an Ed25519-signed, canonical manifest containing repository,
channel, version, monotonic release number, expiry, supported OS/architecture,
minimum updater version, package length/hash, and an exact release asset URL.
Embed trusted public keys in the helper. Keep signing private keys outside Git.
Reject invalid/expired metadata, downgrades/replays, wrong-platform packages,
redirects outside approved download hosts, missing assets, and extraction paths
that escape staging. Key rotation needs overlap signed by an existing trusted
key. Establish signature/test vectors before enabling automatic installation.

SHA-256 checksums detect damage; they do not independently authenticate a
publisher. GitHub release digests/attestations are additional provenance, not
a reason to execute unsigned update metadata. Consider immutable GitHub releases
once the complete asset set has been reviewed and attached. Authenticode signing
is a separate Windows distribution task, not a replacement for manifest checks.

Offline checks, interrupted downloads, full disks, locked files, rejected
signatures, and failed launches leave the current working version intact.
Use resumable staging only when the resumed content is reverified. Disable
restart actions until installation has succeeded. Never force a restart during
playback. The updater is independent of visualizer timers: minimizing the player
continues to suspend effects, even if the user opted into background updates.

## Implementation sequence and acceptance

1. **Release foundation (this preparation):** one version source, Linux/Windows
   builds, source archive, checksums/inventory, draft release, contribution docs.
2. **Flathub:** build/test the manifest on supported architectures, validate
   portals/playlists/covers/OpenGL/MPRIS/mod restrictions, then submit for review.
3. **Discovery/settings/notifications:** package markers, version comparison,
   ten-minute checks, mode persistence, native notification activation, duplicate
   suppression, and Linux/portable release/store links. No binary installation.
4. **Authenticated Windows updater:** signed manifests, staged version layout,
   per-user installer migration, scheduled task, locking, session-save/restart,
   success reporting and rollback. Enable silent modes only after these pass.
5. **Release verification:** test all four installer modes, portable behavior,
   disabled-network behavior, app-open/app-closed checks, multi-instance use,
   minimize/restore, offline/retry, download interruption, signature/rollback
   rejection, disk-full/locked files, task removal on uninstall, and a real
   two-version upgrade on Windows 10/11 and Flatpak-capable Linux desktops.

References: [GitHub release API](https://docs.github.com/en/rest/releases/releases),
[immutable releases](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases),
[Flathub requirements](https://docs.flathub.org/docs/for-app-authors/requirements),
[PyQt BaseApp](https://github.com/flathub/com.riverbankcomputing.PyQt.BaseApp).
