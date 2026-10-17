# /// script
# requires-python = ">=3.10"
# dependencies = ["manifold3d==3.2.1", "numpy"]
# ///
"""Two-part enclosure (box + press-fit lid) for the Seeed XIAO ESP32-S3.

    uv run hardware/enclosure.py      # writes hardware/xiao-esp32s3-enclosure.stl

Both parts are laid out flat, side by side, ready to print without supports.
All sizes are in mm. Board dimensions follow Seeed's XIAO ESP32-S3 drawing;
measure your board and adjust the BOARD_* / BUTTON_* values if they differ.

Frame: X across the board, Y along it (USB-C at +Y), Z up. The cavity is
centred on the origin in X and Y; the floor's top surface is at Z = FLOOR.
"""

import struct
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, JoinType, Manifold

# Board (XIAO ESP32-S3, not the Sense: its camera board does not fit).
BOARD_W = 17.8          # X
BOARD_L = 21.0          # Y
PCB_T = 1.2             # PCB thickness; the board lies flat on the floor
USB_W, USB_H = 8.94, 3.26   # USB-C receptacle, top-mounted, centred on the +Y edge
# BOOT (B) and RESET (R) sit either side of the USB-C connector.
BUTTON_X = 6.5          # offset of each button from the board centre line
BUTTON_Y = 2.5          # distance of the button centres from the USB edge

FIT = 0.2               # clearance around the board on each side
WALL = 1.2
FLOOR = 1.0
HEADROOM = 0.6          # gap between the top of the USB-C shell and the lid
LID_T = 1.2
LEDGE = 0.5             # how far the lid recess eats into the wall
LID_FIT = 0.15          # clearance around the lid on each side
CORNER_R = 1.5          # outer corner radius

CAV_W = BOARD_W + 2 * FIT
CAV_L = BOARD_L + 2 * FIT
CAV_H = PCB_T + USB_H + HEADROOM
OUT_W = CAV_W + 2 * WALL
OUT_L = CAV_L + 2 * WALL
BOX_H = FLOOR + CAV_H + LID_T


def rrect(w, l, r):
    """Centred rounded rectangle."""
    r = min(r, w / 2 - 0.01, l / 2 - 0.01)
    if r <= 0:
        return CrossSection.square([w, l], center=True)
    core = CrossSection.square([w - 2 * r, l - 2 * r], center=True)
    return core.offset(r, JoinType.Round, circular_segments=48)


def prism(w, l, h, r=0.0, z=0.0):
    return Manifold.extrude(rrect(w, l, r), h).translate([0, 0, z])


def box():
    shell = prism(OUT_W, OUT_L, BOX_H, CORNER_R)
    cavity = prism(CAV_W, CAV_L, CAV_H + LID_T + 1, z=FLOOR)
    lid_seat = prism(CAV_W + 2 * LEDGE, CAV_L + 2 * LEDGE, LID_T + 1, 0.3,
                     z=FLOOR + CAV_H)

    # USB-C opening: the receptacle outline plus 0.35 mm all round, cut through
    # the +Y wall at the connector's height.
    usb_z = FLOOR + PCB_T + USB_H / 2
    usb_cut = (Manifold.extrude(rrect(USB_W + 0.7, USB_H + 0.7, 1.2), WALL + 2)
               .rotate([-90, 0, 0])
               .translate([0, CAV_L / 2 - 1, usb_z]))
    return shell - cavity - lid_seat - usb_cut


def lid():
    plate = prism(CAV_W + 2 * LEDGE - 2 * LID_FIT,
                  CAV_L + 2 * LEDGE - 2 * LID_FIT, LID_T, 0.3)
    cuts = []
    # Pin holes over BOOT and RESET; press them with a paperclip.
    for sx in (-1, 1):
        cuts.append(Manifold.cylinder(LID_T * 3, 1.3, circular_segments=32)
                    .translate([sx * BUTTON_X, CAV_L / 2 - FIT - BUTTON_Y, -LID_T]))
    # Vent slots over the chip.
    for i in range(-2, 3):
        cuts.append(prism(1.2, 9.0, LID_T * 3, 0.6, z=-LID_T).translate([i * 2.6, -2.5, 0]))
    return plate - Manifold.compose(cuts)


def write_stl(path, solid):
    mesh = solid.to_mesh()
    verts = np.asarray(mesh.vert_properties)[:, :3]
    tris = np.asarray(mesh.tri_verts)
    with open(path, "wb") as f:
        f.write(b"XIAO ESP32-S3 enclosure".ljust(80, b"\0"))
        f.write(struct.pack("<I", len(tris)))
        for a, b, c in verts[tris]:
            n = np.cross(b - a, c - a)
            n = n / (np.linalg.norm(n) or 1)
            f.write(struct.pack("<12fH", *n, *a, *b, *c, 0))


def main():
    parts = box() + lid().translate([OUT_W + 5, 0, 0])
    out = Path(__file__).with_name("xiao-esp32s3-enclosure.stl")
    write_stl(out, parts)
    print(f"box {OUT_W:.1f} x {OUT_L:.1f} x {BOX_H:.1f} mm, "
          f"cavity {CAV_W:.1f} x {CAV_L:.1f} x {CAV_H:.1f} mm -> {out}")


if __name__ == "__main__":
    main()
