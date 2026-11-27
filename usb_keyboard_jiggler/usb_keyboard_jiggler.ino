// usb_keyboard_jiggler.ino
//
// Enumerates as a plain USB keyboard and taps a harmless key (Left Shift by
// default) every 30-40 s, so the computer never goes idle. A lone Shift tap
// types nothing and triggers no shortcut. Useful where a mouse nudge is not
// enough, or where the pointer must not move at all.
//
// Needs a chip with native USB-OTG (ESP32-S2/S3); built for the Seeed XIAO
// ESP32-S3. The ESP32-C3/C6 USB port is serial/JTAG only and cannot do this.
//
// Build with USB Mode = USB-OTG (TinyUSB). See README.md.

#include <Arduino.h>

#ifndef ARDUINO_USB_MODE
#error This ESP32 SoC has no native USB interface
#elif ARDUINO_USB_MODE == 1
#error USB Mode must be USB-OTG (TinyUSB), not Hardware CDC and JTAG
#endif

#include "USB.h"
#include "USBHIDKeyboard.h"

// ---- Tuning ----------------------------------------------------------------
static const uint32_t TAP_EVERY_MS  = 30000;          // base gap between taps
static const uint32_t TAP_RANDOM_MS = 10000;          // + random 0..this, so it isn't metronomic
static const uint8_t  TAP_KEY       = KEY_LEFT_SHIFT; // key to tap (see USBHIDKeyboard.h)
static const uint32_t HOLD_MS       = 40;             // how long the key is held down
// ----------------------------------------------------------------------------

USBHIDKeyboard Keyboard;

void setup() {
  USB.productName("USB Keyboard");
  Keyboard.begin();
  USB.begin();
}

void loop() {
  delay(TAP_EVERY_MS + random(TAP_RANDOM_MS + 1));
  Keyboard.press(TAP_KEY);
  delay(HOLD_MS);
  Keyboard.releaseAll();
}
