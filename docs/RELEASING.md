# GitHub preparation and releases

Public repository: [PrismByteDev/FireMedia](https://github.com/PrismByteDev/FireMedia).
GitHub Actions builds the committed source. Updates and Flathub publication remain
separate work; building a package does not enable an updater or publish a release.

## First push

Create an **empty public repository** in PrismByteDev named FireMedia, without
generating a second README/license. Use `main` as the initial branch. Review
the files being added; do not commit binaries, vendor downloads, private state,
media libraries, credentials, or signing keys. `.gitignore` excludes local build
and app state; the source exporter additionally uses an explicit allowlist.

If starting from an exported folder without Git metadata:

```sh
git init -b main
git add .
git diff --cached --stat
git commit -m "Prepare FireMedia public preview"
git remote add origin https://github.com/PrismByteDev/FireMedia.git
git push -u origin main
```

Use your own Git author identity. Keep the GPL-3.0-or-later LICENSE. The archived
web prototype retains its MIT license. Source archives preserve both.

Enable Actions, private vulnerability reporting, and the repository's normal
pull-request review controls. Protect `main` and version tags as appropriate
for the organization. CI has read-only repository permissions; only the final
draft-release job gets contents-write permission. All external actions are
pinned to verified full commits and Dependabot proposes updates. No untrusted
PR code runs with a write token or release credentials.

## What the workflows do

- **CI:** Linux tests/builds on main pushes and pull requests. Manual runs can
  also build Windows. Linux tests use an isolated D-Bus session and a virtual
  X11 display. Real GPU/desktop rendering is a separate check.
- **Build and test:** reusable Linux/Windows workflow. Windows builds a portable
  ZIP and a per-user Inno Setup installer, then runs portable core tests and a
  packaged-startup smoke check. This is not a substitute for desktop playback.
- **Draft release:** version-tag pushes or manual runs build both platforms,
  assemble source/inventory/checksums, and create a **draft** release. Reruns can
  update that draft but refuse to overwrite an already-published release.

Use standard Ubuntu/Windows runners. Windows packages build only for explicit
manual requests and release tags, not on every PR. Temporary artifacts expire
after one day and superseded runs for the same trigger and branch are canceled.
Manual builds run independently of push/PR checks. Build minutes are
free for public repos on standard runners; artifact storage still has an
allowance. Check organization storage/budgets before retaining many builds.
No paid larger runners or private signing service is configured.

## Run a build and download it

Open **Actions → CI → Run workflow**, select `main`, leave **Also build and test
the Windows packages** checked, and run it. Pushes and pull requests run Linux
checks automatically; this manual option adds the Windows ZIP and installer.

When the run succeeds, open its summary and download **linux-build** or
**windows-build** from **Artifacts**. Sign in to GitHub to download artifacts.
The **appimage-build** artifact contains the Linux AppImage. The Windows artifact contains the portable ZIP and setup EXE; extract the artifact
first, then extract the portable ZIP and run `FireMedia/FireMedia.exe`, or run the
installer. Artifacts expire after one day, so download them promptly or run a new
build. A CI artifact is a test build; reviewed releases belong on Releases.

Windows dependency lookup uses the job's read-only GitHub token to avoid shared
runner API limits. That token is sent only to the GitHub API, never to binary
download hosts. Local builds also work without it, subject to public API limits.
Linux tests print periodic stack traces if they stall and have a hard timeout,
so a blocked GUI test cannot consume the full job timeout without diagnostics.

## Version and release assets

The single application version is `firemedia.__version__`, currently `0.3.0`.
Setuptools, `.deb`, installer builds, and release assembly consume it. Stable
tags are `vX.Y.Z`. Preview tags may use Python suffixes such as `v0.3.0rc1`;
the draft is marked prerelease. The workflow fails if the tag and code differ.

The draft includes:

| Asset | Purpose |
|---|---|
| `firemedia_X.Y.Z_all.deb` | Debian/Ubuntu dependency-based package |
| `FireMedia-X.Y.Z-windows-x64.zip` | Complete Windows portable folder |
| `FireMedia-X.Y.Z-windows-x64-setup.exe` | Per-user installer |
| `FireMedia-X.Y.Z-x86_64.AppImage` | Linux portable image with signed automatic updates |
| `FireMedia-X.Y.Z-source.zip` | FireMedia source, docs, build scripts, and licenses |
| `release-info.json` | Version/platform/size/hash/URL inventory; not a signed update feed |
| `update.json` | Authenticated stable update metadata (requires signing secret) |
| `SHA256SUMS` | SHA-256 hashes of all other attached files |

Python wheel/sdist builds are retained in the Linux workflow artifact. They are
not automatically uploaded to PyPI. There is no macOS release job.
Flatpak preparation is tracked [separately](../packaging/flatpak/README.md).

Before tagging, update CHANGELOG, run tests, and run the real desktop playback
check on Linux/Windows. Commit the version, then create/push its tag. A manual
release run needs an existing tag. Never move a published version tag.

## Review before publishing the draft

Verify all three build jobs succeeded and download/test the actual packaged builds.
Check song/video playback, seek, pause/resume, cover/subtitle loading, playlist
formats, presets, restart persistence, resize, and minimized effects. Verify
the checksum file against the downloaded assets. Windows smart-screen/publisher
signing and manual desktop compatibility are separate from a successful build.

Include notices and corresponding source/build information for the exact bundled
Qt/PyQt6, NumPy, libmpv, FFmpeg, codec, and other dependency builds. The Windows
spec copies Python package metadata/licenses and playback notices, and embeds
FireMedia source; that does not by itself certify that every third-party source
obligation has been satisfied. Keep the playback build provenance file. Preserve
and publish any additional corresponding source/build recipes required by those
exact builds before distributing binaries. Linux `.deb` dependencies come from
the distribution rather than being bundled by FireMedia.

Then publish the reviewed draft from GitHub. Consider enabling immutable releases
after attaching the complete reviewed asset set. Configure the explicitly approved FIREMEDIA_UPDATE_SIGNING_KEY secret before
releasing. Only published stable signed releases are used for automatic updates.
See [UPDATES.md](UPDATES.md) for testing and key-backup requirements.

References: [Actions security](https://docs.github.com/en/actions/reference/security/secure-use),
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
[release management](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).
