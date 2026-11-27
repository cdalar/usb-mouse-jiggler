# Makefile — build and flash the USB jigglers for the Seeed XIAO ESP32-S3.
#
#   make setup                 install arduino-cli's ESP32 core (pinned)
#   make                       compile the mouse, then write dist/<name>-full.bin
#   make DEVICE=keyboard       same for the keyboard jiggler
#   make flash PORT=/dev/ttyACM0 [DEVICE=keyboard]
#   make clean
#
# FQBN and versions come from build.env, the same file CI reads.
# Requires: arduino-cli. `flash` also needs esptool (pip install esptool).

include build.env

DEVICE  ?= mouse
ifeq ($(filter $(DEVICE),mouse keyboard),)
$(error DEVICE must be mouse or keyboard, not '$(DEVICE)')
endif
SKETCH  := usb_$(DEVICE)_jiggler
OUTDIR  := build-out/$(DEVICE)
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo dev)
IMAGE   := dist/usb-$(DEVICE)-xiao-$(CHIP)-$(VERSION)-full.bin
PORT    ?=
BAUD    ?= 921600

.PHONY: all setup build image flash clean help
all: image

setup:
	arduino-cli config init --overwrite
	arduino-cli config add board_manager.additional_urls \
	  https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
	arduino-cli core update-index
	arduino-cli core install "esp32:esp32@$(CORE_VERSION)"

build:
	arduino-cli compile --fqbn "$(FQBN)" --warnings default --output-dir $(OUTDIR) $(SKETCH)

image: build
	SKETCH=$(SKETCH) bash scripts/make-full-image.sh $(OUTDIR) $(IMAGE)

# Writes the trimmed image at 0x0. Never flash build-out/*/*.merged.bin: it is
# padded to the whole chip. The firmware has no serial port, so put the board in
# download mode first: hold BOOT while plugging in the USB cable.
flash: image
	@test -n "$(PORT)" || { echo "PORT is required, e.g. make flash PORT=/dev/ttyACM0"; exit 1; }
	esptool --chip $(CHIP) --port "$(PORT)" --baud $(BAUD) write-flash 0x0 $(IMAGE)

clean:
	rm -rf build-out dist

help:
	@sed -n '3,8p' $(firstword $(MAKEFILE_LIST))
