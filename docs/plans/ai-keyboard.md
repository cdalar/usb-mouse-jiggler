# Plan: AI-controlled USB keyboard

Status: **proposal, not implemented.** Review this before any code is written.

## Goal

Use the same Seeed XIAO ESP32-S3 as a **USB keyboard that an AI model types
on**. The board plugs into the *target* computer as a plain HID keyboard. The
AI runs somewhere else and sends it text and key combos over Wi-Fi. The target
needs no software, driver or pairing, so this also works on locked-down
machines, login screens, BIOS/UEFI setup and a fresh OS install.

```
 ┌──────────────┐  MCP (stdio)  ┌────────────┐  HTTP + token   ┌──────────────┐  USB HID  ┌────────────┐
 │ AI model     │ ────────────▶ │ MCP server │ ──── Wi-Fi ───▶ │ XIAO ESP32-S3│ ────────▶ │ target PC  │
 │ (Claude etc.)│               │ (Python)   │    (LAN)        │ firmware     │  keyboard │            │
 └──────────────┘               └────────────┘                 └──────────────┘           └────────────┘
```

## Non-goals (first version)

- **Seeing the screen.** The AI types blind. Feedback (a screenshot or capture
  card, or a person describing the screen) is a separate problem. See
  "Open questions".
- Mouse control. It can be added later as a composite HID device.
- TLS on the device. The device trusts the local network, and the token is the
  only guard (see Security).
- Reaching the device from outside the LAN.

## Components

### 1. Firmware: `usb_ai_keyboard/usb_ai_keyboard.ino`

A new sketch next to the mouse jiggler. It uses the same board, FQBN and
`build.env`.

- **USB:** `USBHIDKeyboard`, product name "USB Keyboard", with no CDC serial
  (same USB settings as the mouse).
- **Wi-Fi:** station mode, with mDNS name `ai-keyboard.local`. It reconnects on
  its own if the link drops.
- **HTTP API** (`WebServer`, port 80, JSON bodies). Every endpoint except the
  setup page needs `Authorization: Bearer <token>`, compared in constant time.

  | Method | Path | Body | Effect |
  |---|---|---|---|
  | GET  | `/status`  | none | `{usb_mounted, busy, version, layout}` |
  | POST | `/type`    | `{"text": "...", "delay_ms": 8}` | types text, returns when done |
  | POST | `/keys`    | `{"keys": ["ctrl","alt","t"]}` | presses the combo, then releases it |
  | POST | `/sequence`| `{"steps": [{"keys":[...]}, {"text":"..."}, {"sleep_ms":500}]}` | runs the steps in order |
  | POST | `/release` | none | releases all keys (panic) |

  - Key names: modifiers (`ctrl`, `shift`, `alt`, `gui`/`cmd`/`win`, plus
    left/right variants), `enter`, `tab`, `esc`, `backspace`, `delete`, arrows,
    `home/end/pageup/pagedown`, `f1`–`f24`, and single printable characters.
    Unknown names are rejected with 400, and nothing is typed.
  - Limits: 2000 chars per `/type`, 6 non-modifier keys per combo, and 50 steps
    per sequence. Text that is too long gets a 413. The MCP server splits long
    text into chunks.
  - One request types at a time. A second request during typing gets 409 `busy`.
- **Provisioning (no secrets in the image):** on first boot, or when BOOT is
  held for 3 s after power-up, the board starts a SoftAP `AI-Keyboard-XXXX`
  with a captive setup page. There you enter the Wi-Fi SSID and password and
  pick the keyboard layout. The board generates a random 32-byte token and
  shows it **once** on that page. Everything is stored in NVS (`Preferences`).
  This keeps the release image generic and the CI build free of secrets.
- **Kill switch:** a short press of BOOT during operation aborts any typing,
  releases all keys, and refuses input until the next press. The onboard LED
  shows the state: off when idle, blinking while typing, solid when disabled.

### 2. MCP server: `mcp/ai_keyboard_mcp.py`

A Python [MCP](https://modelcontextprotocol.io) server over stdio, run with
`uv run` (dependencies declared inline, like `hardware/enclosure.py`).

- Config comes from environment variables: `AI_KEYBOARD_URL` (default
  `http://ai-keyboard.local`) and `AI_KEYBOARD_TOKEN`.
- Tools:
  - `type_text(text)`: splits the text into chunks and calls `/type`.
  - `press_keys(keys: list[str])`: one combo, e.g. `["cmd","space"]`.
  - `run_sequence(steps)`: several steps in one call, e.g. open a launcher,
    wait, type, press Enter.
  - `release_all()` and `status()`.
- Tool descriptions warn the model that it cannot see the screen. They tell it
  to add waits after actions that open windows.
- Registering it with Claude Code:
  `claude mcp add ai-keyboard -e AI_KEYBOARD_TOKEN=... -- uv run mcp/ai_keyboard_mcp.py`

### 3. Build, CI, release

- Makefile: `DEVICE ?= mouse`, with `DEVICE=ai-keyboard` selecting the new
  sketch. Output goes to `build-out/<device>/` and
  `dist/usb-<device>-xiao-esp32s3-<version>-full.bin`. (This is the plumbing
  from the closed PR #4, reused.)
- The composite action takes a `device` input. CI builds both sketches in a
  matrix. A release publishes both images and one `SHA256SUMS`.
- CI also runs the MCP server's tests (below) with `uv`.
- Partition scheme `default_8MB` still fits. Wi-Fi brings the image to about
  1 MB.

### 4. Docs

- A README section for the AI keyboard: flash, provision, connect MCP, and
  security notes.
- Repo name: `usb-mouse-jiggler` no longer describes the whole repo. Renaming
  it is your call and is not part of this work.

## Security

This device is a **remote keystroke injector** into whatever computer it is
plugged into. Anyone with the token, and access to the LAN, can type anything
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

- **Firmware:** CI compiles it. A pure `keymap` parser (key name to HID code)
  is kept separate so it can also be checked on the host.
- **MCP server:** pytest against a fake device (a small local HTTP server). The
  tests cover chunking, auth headers, error mapping (400/409/413), and
  rejection of unknown keys.
- **On the board (manual checklist):** provisioning, `/status`, typing into a
  text editor on macOS, Windows and Linux, combos (`cmd+space`, `ctrl+alt+t`),
  the kill switch, reconnect after a Wi-Fi drop, and a wrong token returning 401.

## Milestones (one PR each)

1. Firmware with hard-coded test Wi-Fi from a gitignored `secrets.h`: HID
   typing, `/type`, `/keys`, `/release`, `/status`, token auth.
2. Provisioning over SoftAP, NVS storage, the BOOT kill switch and the LED.
3. MCP server, its tests, and the README section.
4. Build/CI/release matrix for both firmwares.

## Open questions for you

1. **Keyboard layout of the target computers.** HID sends key *positions*, not
   characters. The core has layouts for en_US, de_DE, es_ES, fr_FR, fr_CH,
   it_IT, pt_PT, sv_SE and da_DK. It has **no Turkish layout**, and all of
   them are ASCII-only. If the targets use Turkish Q, I would add a `tr_TR`
   table. Characters like ğ, ş and ı would then need either that table or a
   per-OS Unicode-input fallback.
2. **Screen feedback.** Is blind typing enough for your use (scripts, filling
   known forms), or should a later milestone add a feedback loop? Options are
   an HDMI capture card on the AI's machine, or screenshots from the target.
3. **Mouse too?** A composite keyboard and mouse would allow full "computer
   use"-style control. It is an extra milestone.
4. **Where does the AI run?** Claude Code or Claude Desktop through MCP is
   assumed. If you want a standalone agent loop instead (Claude API with tool
   use), that replaces milestone 3.
