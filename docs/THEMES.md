# UI themes, cover art, and controls

Both gear buttons open **the same FireMedia Settings menu**. It contains Themes,
shuffle/repeat controls, Low Detail Mode, subtitle autoload, the mod manager,
and a shortcut to visualizer settings. UI themes and visualizer presets are
separate: `.firemt` changes the player interface; `.firemv` changes the artwork.

## Themes submenu

Open **Settings → Appearance → Customize themes…**.

- **Simple:** choose a hue (0–359°), dark/light appearance, or a neutral gray
  shade instead of hue.
- **Color palette:** choose Default, Ocean, Ember, Forest, Light, or Monochrome,
  then edit Window, Panel, Control, Text, Muted, Accent, Border, and Selection
  colors individually. All support RGB plus alpha, HSV text, and the picker.
- **Advanced:** edit the application font and pixel size, then select any of
  the same eight UI groups to edit its RGBA color. Window and Panel each have
  independent Color/Gradient/Image appearances; Control and Selection support
  Color/Gradient. Text, Muted, Accent, and Border expose their color directly.
  Gradient controls include stop editing, angle, speed, offset, size, and
  transparency. Window/Panel images support crop, grid slice, repeat, and
  Fit/Scale/Stretch, and are embedded into the theme. Switching groups preserves
  edits. Palette and Advanced color editors share the same colors.

Changes apply live and restore at launch. Save as stores or overwrites a named
local theme; Load and Remove manage that library. Import/export works in any
mode through `.firemt`. Imported name collisions receive numbered suffixes.
Color/gradient/image-specific rows hide when their mode is not selected.
Fonts are referenced by installed family name, not bundled font files.
Theme images are embedded raster PNG data, not external file paths or URLs.

A gradient size of 2× repeats twice over its surface; 0.5× shows half a loop.
A full speed/offset cycle is 360°. Surface transparency blends the gradient or
image with the underlying palette color; it does not make the app window see
through to the desktop. Different UI surfaces map the theme to their own bounds.
Native tabs, scroll pages, tables, headers, checkboxes, and menus follow the
selected palette, including light themes. Animated gradients run on the main
Window/Panel surfaces; native widget backgrounds use a static gradient with the
chosen size, angle, and offset. Video pixels and visualizer art keep their own
settings. Animated theme timers stop while their surface is hidden or the
window is minimized/unexposed, and restart when it becomes visible again.

## `.firemt` format

Versioned, validated UTF-8 JSON, maximum 16 MB:

```json
{
  "format": "FireMediaTheme",
  "version": 1,
  "name": "My theme",
  "theme": {
    "mode": "advanced",
    "appearance": "dark",
    "font": "Sans Serif",
    "font_size": 13,
    "surface_mode": "gradient",
    "gradient": [[0, "#102040FF"], [1, "#102040FF"]],
    "speed": 0,
    "offset": 0,
    "size": 1,
    "angle": 0,
    "transparency": 0
  }
}
```

Omitted fields use defaults. Other keys include `hue`, `grayscale`, `colors`
(the eight named palette colors), and `image` (the same embedded image object
used by visualizer presets). The optional `groups` object stores independent
appearance overrides under `window`, `panel`, `control`, and `selection`, using
the same `surface_mode`, `gradient`, `angle`, `speed`, `offset`, `size`,
`transparency`, and `image` fields. Older files without `groups` still load;
their shared appearance remains the fallback for Window/Panel. All eight RGBA
colors remain in `colors`. No raw stylesheet code, executable Python,
external image paths, or network URLs are accepted. Unknown keys do not become
UI code. Font and numeric values are validated before generating Qt styles.

## Cover artwork

For each local song, FireMedia looks in its parent directory for a file named
**`cover`**, case-insensitively, with an image extension. Examples: `cover.png`,
`cover.jpg`, `cover.webp`, `cover.jxl`, `cover.avif`, or `COVER.PNG`. PNG/JPEG
are preferred when multiple files exist. Remaining Qt-supported raster formats
are tried too. JPEG XL and AVIF can fall back to the installed FFmpeg decoder;
actual codec support depends on your Qt/FFmpeg build.

Discovery/decoding runs on background workers and is cached per directory.
Images are limited to 16 MB / 16 megapixels and resized to at most 1024×1024.
Artwork appears in playlist rows and the transport strip. A missing/unreadable
cover uses the normal placeholder and does not stop playback. Changing tracks
clears the previous cover immediately, then displays the new one when ready.
There are no network artwork lookups. Embedded music-file artwork is not used
by this directory-cover feature. Restart/reload the app to refresh replaced
cached covers.

Choose **Visualizer → Background → cover** to use the current song’s artwork
behind the visualizer. Fit/Scale/Stretch and background transparency apply.
A missing cover produces a black background. Cover pixels are dynamic media
artwork and are not exported inside `.firemv` files; that mode resolves the
current track’s directory when playing.

## Scrubbers

The time and volume widgets paint only their track and handle; their widget
backgrounds are transparent. Click anywhere to jump, or drag the handle.
Keyboard seeking and volume adjustment still work.

Volume uses one fixed gradient across the complete **0–150%** slider:

| Position | Volume | Color |
|---|---|---|
| 0/3 | 0% | `#000000FF` |
| 1/3 | 50% | `#00FF00FF` |
| 2/3 | 100% | `#FFFF00FF` |
| 3/3 | 150% | `#FF0000FF` |

Only the portion up to the handle is drawn in color; the right-hand remainder
stays gray. Lowering volume clips the fixed gradient instead of stretching the
whole rainbow into the shorter filled portion.
