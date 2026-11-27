# Plan: AI-controlled USB keyboard and mouse

Status: **proposal, not implemented.** Review this before any code is written.

## Goal

Use the same Seeed XIAO ESP32-S3 as a **USB keyboard and mouse that an AI
model drives**. The board plugs into the *target* computer as a plain composite
HID device. The AI runs somewhere else and sends it text, key combos and mouse
actions over Wi-Fi. The target needs no software, driver or pairing.

```
 ┌──────────────┐  MCP (stdio)  ┌────────────┐  HTTP + token   ┌──────────────┐  USB HID   ┌────────────┐
 │ AI model     │ ────────────▶ │ MCP server │ ──── Wi-Fi ───▶ │ XIAO ESP32-S3│ ─────────▶ │ target PC  │
 │ (Claude etc.)│               │ (Python)   │    (LAN)        │ firmware     │ kbd+mouse  │            │
 └──────────────┘               └────────────┘                 └──────────────┘            └────────────┘
```

## Decisions so far

- **Keyboard layout: US (en_US) only.** The target computers must use the US
  layout. Characters outside ASCII are rejected, not mistyped.
- **Keyboard and mouse in one device.** It is a composite USB HID: a keyboard
  plus an **absolute** mouse.

## Non-goals (first version)

- **Seeing the screen.** The AI acts blind (see "Open questions"). This hurts
  the mouse most, because clicking needs to know where things are.
- TLS on the device. The device trusts the local network, and the token is the
  only guard (see Security).
- Reaching the device from outside the LAN.
- Other keyboard layouts.

## Components

### 1. Firmware: `usb_ai_hid/usb_ai_hid.ino`

A new sketch next to the mouse jiggler. It uses the same board, FQBN and
`build.env`.

- **USB:** a composite of `USBHIDKeyboard` and `USBHIDAbsoluteMouse`, with
  product name "USB Keyboard" and no CDC serial (same USB settings as the
  jiggler). Both are standard boot-class HID devices that macOS, Windows and
  Linux support natively.
- **Why an absolute mouse:** the AI says "go to (x, y)" and the pointer lands
  there. It doesn't have to track position or deal with OS pointer
  acceleration, which distorts relative moves. The HID range is 0–32767 on each
  axis and the OS maps it onto the screen. On multi-monitor setups the mapping
  is OS-specific: usually the primary display on macOS, the whole virtual
  desktop on Windows. Testing will confirm this.
- **Wi-Fi:** station mode, with mDNS name `ai-hid.local`. It reconnects on its
  own if the link drops.
- **HTTP API** (`WebServer`, port 80, JSON bodies). Every endpoint except the
  setup page needs `Authorization: Bearer <token>`, compared in constant time.
  Coordinates are **normalized floats 0.0–1.0** (fraction of screen width and
  height), so the device needs no screen-size setting.

  | Method | Path | Body | Effect |
  |---|---|---|---|
  | GET  | `/status`       | none | `{usb_mounted, busy, version}` |
  | POST | `/type`         | `{"text": "...", "delay_ms": 8}` | types US-ASCII text, returns when done |
  | POST | `/keys`         | `{"keys": ["ctrl","alt","t"]}` | presses the combo, then releases it |
  | POST | `/mouse/move`   | `{"x": 0.5, "y": 0.5}` | moves the pointer to an absolute position |
  | POST | `/mouse/click`  | `{"x":0.5,"y":0.5,"button":"left","count":1}` | optional move, then click (count 2 = double-click) |
  | POST | `/mouse/drag`   | `{"from":[x,y],"to":[x,y],"button":"left","duration_ms":300}` | press, move in steps, release |
  | POST | `/mouse/scroll` | `{"dy": -3, "dx": 0}` | wheel and pan, in notches |
  | POST | `/sequence`     | `{"steps": [ {"keys":[...]}, {"text":"..."}, {"click":{...}}, {"sleep_ms":500} ]}` | runs the steps in order |
  | POST | `/release`      | none | releases all keys and buttons (panic) |

  - Key names: modifiers (`ctrl`, `shift`, `alt`, `gui`/`cmd`/`win`, plus
    left/right variants), `enter`, `tab`, `esc`, `backspace`, `delete`, arrows,
    `home/end/pageup/pagedown`, `f1`–`f24`, and single printable ASCII
    characters. Unknown names are rejected with 400, and nothing is sent.
  - Mouse buttons: `left`, `right` and `middle`. Clicks can be combined with
    held modifiers, e.g. `{"keys":["cmd"], "click":{...}}` in a sequence step.
  - Limits: 2000 chars per `/type`, 6 non-modifier keys per combo, 50 steps per
    sequence, and coordinates clamped to 0–1. Text that is too long gets a 413,
    and non-ASCII text a 422. The MCP server splits long text into chunks.
  - One request at a time. A second request during an action gets 409 `busy`.
- **Provisioning (no secrets in the image):** on first boot, or when BOOT is
  held for 3 s after power-up, the board starts a SoftAP `AI-HID-XXXX` with a
  captive setup page. There you enter the Wi-Fi SSID and password. The board
  generates a random 32-byte token and shows it **once**. Both are stored in
  NVS (`Preferences`), so the release image stays generic and CI needs no
  secrets.
- **Kill switch:** a short press of BOOT during operation aborts the current
  action, releases all keys and buttons, and refuses input until the next
  press. The onboard LED shows the state: off when idle, blinking while active,
  solid when disabled.

### 2. MCP server: `mcp/ai_hid_mcp.py`

A Python [MCP](https://modelcontextprotocol.io) server over stdio, run with
`uv run` (dependencies declared inline, like `hardware/enclosure.py`).

- Config comes from environment variables:
  - `AI_HID_URL`, default `http://ai-hid.local`.
  - `AI_HID_TOKEN`.
  - `AI_HID_SCREEN` (optional), e.g. `1920x1080`. When it is set, mouse tools
    also accept pixel coordinates and convert them to the 0–1 range, which
    pairs well with screenshots.
- Tools:
  - Keyboard: `type_text(text)` and `press_keys(keys)`.
  - Mouse: `move_mouse(x, y)`, `click(x, y, button, count)`,
    `drag(from_x, from_y, to_x, to_y)` and `scroll(dy, dx)`.
  - Both: `run_sequence(steps)`, `release_all()` and `status()`.
- Tool descriptions warn the model that it cannot see the screen. They tell it
  to add waits after actions that open windows, and to prefer keyboard
  shortcuts over clicking when it doesn't know the layout.
- Registering it with Claude Code:
  `claude mcp add ai-hid -e AI_HID_TOKEN=... -- uv run mcp/ai_hid_mcp.py`

### 3. Build, CI, release

- Makefile: `DEVICE ?= mouse` keeps the jiggler, and `DEVICE=ai-hid` selects
  the new sketch. Output goes to `build-out/<device>/` and
  `dist/usb-<device>-xiao-esp32s3-<version>-full.bin`. (This is the plumbing
  from the closed PR #4, reused.)
- The composite action takes a `device` input. CI builds both sketches in a
  matrix. A release publishes both images and one `SHA256SUMS`.
- CI also runs the MCP server's tests (below) with `uv`.
- Partition scheme `default_8MB` still fits. Wi-Fi brings the image to about
  1 MB.

### 4. Docs

- A README section for the AI device: flash, provision, connect MCP, the US
  layout requirement, and security notes.
- Repo name: `usb-mouse-jiggler` no longer describes the whole repo. Renaming
  it is your call and is not part of this work.

## Security

This device is a **remote keyboard and mouse** for whatever computer it is
plugged into. Anyone with the token, and access to the LAN, can do anything
the logged-in user could. The design limits that risk:

- A random per-device token from provisioning, which is never in the firmware
  image or the repo. Re-provisioning rotates it.
- HTTP is plaintext, so the token can be sniffed on the LAN. Use it on a
  trusted network only. HTTPS on the ESP32 is possible later, at a cost in
  memory and setup.
- The physical kill switch (BOOT), the per-request limits, and one request at
  a time.
- The setup AP runs only on first boot or when BOOT is held, never otherwise.
- The README will say it plainly: plug it only into machines you own or are
  allowed to control.

## Testing

- **Firmware:** CI compiles it. The key-name parser and the coordinate mapping
  (0–1 to 0–32767, with clamping) are pure functions kept apart from the USB
  code, so they can be checked on the host too.
- **MCP server:** pytest against a fake device (a small local HTTP server). The
  tests cover chunking, pixel-to-normalized conversion, auth headers, error
  mapping (400/409/413/422), and rejection of unknown keys.
- **On the board (manual checklist), on macOS, Windows and Linux:**
  - provisioning and `/status`
  - typing into a text editor, and combos (`cmd+space`, `ctrl+alt+t`)
  - the pointer landing on corners and the center (0,0 / 1,1 / 0.5,0.5)
  - left, right and double click, drag selecting text, scrolling
  - the kill switch during a long `/type` and during a drag
  - reconnect after a Wi-Fi drop, and a wrong token returning 401

## Milestones (one PR each)

1. Firmware keyboard and mouse with hard-coded test Wi-Fi from a gitignored
   `secrets.h`: HID, all endpoints, token auth.
2. Provisioning over SoftAP, NVS storage, the BOOT kill switch and the LED.
3. MCP server, its tests, and the README section.
4. Build/CI/release matrix for both firmwares.

## Open questions for you

1. **Screen feedback.** With the mouse in scope, blind control gets much
   weaker: the AI can only click where it guesses things are. Options for a
   later milestone:
   - an HDMI capture card on the AI's machine, which works with any target,
     even BIOS;
   - screenshots taken on the target;
   - you describing the screen.
2. **Where does the AI run?** Claude Code or Claude Desktop through MCP is
   assumed. If you want a standalone agent loop instead (Claude API with tool
   use), that replaces milestone 3.
