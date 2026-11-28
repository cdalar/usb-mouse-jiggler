# Plan: AI-controlled USB keyboard and mouse, with HDMI screen capture

Status: **proposal, not implemented.** Review this before any code is written.

## Goal

Let an AI model operate a separate computer (the **target**) the way a person
at its desk would: it sees the screen, then types and clicks.

- **Hands:** the Seeed XIAO ESP32-S3 plugs into the target as a plain USB
  **keyboard plus absolute mouse**. It takes commands over Wi-Fi.
- **Eyes:** an off-the-shelf **HDMI capture card** takes the target's video
  output and shows up on the controller as a webcam.
- **Brain:** Claude (Claude Code or Claude Desktop) on the user's **MacBook
  Pro** (the **controller**), through a local MCP server that ties the two
  together.

The target needs no software, driver or pairing. This also works on locked-down
machines, login screens, BIOS/UEFI setup and a fresh OS install.

## Physical setup

```
                         ┌──────────────── TARGET PC ────────────────┐
                         │   HDMI out                    USB port    │
                         └──────┬───────────────────────────┬────────┘
                                │ HDMI cable                │ USB-C cable
                                │ (or USB-C→HDMI adapter)   │ (also powers the XIAO)
                                ▼                           ▼
                      ┌───────────────────┐       ┌───────────────────┐
                      │ HDMI capture card │       │ XIAO ESP32-S3     │
                      │ (UVC "webcam")    │       │ USB keyboard      │
                      └─────────┬─────────┘       │ + absolute mouse  │
                                │ USB 3           └─────────┬─────────┘
                                │ (USB-C, or C→A adapter)   │ Wi-Fi: HTTP + token
                                ▼                           │
                ┌───────────────────────────────────┐       │
                │ CONTROLLER: MacBook Pro (USB-C)   │◀──────┘
                │                                   │
                │  MCP server                       │
                │   ├─ screenshot()  ← capture card │
                │   └─ type / keys / click → XIAO   │
                │  Claude Code / Claude Desktop     │
                └───────────────────────────────────┘
```

- The capture card and the XIAO never connect to each other. The MCP server
  on the controller is the only thing that uses both.
- The controller only needs **one USB-C port**, for the capture card. The XIAO
  talks to it over Wi-Fi.
- The controller must be within cable reach of the target, because the capture
  card plugs into it by USB. Remote targets are a non-goal (see below).
- The MacBook Pro's own HDMI port (14″/16″, 2021 and later) is **output
  only**, so it cannot replace the capture card.

### Parts list

| Part | Where it goes | Approx. price | Notes |
|---|---|---|---|
| Seeed XIAO ESP32-S3 | target USB port | owned | runs the new firmware |
| USB-C cable | target ↔ XIAO | owned | data-capable, not charge-only |
| [Waveshare HDMI to USB adapter](https://www.waveshare.com/hdmi-to-usb-adapter.htm), **USB 3.0 version** | target HDMI → controller | $13–17 | UVC, driver-free on macOS, 1080p60, YUV422/MJPEG, about 50 ms latency |
| USB-C (male) to USB-A (female) adapter, **USB 3** | capture card → MacBook | $5–10 | e.g. Apple or Anker. A USB 2 adapter caps capture at 30 fps. Skip it if the card has a USB-C plug. |
| HDMI cable | target → capture card | owned | |
| USB-C to HDMI adapter, e.g. Anker 310 | target, only if it has no HDMI | $15–20 | target's port must support DisplayPort Alt Mode |
| HDMI splitter (optional) | before the capture card | $10–20 | only to keep a local monitor on the target |

Alternatives to the Waveshare card. Any HDMI capture card that macOS sees as a
webcam (UVC) works, because the MCP server only needs still frames.

- **UGREEN HDMI to USB capture card**
  ([Amazon.nl B0CFQ2BMPZ](https://www.amazon.nl/-/en/dp/B0CFQ2BMPZ)).
  Listings give 1080p60 capture from up to 4K30 input, and Mac support with
  QuickTime and OBS, so it shows up as a camera with no driver. Before buying,
  check on the listing:
  1. whether it includes a USB-C plug, cable or adapter (if not, use the
     USB 3 C-to-A adapter above);
  2. that it is the USB 3.0 / 1080p60 version and not the similar USB 2.0 /
     1080p30 model 40189. Either works for screenshots; 60 fps gives sharper
     text and less lag.
- **ATEN UC3020 (CAMLIVE+):** a native USB-C plug and 1080p60 UVC, but it
  costs more.

### Target display settings

- Set the target to **1920×1080** so the capture is 1:1.
- On a laptop target, **mirror** the display to HDMI, or the card captures an
  empty extended desktop.
- HDCP-protected content (streaming video) may capture as black. Desktops,
  login screens and BIOS capture fine.

## Decisions so far

- **Keyboard layout: US (en_US) only.** The target computers must use the US
  layout. Characters outside ASCII are rejected, not mistyped.
- **Keyboard and mouse in one device.** It is a composite USB HID: a keyboard
  plus an **absolute** mouse.
- **Screen feedback through a separate HDMI capture card** on the controller.
  It does not go through the ESP32, which can't handle video.
- **Controller: MacBook Pro (USB-C only)**, running Claude through MCP.

## Non-goals (first version)

- Controlling a target that is out of cable reach of the controller. Later,
  a small always-on computer next to the target could hold the capture card and
  serve frames over the network.
- Video streaming or audio. The AI works from still screenshots.
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
  jiggler). Both are standard HID devices that macOS, Windows and Linux support
  natively.
- **Why an absolute mouse:** the AI says "go to (x, y)" and the pointer lands
  there. It doesn't have to track position or deal with OS pointer
  acceleration, which distorts relative moves. The HID range is 0–32767 on each
  axis and the OS maps it onto the screen. Because the capture card sees the
  whole screen, screenshot coordinates and mouse coordinates line up directly.
  On multi-monitor setups the mapping is OS-specific, so this plan assumes a
  single display.
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
    held modifiers in a sequence step.
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

A Python [MCP](https://modelcontextprotocol.io) server over stdio, run on the
MacBook with `uv run` (dependencies declared inline, like
`hardware/enclosure.py`).

- **Config** comes from environment variables:
  - `AI_HID_URL`, default `http://ai-hid.local`.
  - `AI_HID_TOKEN`.
  - `AI_HID_CAPTURE`: the capture device's name or index. The default is the
    first UVC device whose name matches "USB Video". `--list-devices` prints
    the candidates.
  - `AI_HID_SHOT_WIDTH`: the width screenshots are scaled down to before they
    go to the model, default 1280. This keeps image tokens down while text
    stays readable.
- **Screen capture:**
  - OpenCV (`opencv-python`, AVFoundation backend on macOS) opens the capture
    card once at 1920×1080 and keeps reading in a background thread, so a
    screenshot is the latest frame, with no open/warm-up delay per call.
  - If the card disappears, the server reconnects and the tool returns a clear
    error.
  - **macOS camera permission:** the app that launches the MCP server
    (Terminal/iTerm for Claude Code, or Claude Desktop) needs it, granted once
    in System Settings → Privacy & Security → Camera.
  - A frame that is entirely black or a single color is flagged in the result
    ("no signal or HDCP?"), so the model doesn't act on an empty screen.
- **Coordinates:** mouse tools take **pixel coordinates in the most recent
  screenshot** as the model saw it, e.g. 1280×720. The server converts them to
  0–1 before calling the XIAO, so the model never has to do that math.
- **Tools:**
  - `screenshot()`: returns the scaled frame as an image, plus its width and
    height.
  - Keyboard: `type_text(text)` and `press_keys(keys)`.
  - Mouse: `move_mouse(x, y)`, `click(x, y, button, count)`,
    `drag(from_x, from_y, to_x, to_y)` and `scroll(dy, dx)`.
  - Both: `run_sequence(steps)`, `release_all()` and `status()`. `status()`
    reports the XIAO, the capture card and the signal.
  - Action tools take an optional `screenshot_after_ms`. When it is set, the
    tool waits that long, then returns a fresh screenshot, which saves a round
    trip in the look-act-look loop.
- Tool descriptions tell the model to take a screenshot before clicking, and to
  check the result after actions that change the screen.
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

- A README section for the AI setup: the parts list, wiring, flashing,
  provisioning, the macOS camera permission, connecting MCP, the US layout
  requirement, and security notes.
- Repo name: `usb-mouse-jiggler` no longer describes the whole repo. Renaming
  it is your call and is not part of this work.

## Security

This setup is a **remote keyboard, mouse and screen** for whatever computer it
is plugged into. Anyone with the token, and access to the LAN, can do anything
the logged-in user could. Screenshots of the target go to the AI model's
provider. The design limits that risk:

- A random per-device token from provisioning, which is never in the firmware
  image or the repo. Re-provisioning rotates it.
- HTTP is plaintext, so the token can be sniffed on the LAN. Use it on a
  trusted network only. HTTPS on the ESP32 is possible later, at a cost in
  memory and setup.
- The capture card stays local to the MacBook. No video leaves it except the
  screenshots the model asks for.
- The physical kill switch (BOOT), the per-request limits, and one request at
  a time.
- The setup AP runs only on first boot or when BOOT is held, never otherwise.
- The README will say it plainly: plug it only into machines you own or are
  allowed to control, and don't point it at screens showing secrets you don't
  want sent to the model.

## Testing

- **Firmware:** CI compiles it. The key-name parser and the coordinate mapping
  (0–1 to 0–32767, with clamping) are pure functions kept apart from the USB
  code, so they can be checked on the host too.
- **MCP server:** pytest against a fake device (a small local HTTP server) and
  a fake capture source (a still image). The tests cover:
  - text chunking and auth headers
  - converting screenshot pixels to 0–1 at several scale factors
  - error mapping (400/409/413/422) and rejection of unknown keys
  - the black-frame warning and reconnecting after the capture card goes away
- **With the real hardware (manual checklist):**
  - the capture card shows up on the MacBook, and `screenshot()` returns a
    readable 1080p frame
  - provisioning and `/status`
  - typing into a text editor, and combos (`cmd+space`, `ctrl+alt+t`), on
    macOS, Windows and Linux targets
  - **alignment:** clicking the screenshot's corners and center lands the
    pointer there on the target
  - left, right and double click, drag selecting text, scrolling
  - the kill switch during a long `/type` and during a drag
  - reconnect after a Wi-Fi drop, a wrong token returning 401, and unplugging
    the capture card
  - **end to end:** Claude opens a text editor on the target, writes a
    sentence, and confirms it from a screenshot

## Milestones (one PR each)

1. Firmware keyboard and mouse with hard-coded test Wi-Fi from a gitignored
   `secrets.h`: HID, all endpoints, token auth.
2. MCP server: keyboard and mouse tools against the XIAO, plus their tests.
3. Screen capture: `screenshot()`, pixel coordinates, `screenshot_after_ms`,
   and their tests. Works once the capture card arrives.
4. Provisioning over SoftAP, NVS storage, the BOOT kill switch and the LED.
5. Build/CI/release matrix for both firmwares, and the README section.

Milestones 1–2 need only the XIAO. Milestone 3 needs the capture card.

## Open questions

None blocking. To settle while testing:

- Whether the Waveshare card has a USB-A or a USB-C plug. This only decides
  whether the C-to-A adapter is needed.
- How each target OS maps the absolute mouse on a single display. The
  alignment test in the checklist answers this.
