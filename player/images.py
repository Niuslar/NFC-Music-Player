"""Opening cover images. They come from uploads and from tags, which anyone on the network can set.

Only JPEG and PNG are read (the only cover files uploads accept, and what tags carry in practice),
so Pillow's parsers for other formats never see this data. A small file can claim a huge picture:
one that would need hundreds of MB to decode would run the Pi Zero 2 W out of memory every time
the album is shown, so its size is checked from the header before anything is decoded.
"""

import io

from PIL import Image

FORMATS = ("JPEG", "PNG")
MAX_PIXELS = 25_000_000  # 5000 x 5000: far beyond any real cover, and about 75 MB decoded
DRAFT_SIZE = (400, 400)  # the largest a cover is shown: the web page's thumbnails


def open_cover(data: bytes) -> Image.Image:
    """The cover as an RGB image. Raises an exception for anything that is not a sensible cover."""
    img = Image.open(io.BytesIO(data), formats=FORMATS)
    width, height = img.size
    if width * height > MAX_PIXELS:
        raise ValueError(f"cover is too large ({width} x {height})")
    if img.format == "JPEG":
        img.draft("RGB", DRAFT_SIZE)  # decode a big JPEG at a fraction of its size, still at least DRAFT_SIZE
    return img.convert("RGB")
