"""ST7789 SPI display (Waveshare 2inch LCD Module, 240x320 panel used in landscape).

The spi object is a spidev.SpiDev (or a fake with writebytes2); dc, rst and bl
are objects with on()/off(), e.g. gpiozero.DigitalOutputDevice.
"""

import time

WIDTH, HEIGHT = 320, 240
SWRESET, SLPOUT, NORON, INVON, DISPON = 0x01, 0x11, 0x13, 0x21, 0x29
CASET, RASET, RAMWR, MADCTL, COLMOD = 0x2A, 0x2B, 0x2C, 0x36, 0x3A


def to_rgb565(image) -> bytes:
    """Pillow RGB image -> big-endian RGB565 bytes."""
    import numpy as np

    a = np.asarray(image.convert("RGB"), dtype=np.uint16)
    packed = ((a[..., 0] & 0xF8) << 8) | ((a[..., 1] & 0xFC) << 3) | (a[..., 2] >> 3)
    return packed.astype(">u2").tobytes()


class ST7789:
    def __init__(self, spi, dc, rst, bl, rotate180: bool = False, sleep=time.sleep):
        self.spi, self.dc, self.rst, self.bl = spi, dc, rst, bl
        self._last = None
        self._lit = False
        rst.off()
        sleep(0.02)
        rst.on()
        sleep(0.15)
        self._command(SWRESET)
        sleep(0.15)
        self._command(SLPOUT)
        sleep(0.12)
        self._command(COLMOD, 0x55)  # 16 bits per pixel
        self._command(MADCTL, 0xA0 if rotate180 else 0x60)  # landscape
        self._command(INVON)  # IPS panels need inversion on for true colours
        self._command(NORON)
        self._command(CASET, 0, 0, (WIDTH - 1) >> 8, (WIDTH - 1) & 0xFF)
        self._command(RASET, 0, 0, (HEIGHT - 1) >> 8, (HEIGHT - 1) & 0xFF)
        self._command(DISPON)

    def _command(self, cmd: int, *params: int) -> None:
        self.dc.off()
        self.spi.writebytes2(bytes([cmd]))
        if params:
            self.dc.on()
            self.spi.writebytes2(bytes(params))

    def show(self, image) -> None:
        raw = image.tobytes()
        if raw == self._last:
            return
        self._last = raw
        self._command(RAMWR)
        self.dc.on()
        self.spi.writebytes2(to_rgb565(image))
        if not self._lit:  # light up only once there is a picture
            self.bl.on()
            self._lit = True
