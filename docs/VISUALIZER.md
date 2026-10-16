# Visualizer presets and customization

Open the effects row → **Visualizer**, or Settings → **Visualizer**.
Settings preview live. Save as creates a named preset; Update overwrites a
custom preset; Rename/Remove manage custom presets. Built-ins remain available.
Unsaved live settings survive restarting the app, but changing to another
preset loads that preset's saved values. Bar count and falling-bar smoothing
are independent global preferences.

Built-ins replace Fireworks/Aurora/Spectrum:

| Preset | Behavior |
|---|---|
| Default | Rainbow bars and fireworks; 36°/s gradient rotation |
| Classic | Green bars, red barlines, true peaks, low gravity, no particles |
| Frost | Icy white/cyan/blue gradient |
| Amethyst | Pink, lavender, purple gradient with a partial-white collision pulse |
| Ember | Warm gradient with orange starting particles and red fade |
| Starry | Blue bars, star-shaped sparks, brief partially white collision flash |

**Background** supports Off (black), Color, Gradient, Image, and the current
song’s directory **cover**. Cover mode resolves `cover.*` beside each local
track and updates while switching songs. It has Fit/Scale/Stretch mapping. See
[cover art and UI settings](THEMES.md). Background mode controls hide unless
they apply to the selected mode. Its
transparency is composited against black and does not make the desktop window
transparent. Background gradients have an angle and optional rotation speed.

## Colors and gradients

Color4 is RGB plus an alpha channel; Color3 is opaque RGB. The picker includes
RGB/alpha controls. Text accepts `#RRGGBB`, `#RRGGBBAA`, or `hsv(H,S,V,A)`.
HSV uses hue degrees and saturation/value/alpha percentages. Hex alpha is last.
For example, `#80C0FF80` is half-transparent pale blue.

Each gradient editor offers named colors or **Custom**, with 2–16 editable
position/color stops. Add/remove stops and adjust position (%) and color.
Horizontal gradients wrap: 360° = one loop. Default speed 36°/s gives a 10-second
loop; offset shifts the initial phase. Each speed-controlled gradient also
has a **size multiplier**: 2× repeats the gradient twice across the surface,
0.5× displays half a loop. Bars, barline overrides, each particle channel’s
start-gradient override, waves, and the background expose separate size
settings. Barline/particle overrides have independent speed and offset. The vertical gradient multiplies the
horizontal RGBA color from top (0%) to bottom (100%). White preserves color;
black darkens it; stop alpha multiplies opacity.

Frost, Amethyst, Ember, and Starry use mirrored color stops: colors travel to
the far end of the palette and back to the starting color, so wrapping has no
color jump. These presets move in the opposite direction at −36°/s. Default's
Rainbow continues at +36°/s.

**Transparency**: 0% opaque, 100% invisible. On a collision, the bar/barline
uses its collision transparency, then linearly returns to stock transparency
over its configured fade time. A zero fade time disables that transient.
The optional **collision tint** mixes the bar color with a Color4 tint; its
alpha determines strength. Starry uses partial white, fading over 0.6 seconds.

## Image presets

Bar decals, barline decals, particle images, and background images are embedded
as PNG pixels directly in the preset. No dependency on the original file path
remains. Choose a raster image under 16 MB / 16 megapixels; it is reduced to at
most 2048×2048 and must fit within 4 MB after PNG encoding.

**Crop / slice / mode** applies these operations in order:

1. Crop left/top/right/bottom percentages trim the source. Some image area must
   remain.
2. Slice into a grid (1–16 columns/rows) and select a zero-based cell index,
   row-major. This selects a static tile, not an animated sprite sheet.
3. Repeat the selected tile 1–8 times horizontally/vertically in its target.
4. Fit/Scale/Stretch determines each tile's mapping: **Fit** preserves aspect
   inside the target (letterboxing); **Scale** preserves aspect while covering
   and clipping the target; **Stretch** fills the target without preserving
   aspect ratio. This is uniform grid slicing, not nine-slice border scaling.

Decals draw over the gradient-filled bars/barlines. Particle images replace
the small default cross-shaped stars. Their size can be fixed or ranged.
Without a start-gradient override, particle images preserve their original
RGB. Start-gradient override tints them; end-color override gradually tints
them toward the ending RGB. Texture alpha, Color4 alpha, and fade transparency
multiply. All image options, including crop/slice/repeat, export inside presets.

## Bars, barlines, and physics

Bar width is a percentage of one frequency slot, minus padding in pixels;
barline width is a percentage of the resulting bar width. Barline height is
pixels. Widths can exceed 100% for overlapping styles. Hidden bars keep their
FFT and collision physics. **Barline enabled** switches off cap physics and
collisions; **Barline visible** only switches off drawing.

Rising bars always jump immediately to the measured level. Smooth falling
bars only affects downward release. Fall speed controls that release.

Barline gravity is px/s²; spring is the collision restitution factor (0–2).
**Barline launch height (px)** is the maximum additional rise above a collision’s
contact point. It caps launch speed and position; weaker impacts can travel
less. Set it to **0** to prevent upward launches. The default is 120 px. This
limit also works with zero gravity. It affects new launches, so already airborne
barlines finish their existing trajectory. Peak mode always prevents launches.
Bounce controls rebounds after falling onto a bar. Rising bars can still launch
a cap when Bounce is off. **Peak** disables launches and rebounds entirely:
a peak snaps to rising bars, then falls toward them under gravity. Classic
uses peak mode and gravity 180. Default uses launch/bounce and gravity 1800.
A separate gradient override can recolor barlines independently of bars.

## Waves and collision fog

**Wave** draws a thin, unfilled oscilloscope trace of the decoded audio samples
between the background and bars. It uses the same timestamped frames and playback
clock as the spectrum, without a separate decoder or generated sine animation.
Silence produces a straight line, and pausing holds the last trace. The default
is **Solid**, RGBA **`#FFFFFF33`**, with no additional transparency.

Audio window chooses how much sound appears across the screen (1–46 ms, default
20 ms); shorter windows show fewer oscillations. Height controls amplitude as a
percentage of the screen, Vertical position places the center line, and Trace
width controls thickness. Gradient mode exposes speed, offset, and size;
solid mode hides those controls. Transparency and Color4 alpha multiply.
The former procedural Cycles and Motion fields are ignored when loading old
presets. Existing saved wave colors remain unchanged. The wave also works in LDM.

**Fog** uses a separate pool of at most **96** soft radial particles. Each
collision emits puffs at the **bottom of the screen**, near the impacted bar’s
horizontal position. Puffs spread, slowly rise, and fade over their lifetime.
Toggle fog, set its RGBA color, collision emission, lifetime, radius, and rise
speed. Fog draws over the bottom of the bars and does not consume the regular
400-particle budget. LDM disables and clears fog. There is no continuous fog
emission without collisions. The entire enabled field is clickable. If fog is
enabled while LDM is active, the editor explains that LDM hides it; turn LDM
Off in Settings to see fog.

## Resizing and invisible effects

Resizing the visualizer, including fullscreen and opening/closing panes, clears
all four particle channels and fog and resets bar/cap physics. Fresh effects
spawn in the new viewport. Pending mod drawing/particle replies from the old
viewport are discarded. Subtitle sparks also clear when their overlay resizes.

Minimizing or hiding the window stops visualizer animation and physics, mod
animation frames, subtitle sparks, animated theme timers, and the extra audio
analysis decoder, even with LDM **Off**. Playback and media controls continue.
Changing quality or themes while minimized does not restart effects. Restoring
resumes analysis at the current playback position, without replaying a backlog.
On Wayland the player also checks compositor exposure, because an invisible
minimized window can temporarily report a normal Qt window state.

## Four particle channels

The Particles tab has a **Channel 1–4** selector. Each channel independently
controls enable, emission, collision emission, image, size, fade, motion, and
gradient overrides. Channel 1 inherits older presets; channels 2–4 start
disabled. Switching channels preserves edits in all other channels. Saving,
loading, exporting, and importing presets preserves all four channels and their
embedded images. The **400-particle cap is shared across the four channels**;
fog has its own pool. Mods can request a specific channel using `channel=1..4`.

## Particle motion and SoftN

**Range** enables minimum/maximum sampling. Per-particle values are sampled
once at spawn; emission rate is sampled per bar per tick, and collision
emission per bar impact. Fractional counts use stochastic rounding. All
particles share the existing cap of **400**. LDM removes particles and caps
active bars at 24 while preserving your preferred count.

Emission is particles per active bar per second above the audio activity
threshold; collision emission is additional particles per impact. Fade time
is total lifetime. Start/end transparency interpolate linearly; optional mid
transparency inserts a middle stop at a specified number of seconds, bounded
to the particle's lifetime. Mid-stop opacity, lifetime, velocities, and
accelerations all support ranges.

X increases rightward; positive VY increases **upward**. Motion is integrated
in seconds, using these updates on each animation tick:

```text
acceleration = (acceleration + cbaccel * dt) * expaccel ** dt
velocity += acceleration * dt
x += VX * dt
y -= VY * dt
```

`cbaccel` adds to acceleration each second; `expaccel` multiplies it. A
multiplier of 1 preserves it, 0 removes it. Acceleration is bounded for numerical
stability. Existing particles finish with their sampled motion/fade values;
new particles use edited settings. Live image changes use the current texture.

## Files and compatibility

Export/import custom visualizer presets as **`.firemv`** through the preset
editor. Format is versioned UTF-8 JSON (up to 64 MB, allowing embedded images in
all channels):

```json
{
  "format": "FireMediaVisualizerPreset",
  "version": 1,
  "name": "My blue stars",
  "preset": { "speed": 36, "background_mode": "color" }
}
```

Omitted fields use Default values; normal exports contain every field plus
embedded image data. Imports validate field types, ranges, colors, gradient
positions, image dimensions, crop, and slicing. Imported names receive a
numbered suffix if needed. `.firemp` contains Python mod code, executed only in a restricted Linux
worker; `.firemv` is preset data and does not execute scripts. Subtitle presets remain `.firemsub`.
Old theme names load the new Default; queue, bar count, EQ, and subtitle data
remain intact.

## Preset field reference

These keys live inside `preset`. SoftN accepts a scalar or `[minimum, maximum]`.
Image values are `null` or embedded-image objects. Booleans use `true`/`false`.
The canonical `channels` list contains up to four particle-setting dictionaries;
missing channels are disabled. Top-level particle keys remain a backward-
compatible alias for **channel 1**. When `channels` is present it takes priority
over the flat particle keys. Normal exports include all four channel records.

### Background

| Key | Meaning | Type / range |
|---|---|---|
| `background_mode` | Background | off, color, gradient, image, cover |
| `cover_mode` | Song cover image mode | fit, scale, stretch |
| `background_color` | Background color (RGBA) | color |
| `background_gradient` | Background gradient | gradient |
| `background_angle` | Gradient angle (°) | number, -360–360 |
| `background_speed` | Gradient rotation (°/s) | number, -360–360 |
| `background_size` | Gradient size (×) | number, 0.1–16 |
| `background_transparency` | Background transparency (%) | number, 0–100 |
| `background_image` | Background image | image |

### Gradient settings

| Key | Meaning | Type / range |
|---|---|---|
| `horizontal` | Horizontal gradient | gradient |
| `speed` | Horizontal speed (°/s) | number, -720–720 |
| `size` | Horizontal gradient size (×) | number, 0.1–16 |
| `offset` | Horizontal offset (°) | number, -3600–3600 |
| `vertical` | Vertical gradient · multiplied | gradient |

### Wave

| Key | Meaning | Type / range |
|---|---|---|
| `wave_enabled` | Wave enabled | bool |
| `wave_mode` | Wave color mode | solid, gradient |
| `wave_color` | Wave color (RGBA) | color |
| `wave_gradient` | Wave gradient | gradient |
| `wave_speed` | Gradient speed (°/s) | number, -720–720 |
| `wave_offset` | Gradient offset (°) | number, -3600–3600 |
| `wave_size` | Gradient size (×) | number, 0.1–16 |
| `wave_height` | Wave height (% of screen) | number, 0–60 |
| `wave_window` | Audio window (ms) | number, 1–46 |
| `wave_position` | Trace center (% of screen height) | number, 0–100 |
| `wave_line_width` | Trace width (px) | number, 0.5–8 |
| `wave_transparency` | Wave transparency (%) | number, 0–100 |

### Fog

| Key | Meaning | Type / range |
|---|---|---|
| `fog_enabled` | Collision fog enabled | bool |
| `fog_color` | Fog color (RGBA) | color |
| `fog_emission` | Fog puffs per collision | soft, 0–10 |
| `fog_lifetime` | Fog lifetime (s) | soft, 0.2–20 |
| `fog_radius` | Fog radius (px) | soft, 5–250 |
| `fog_rise` | Fog rise (px/s) | soft, 0–100 |

### Bar settings

| Key | Meaning | Type / range |
|---|---|---|
| `bars_visible` | Bars visible | bool |
| `bar_width` | Bar width (% of slot) | number, 1–200 |
| `bar_padding` | Bar padding (px) | number, 0–100 |
| `bar_transparency` | Bar transparency (%) | number, 0–100 |
| `bar_collision_transparency` | Collision transparency (%) | number, 0–100 |
| `bar_collision_fade` | Collision fade time (s) | number, 0–10 |
| `collision_tint` | Enable collision tint | bool |
| `collision_color` | Collision tint (RGBA) | color |
| `bar_decal` | Bar decal | image |

### Barline settings

| Key | Meaning | Type / range |
|---|---|---|
| `line_enabled` | Barline enabled | bool |
| `line_width` | Barline width (% of bar) | number, 1–300 |
| `line_height` | Barline height (px) | number, 0.5–80 |
| `line_decal` | Barline decal | image |
| `line_visible` | Barline visible | bool |
| `line_transparency` | Barline transparency (%) | number, 0–100 |
| `line_collision_transparency` | Collision transparency (%) | number, 0–100 |
| `line_collision_fade` | Collision fade time (s) | number, 0–10 |

### Physics

| Key | Meaning | Type / range |
|---|---|---|
| `spring` | Barline spring (restitution) | number, 0–2 |
| `gravity` | Barline gravity (px/s²) | number, 0–10000 |
| `launch_height` | Barline launch height (px) | number, 0–1000 |
| `bounce` | Barline bounce | bool |
| `peak` | Barline represents peak · no launch | bool |
| `line_gradient_override` | Barline gradient override | bool |
| `line_gradient_speed` | Barline gradient speed (°/s) | number, -720–720 |
| `line_gradient_offset` | Barline gradient offset (°) | number, -3600–3600 |
| `line_gradient_size` | Barline gradient size (×) | number, 0.1–16 |
| `line_gradient` | Barline horizontal gradient | gradient |

### Particles

| Key | Meaning | Type / range |
|---|---|---|
| `particles_enabled` | Particles enabled | bool |
| `particle_decal` | Particle image | image |
| `particle_size` | Particle image size (px) | soft, 1–128 |
| `emission_rate` | Emission rate (per bar / s) | soft, 0–400 |
| `collision_emission` | Collision emission (per impact) | soft, 0–100 |
| `start_transparency` | Start transparency (%) | soft, 0–100 |
| `mid_enabled` | Enable mid transparency | bool |
| `mid_time` | Mid transparency time (s) | soft, 0–30 |
| `mid_transparency` | Mid transparency (%) | soft, 0–100 |
| `end_transparency` | End transparency (%) | soft, 0–100 |
| `fade_time` | Fade time (s) | soft, 0.02–30 |
| `start_vx` | Starting VX (px/s) | soft, -3000–3000 |
| `start_vy` | Starting VY (px/s; + is up) | soft, -3000–3000 |
| `accel_vx` | Acceleration VX (px/s²) | soft, -10000–10000 |
| `accel_vy` | Acceleration VY (px/s²) | soft, -10000–10000 |
| `cbaccel_vx` | Acceleration change X (/s) | soft, -10000–10000 |
| `cbaccel_vy` | Acceleration change Y (/s) | soft, -10000–10000 |
| `expaccel_vx` | Acceleration multiplier X (/s) | soft, 0–10 |
| `expaccel_vy` | Acceleration multiplier Y (/s) | soft, 0–10 |
| `particle_gradient_override` | Particle start gradient override | bool |
| `particle_gradient_speed` | Particle gradient speed (°/s) | number, -720–720 |
| `particle_gradient_offset` | Particle gradient offset (°) | number, -3600–3600 |
| `particle_gradient_size` | Particle gradient size (×) | number, 0.1–16 |
| `particle_gradient` | Particle horizontal gradient | gradient |
| `particle_end_override` | Fade particle color override | bool |
| `particle_end_color` | Particle end color (RGBA) | color |

Image object: `data` (base64 PNG), `crop` (left/top/right/bottom fractions),
`columns`, `rows`, `cell`, `repeat_x`, `repeat_y`, and `mode` (`fit`, `scale`,
`stretch`). Gradient value: `[[position, color], ...]`, position 0–1. Export
canonicalizes colors to `#RRGGBBAA`. Cover art is resolved dynamically, not
embedded into preset exports.
