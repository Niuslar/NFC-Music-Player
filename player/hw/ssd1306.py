"""SSD1306 I2C OLED, 128x32 (the common 0.91-inch modules with pins GND VCC SCL SDA).

It shares the Pi's I2C bus (GPIO 2 and 3) with the DAC, which sits at a different
address. bus is anything with write(bytes) aimed at the screen's address, e.g. I2cDevice.
"""

import fcntl
import os

WIDTH, HEIGHT = 128, 32
ADDRESSES = (0x3C, 0x3D)  # nearly every 128x32 module is 0x3C
I2C_SLAVE = 0x0703
_COMMAND, _DATA = 0x00, 0x40
DISPLAY_OFF, DISPLAY_ON = 0xAE, 0xAF


class I2cDevice:
    """One device on a Linux I2C bus, written through /dev/i2c-N."""

    def __init__(self, address: int, bus: int = 1):
        self.address = address
        try:
            self._fd = os.open(f"/dev/i2c-{bus}", os.O_RDWR)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"/dev/i2c-{bus} does not exist: I2C is not turned on. "
                "Run 'sudo system/setup.sh' again (it turns I2C on), then reboot."
            ) from None
        fcntl.ioctl(self._fd, I2C_SLAVE, address)

    def write(self, data: bytes) -> None:
        os.write(self._fd, data)

    def close(self) -> None:
        os.close(self._fd)


def open_bus(bus: int = 1) -> I2cDevice:
    """Finds the screen at its usual addresses; raises OSError if there is none."""
    last = None
    for address in ADDRESSES:
        dev = I2cDevice(address, bus)
        try:
            dev.write(bytes([_COMMAND, DISPLAY_OFF]))  # a missing device does not acknowledge
            return dev
        except OSError as e:
            dev.close()
            last = e
    raise OSError(f"no SSD1306 screen answered at {' or '.join(hex(a) for a in ADDRESSES)} on I2C bus {bus} ({last})")


def to_pages(image) -> bytes:
    """Pillow image -> SSD1306 page bytes: each byte is 8 pixels down, lowest bit on top."""
    import numpy as np

    lit = np.asarray(image.convert("L").resize((WIDTH, HEIGHT)), dtype=np.uint8) >= 96
    pages = lit.reshape(HEIGHT // 8, 8, WIDTH)
    weights = (1 << np.arange(8, dtype=np.uint16)).reshape(1, 8, 1)
    return (pages * weights).sum(axis=1).astype(np.uint8).tobytes()


def changed_spans(old: bytes | None, new: bytes) -> list[tuple[int, int, int]]:
    """(page, first column, last column) for each page that differs; every page when old is None."""
    spans = []
    for page in range(HEIGHT // 8):
        a = slice(page * WIDTH, (page + 1) * WIDTH)
        if old is None:
            spans.append((page, 0, WIDTH - 1))
            continue
        cols = [x for x, (o, n) in enumerate(zip(old[a], new[a])) if o != n]
        if cols:
            spans.append((page, cols[0], cols[-1]))
    return spans


class SSD1306:
    def __init__(self, bus, rotate180: bool = False, contrast: int = 0x8F):
        self.bus = bus
        self._last = None
        self.failures = 0
        seg, com = (0xA0, 0xC0) if rotate180 else (0xA1, 0xC8)
        self._command(
            DISPLAY_OFF,
            0xD5, 0x80,  # clock
            0xA8, HEIGHT - 1,  # multiplex
            0xD3, 0x00,  # no offset
            0x40,  # start line 0
            0x8D, 0x14,  # charge pump on (the module runs from 3.3 V)
            0x20, 0x00,  # horizontal addressing
            seg, com,  # orientation
            0xDA, 0x02,  # COM pins for 32 rows
            0x81, contrast,
            0xD9, 0xF1,  # pre-charge
            0xDB, 0x40,  # VCOM detect
            0xA4,  # show RAM
            0xA6,  # not inverted
        )
        self._lit = False

    def _command(self, *codes: int) -> None:
        self.bus.write(bytes([_COMMAND, *codes]))

    def show(self, image) -> bool:
        """Sends the picture; False when it did not reach the screen (it is sent again next time)."""
        data = to_pages(image)
        if data == self._last:
            return True
        try:
            for page, first, last in changed_spans(self._last, data):
                # Only the columns that changed on each 8-row strip: a new second is a few
                # dozen bytes instead of the whole 512-byte screen, so it appears at once.
                self._command(0x21, first, last, 0x22, page, page)
                start = page * WIDTH
                self.bus.write(bytes([_DATA]) + data[start + first : start + last + 1])
            if not self._lit:  # light up only once there is a picture
                self._command(DISPLAY_ON)
                self._lit = True
        except OSError:
            # A held power key pulls the shared clock line low; send the frame again next time.
            self.failures += 1
            self._last = None
            return False
        self._last = data
        return True

    def off(self) -> None:
        self._command(DISPLAY_OFF)
        self._lit = False

    def sleep(self) -> bool:
        """Standby: the screen off. False when it did not get through (the power key shares its clock line), to try again."""
        try:
            self.off()
        except OSError:
            self.failures += 1
            return False
        return True

    def wake(self) -> None:
        self._last = None  # the next picture is sent whole, and switches the screen on
