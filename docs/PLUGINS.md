# FireMedia Python mods · API v1

`.firemp` files are ZIP script packages. They can register custom visualizers,
react to playback/subtitle/collision events, submit drawing commands, and
request host-managed particles. **Mod code runs in a separate restricted Linux
process, never in the player’s Python interpreter.**

## Install, enable, and update

Open either gear button → **Settings → Manage plugins…**. Install a `.firemp`,
select it, and Enable. Dropping a `.firemp` onto the player also installs it
**disabled**. Select its renderer under **Visualizer → Renderer**, or keep the
built-in bars and use a mod only for overlays/events. Disable and Remove are
available in the manager. Remove deletes the installed copy, not the original
package you selected. At most eight mods can be enabled concurrently.

Enabled packages are remembered by SHA-256. Changed packages require explicit
re-enabling. Versions installed under the former unrestricted loader do not
autostart after this change: enable them again to run them under restrictions.
To install a replacement with the same ID, remove the installed copy first.

## Restriction boundary

Requirements: Linux, a kernel with seccomp-filter support, and `libseccomp2`.
The Debian package declares that dependency. **If the sandbox cannot be
installed, the mod is not executed.** Windows mod execution is currently
disabled; it never falls back to unrestricted Python.

Before any mod code executes, the worker:

- Loads its runtime and receives packaged assets over a private pipe.
- Clears inherited environment secrets, closes extra descriptors, sets memory
  limits, and enables `no_new_privs`.
- Installs a default-deny syscall filter. Filesystem opening/enumeration,
  network sockets, shell/process launch, process inspection/control, namespace
  manipulation, and file-backed memory mappings are not permitted.
- Allows only narrow standard-input/output pipes plus the memory, timing,
  signal-return, and synchronization calls needed by Python.

Even native calls through `ctypes` remain subject to the OS filter. This is
not an import blacklist or a modified `__builtins__` dictionary. See the
[Linux seccomp documentation](https://kernel.org/doc/html/latest/userspace-api/seccomp_filter.html)
and [no-new-privileges documentation](https://kernel.org/doc/html/latest/userspace-api/no_new_privs.html).
The implementation and tests are in `mod_worker.py`, `plugins.py`, and
`tests/test_extended_features.py`.

**Use `api.asset()` to read inside your package.** Ordinary `open()`, including
relative paths, is blocked. No filesystem writes, HTTP requests, external
programs, or additional package installation are provided. Standard modules
already loaded by the runner (including `math`, `random`, `time`, `json`, and
`base64`) can be used. Imports requiring new files/extensions are unavailable.
Packaged helper source can be read with `api.asset` and executed in your own
namespace; this remains inside the same OS restrictions.

The worker has a 384 MiB address-space limit. Initialization has a 2.5-second
wall timeout; subsequent requests have a 200 ms wall timeout, enforced by the
player. Hooks exceeding 50 ms are rejected after returning. Infinite loops
are killed by the parent without freezing playback. Errors, SystemExit,
KeyboardInterrupt, malformed responses, and exceeded budgets disable the mod.
Only bounded, validated JSON commands cross into the native UI—no Python
objects, pickle, arbitrary paths, or Qt objects. The host uses a shared 12 ms
budget for replaying mod drawing commands. This is an OS restriction boundary,
not a formal security audit; it relies on the kernel and runtime/image decoders
being maintained.

## Package layout

```text
my-effect.firemp     (ZIP, renamed .firemp)
  manifest.json
  plugin.py
  assets/spark.png   (optional)
```

`manifest.json` at the archive root:

```json
{
  "format": "FireMediaPlugin",
  "api": 1,
  "id": "yourname.my-effect",
  "name": "My effect",
  "version": "1.0.0",
  "entry": "plugin.py"
}
```

IDs start with a lowercase letter, contain 2–64 lowercase letters, digits,
dots, underscores, or hyphens. Name/version have 1–128 characters. Entry defaults
to `plugin.py`. Paths use `/`; absolute, traversing, duplicate, and backslash
paths are rejected. The archive is never extracted. Limits: 16 MB compressed,
32 MB expanded total, 128 members, 256 KB entry script. Limits apply before
execution; Python code cannot grant itself host access.

The global `api` object is injected into the entry script. `api.version == 1`.
Global functions with event names are registered automatically. Alternatively:

```python
@api.on('onBarCollision')
def sparks(event):
    api.summonParticle(event.x, event.y, channel=2,
                       color=[255, 190, 70, 220],
                       vx=[-30, 30], vy=[90, 180], lifetime=1.4)
```

Enable channel 2 in the visualizer editor for this example to emit. A function
registered both by decorator and event name is called once.

## Asynchronous frames and events

Mods receive event/frame batches asynchronously. The UI never waits for mod
code during an animation frame. Under load, intermediate frame snapshots are
replaced by the latest; discrete events queue up to 256 entries per mod.
Resizing clears cached commands and host particles; replies produced for an old
viewport are discarded, including particle requests. Recompute coordinates from
the next frame’s width/height. Animation frames stop while the player is minimized
or hidden, in every LDM mode. Lifecycle/subtitle events can still be delivered;
no drawing or particles are applied while visualization is suspended. Restoring
resumes with a fresh frame.

Drawing uses the latest completed command list, usually one animation frame
behind the host. Responses are limited to 1 MB, 1024 drawing commands, 32 log
messages, 32 registered renderers, and 400 particle requests per batch.

| Event | Attributes / timing |
|---|---|
| `onLoad` | `api` (version number); after restriction setup and script execution |
| `onUnload` | no fields; best-effort 30 ms grace on an idle worker; forced termination may skip it |
| `onTrackLoad` | `source`, `title`; track requested, before decoding necessarily completes |
| `onPlaybackState` | `playing`, `loaded`, `position` in seconds; when state changes |
| `onSubtitleLoad` | `track` (mpv ID), `source` (external path or empty), `media`; selected subtitle track changes |
| `onSubtitleMessage` | `text`, `position`; decoded text changes; empty clears; emitted even with display off |
| `onBarCollision` | `index`, `x`, `y`, `height`, `impact`; at most one per impacted bar per host frame |
| `update` | `frame`, `dt`; one animation snapshot |
| `draw` | `draw` command recorder, `frame`, `dt`; overlay after selected renderer |

Collision coordinates are pixels, top-left origin. `height` is pixels;
`impact` is relative px/s. Disabled barlines stop collisions; invisible
barlines keep physics/events. Visualizer ticks stop during video,
minimization, and LDM background suspension. Playback/subtitle events still
arrive during video. Mods do not draw over video in this version.

## Frame data

`api.frame` and event `frame` have these fields. Before the first host frame,
`api.frame` is an empty 1×1 placeholder, so initialize assets in `onLoad` and
use frame sizes inside `update`/`draw`.

| Field | Meaning |
|---|---|
| `width`, `height`, `baseline` | logical pixels; baseline measured from top |
| `time` | accumulated animation seconds, not song position |
| `dt` | host delta seconds, capped at 0.06 |
| `paused`, `low_detail` | booleans |
| `levels` | tuple of FFT magnitudes, each 0–1 |
| `bars` | tuple of mappings, one per active bar |

Bar mappings contain `index`, `x` (center), `y` (top), `height`, `cap_y`,
`velocity`, `cap_velocity` (positive upward), and `collision_age` (seconds).
Snapshots are worker-local copies; changing them does not change player state.
FFT level count and bar count can differ in LDM.

## Custom renderers and drawing

```python
def paint(e):
    for bar in e.frame.bars:
        e.draw.rect(bar['x'] - 3, bar['y'], 6, bar['height'], '#88CCFFFF')

api.registerVisualizer('my-bars', 'My custom bars', paint)
```

`api.registerVisualizer(id, name, draw, update=None)` registers a selectable
renderer. IDs use a lowercase first letter followed by up to 63 lowercase
letters/digits/underscores/hyphens. Its full selection ID is
`plugin-id:renderer-id`. Draw is required, update optional. Selected custom
renderers replace built-in bars, while FFT, physics, collisions, wave,
fog, and host particles continue. Global hooks run for all enabled mods.

Drawing methods **record commands**; they do not expose a QPainter or Qt:

| Method | Arguments |
|---|---|
| `e.draw.rect` | `x, y, width, height, color='#FFFFFF', radius=0` |
| `e.draw.ellipse` | `x, y, width, height, color='#FFFFFF'` |
| `e.draw.line` | `x1, y1, x2, y2, color='#FFFFFF', width=1` |
| `e.draw.text` | `x, y, text, color='#FFFFFF', size=16`; y is baseline |
| `e.draw.image` | `image_reference, x, y, width, height` |

Coordinates are bounded to ±100,000, line width 0–50, corner radius 0–1000,
text size 1–144 pixels, text length 1024. Numeric arguments must be finite.
The player validates commands before painting and preserves painter state.
Do not keep drawing contexts across callbacks.

## Packaged assets and images

- `api.asset('assets/name')` returns packaged bytes from memory.
- `api.image('assets/spark.png')` returns an **opaque image reference**, not
  a QImage. Pass it to `e.draw.image`. The host reads only that named package
  member, accepts raster PNG/JPEG/WebP/BMP only, limits it to 4 MB / 4
  megapixels, and caches decoded pixels. SVG/vector formats are rejected before
  decoding so images cannot request outside files or URLs.
- `api.log(message)` adds a manager log message, up to 2048 characters. The
  manager retains its last 100 messages.

## Host particles and channels

`api.summonParticle(x, y, **options)` queues a particle request. Its return value
reports whether the worker accepted the request, not whether the host later
emits it. LDM, disabled channels, and the shared **particle limit chosen in Settings** can drop
requests. Fog is a separate native pool, capped at 96.

| Option | Meaning |
|---|---|
| `channel` | integer **1–4**, defaults to 1 |
| `color`, `end_color` | starting/ending Color3 or Color4 |
| `vx`, `vy`, `ax`, `ay` | initial velocity / acceleration, fixed or range |
| `cbaccel_vx`, `cbaccel_vy` | additive acceleration change per second |
| `expaccel_vx`, `expaccel_vy` | acceleration multiplier per second |
| `lifetime` | fixed/ranged seconds, clamped 0.02–30 |
| `size` | fixed/ranged image size, clamped 1–128 px |
| `start_transparency`, `mid_transparency`, `end_transparency`, `mid_time` | channel fade overrides; middle stop still requires channel mid toggle |

Origin is top-left; positive VY moves upward. Each channel has independent
emission, image, motion, gradient, fade, and enable settings. The selected
channel supplies defaults for omitted options. Existing particles retain their
sampled motion/fade and use their channel’s current image. Unsupported options
or nonfinite values disable the offending mod.

Color4 is **R,G,B,A**, each byte 0–255; Color3 omits opaque alpha. Hex uses
`#RRGGBB` or **`#RRGGBBAA`**. HSV strings use degrees and percentages:
`hsv(220,69,100,50)`. SoftN is a scalar or increasing `[minimum, maximum]` pair.

## Build the example

Editable source: `examples/plugins/orbit-stars/`.

```sh
python3 tools/build_plugins.py
```

Install `dist/plugins/orbit-stars.firemp` and choose its radial renderer.
It uses only the restricted API and preloaded `math` module. Example source
is licensed under FireMedia’s GPL-3.0-or-later license.
