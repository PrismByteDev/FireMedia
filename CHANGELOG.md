# Changelog

## vBETA.0.0 — 2026-10-17 (package 0.3.0)

- Signed update discovery, ten-minute checks, native notifications, and update settings.
- Windows version folders, opt-in scheduled background updates, restart/resume,
  installer update choices, and optional Open With registration.
- AppImage packaging, atomic updates with a retained previous image, optional
  systemd user timer, and first-run desktop/media registration.
- Flatpak notifications based on Flathub publication; portable/source builds only notify.
- Playback wake locks on Windows/Linux, released on pause/stop/close.
- Separate Windows installer and portable downloads, AppImage, Debian package,
  source archive, checksums, and signed update metadata.
- Beta/Canary channel selection is planned; this build follows main/latest.
- CI covers package startup, installer integration, update verification and
  atomic replacement. Native notification clicks and a full two-version desktop
  upgrade remain manual validation gaps.

## Unreleased — 0.2.0 public preview preparation

- Native Qt/libmpv audio/video player with a collapsible effects menu and playlist.
- M3U/M3U8 and FireMedia playlist/preset formats, relative paths, drag/drop,
  saved playlists, and custom display names.
- Physics-driven visualizer caps, configurable gradients/images, four particle
  channels, collision fog, actual PCM waveform, and cover artwork.
- Art subtitles, EQ/picture effects, UI themes, and Linux MPRIS controls.
- Restricted Linux mod workers and documented drawing/event/particle API.
- Resize cleanup and suspension of invisible effects, including Wayland exposure.
- Linux package and Windows portable/per-user installer build recipes.
- GitHub CI/draft-release preparation and Windows/portable/Flathub update design.

Automatic updates and a tested Flathub package are not implemented in this
preview. Windows desktop validation remains separate from Linux coverage.
