# USB Mouse Jiggler

Tiny firmware that turns a **Seeed XIAO ESP32-S3** into a plain USB mouse named
"USB Mouse". Every 30-40 seconds it nudges the pointer 2 px and straight back,
so the computer never goes idle (screen lock, "away" status, sleep timers).
Plug it in and it works: no pairing, no driver, no serial port.

## Hardware

Any board with native USB-OTG works, so ESP32-S2 and ESP32-S3. The ESP32-C3 and
C6 will **not** work: their USB port is a fixed serial/JTAG peripheral and
cannot enumerate as a HID device. The build targets the
[Seeed XIAO ESP32-S3](https://www.seeedstudio.com/XIAO-ESP32S3-p-5627.html);
other S3 boards need a different `FQBN` in `build.env` (and a matching flash
size in the image header).

Neither the flash size nor PSRAM matters here. The firmware is ~330 KB and uses
about 54 KB of RAM.

## Get the firmware

Download `usb-mouse-xiao-esp32s3-<version>-full.bin` from the
[latest release](../../releases/latest), or build it yourself (below).

## Flash

The image is complete (bootloader, partition table, app) and is written at
**`0x0`**.

```sh
pip install esptool
esptool --chip esp32s3 --port /dev/ttyACM0 write-flash 0x0 usb-mouse-xiao-esp32s3-<version>-full.bin
```

Or use [ESP Launchpad](https://espressif.github.io/esp-launchpad/) in Chrome or
Edge: DIY tab, connect, pick the file, address `0x0`, Program.

**The firmware has no serial port, so put the board in download mode first:**
hold **BOOT** while plugging in the USB cable (or hold BOOT and tap RESET).
Do this for the first flash and every re-flash.

Verify a download against `SHA256SUMS` from the release:
`sha256sum -c SHA256SUMS --ignore-missing`.

## Build from source

Needs [arduino-cli](https://arduino.github.io/arduino-cli/) (and `make`).

```sh
make setup      # installs the pinned ESP32 core
make            # compiles, writes dist/usb-mouse-xiao-esp32s3-<version>-full.bin
make flash PORT=/dev/ttyACM0
```

The toolchain and board settings live in one file, `build.env`, which the
Makefile and CI both read. Two settings are load-bearing:

- `USBMode=default` is **USB-OTG (TinyUSB)**. Hardware CDC and JTAG cannot be a mouse.
- `CDCOnBoot=cdc` means **Disabled** (the labels are swapped in the XIAO board
  definition). It keeps the board a mouse only, with no serial interface.

Never flash `build-out/*.merged.bin` directly. The core pads it to the whole
flash chip; `scripts/make-full-image.sh` cuts it right after the app and
refuses if anything non-empty would be lost.

## Tuning

Constants at the top of `usb_mouse_jiggler/usb_mouse_jiggler.ino`:

| Constant | Default | Meaning |
|---|---|---|
| `JIGGLE_EVERY_MS` | 30000 | base gap between nudges |
| `JIGGLE_RANDOM_MS` | 10000 | extra random 0..N ms, so it isn't metronomic |
| `JIGGLE_PIXELS` | 2 | size of the nudge (it moves back afterwards) |
| `SETTLE_MS` | 40 | pause between the out and back moves |

## CI and releases

- `ci.yml` compiles on every PR and push to `main` and uploads the flashable
  image as an artifact (14 days), so a PR can be tested on a board.
- `release.yml` runs when a `v*` tag is pushed:
  ```sh
  git tag v1.0.0 && git push origin v1.0.0
  ```
  It publishes the full image, the app-only image and `SHA256SUMS`. A tag with a
  suffix (`v1.0.0-rc.1`) becomes a prerelease.
- Dependabot keeps the GitHub Actions current. The core and arduino-cli pins in
  `build.env` are bumped by hand.

## License

MIT, see [LICENSE](LICENSE).
