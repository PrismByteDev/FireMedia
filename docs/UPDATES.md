# Updates and playback wake locks

FireMedia 0.3.0 introduces signed automatic updates. Existing 0.2.0 builds have
no updater: install a new build once to receive future updates. A published stable
release must contain a valid `update.json` signed with FireMedia's publishing key.
Drafts and prereleases never trigger stable automatic installation.

## Platforms and modes

Choose **Settings → Updates**. Notify is the default; unattended installation is
opt-in. The Windows installer and AppImage first-run setup ask about background
updates and media-file registration.

| Platform | Modes | When FireMedia is closed |
|---|---|---|
| Windows installer | Background, Update on launch, Notify, Disabled | Background uses a per-user Task Scheduler task every ten minutes while signed in, plus logon |
| AppImage | Background (systemd user session required), Update on launch, Notify, Disabled | Background uses a systemd user timer every ten minutes; no root/system service |
| Windows portable | Notify, Disabled | No checks or installation |
| Flatpak | Notify, Disabled | No FireMedia task; updates belong to the software manager |
| Source / Debian package | Notify, Disabled | No FireMedia task; use the package manager/manual download |

Enabled modes check after launch and every ten minutes while running. Background
and Update on launch download/install a verified update automatically. Notify
announces an available update; installed Windows/AppImage builds offer **Update
now** in Settings. Windows notifications also offer Update or Restart. Portable
notifications open Releases. Disabled sends no automatic update requests; the
explicit **Check now** button still works. Checks run independently of visualizer
activity; minimized windows do not resume graphics effects to check for updates.

AppImage Background appears only with a functioning systemd user session.
The file and its containing directory must be writable and support hard links.
Moving an integrated AppImage requires rerunning setup/settings so its desktop
entry and background timer use the new path. Turning Background off removes its
user timer. Windows uninstall removes its task. Before manually deleting an
AppImage, switch its update mode away from Background. Windows checks stop after
logout. The AppImage timer follows the systemd user manager's lifetime (including
any user-enabled lingering); it never installs a system-wide service.

Flatpak checks Flathub appstream releases, rather than assuming a GitHub release
is already on Flathub. Notifications use the desktop portal. There is currently
no published Flathub listing; Flatpak publication/testing remains separate work.
No updater runs sudo, pkexec, or an unattended `flatpak update`.

## Installation and restart

Installed Windows builds use:

```
%LOCALAPPDATA%/Programs/FireMedia/
  FireMedia.exe             stable launcher
  FireMediaUpdate.exe       short-lived updater/task/protocol helper
  install.json
  current.json              selected version and previous version
  versions/0.3.0/           complete app + Qt + playback libraries
  versions/0.3.1/           next complete version
```

New versions are extracted into staging, then moved into a new immutable version
folder. The launcher pointer changes atomically only after verification and
extraction finish. Running players keep their existing files. Old version folders
are retained for manual recovery; no automatic deletion or automatic rollback is
attempted. The stable helper is updated by a new installer, not by overwriting a
helper that is executing. A release requiring a newer updater must use a new
installer; this helper rejects incompatible manifests.

AppImage updates download to the same filesystem, preserve the previous image as
`FireMedia.AppImage.previous`, then replace the image atomically. An open mounted
player continues running its original image. Restart launches the new image.

After installation, Settings and Windows notifications offer Restart. Restart
saves the queue/settings and current source/position/pause state. Windows uses
per-session random nonces and checks that process handles belong to installed
FireMedia executables; it asks processes to exit and waits without forcibly
terminating them. If a player is busy, close/reopen it manually. Playback resumes
from the saved position. A normal reopen selects the installed version too.

Update configuration/status lives beside FireMedia's app state in `updates.json`
and `update-status.json`. Updates never send media paths, playlist names, or
listening history. HTTPS requests still expose normal network metadata to the
release/download provider. Avoid editing update files while an updater runs.

## Trust and publishing

`release-info.json` and SHA256SUMS are inventories; they do not authorize automatic
installation. `update.json` is an Ed25519-signed canonical JSON envelope containing
repository, stable channel, version, issuance/expiry, sequence, minimum updater,
and exact platform package URLs/sizes/SHA-256 hashes. The embedded public key is
`firemedia/update_keys.json`. Private keys must never be committed or distributed.

The Draft release workflow builds Windows, AppImage, and Debian/Python packages,
then signs metadata with the repository secret **FIREMEDIA_UPDATE_SIGNING_KEY**.
The signing step fails if the secret is absent or does not match the embedded
public key. Configure this secret with explicit maintainer approval. A local
private key backup is ignored under `.signing/`; keep an independent secure backup.

Signed metadata expires after one year; refresh it through a reviewed release
before it expires. Unknown keys, tampered signatures, wrong channels/platforms,
expired/future/replayed metadata, older/equal versions, unsafe redirects, length
and hash mismatches, ZIP traversal/links/Windows aliases and extraction-limit
violations are rejected. Offline/failed/interrupted checks leave the current
version selected. A shared OS lock prevents simultaneous task/app installations.
No access token is shipped in clients. Conditional requests reuse signed cached
metadata, and failed automatic checks wait until the next interval.

Before publishing, test two real versions on Windows and AppImage: active audio
and video playback, notifications and activation, background after app exit,
launch mode, Notify, Disabled, restart resume, task/timer removal, an offline
check, a corrupt download, and a full/locked destination. CI verifies updater
policy/trust/atomic staging and packaged startup; it does not replace this desktop
upgrade acceptance test. Windows publisher/Authenticode signing is separate.

## Wake lock

**Settings → Prevent sleep during playback** is enabled by default. Playing audio
inhibits automatic suspend; video additionally inhibits display idle/screensaver.
Pause, stop, end of queue, disabling the setting, and closing the player release
it. The lock stays active for playback in a minimized window without running
visual effects. It never blocks a deliberate user shutdown/sleep request.

Windows uses SetThreadExecutionState on the UI thread. Linux uses the Inhibit
portal (including Flatpak), with freedesktop PowerManagement/ScreenSaver fallbacks
for desktops without it. Requests are asynchronous; late replies are released
when playback has already stopped. Desktop policy can refuse inhibition.

References: [AppImage updates](https://docs.appimage.org/packaging-guide/optional/updates.html),
[Inhibit portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Inhibit.html),
[Windows execution state](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate).
