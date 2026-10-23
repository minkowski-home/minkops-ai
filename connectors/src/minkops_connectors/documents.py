"""Bill documents as the pages a session reads: each page's text layer, a bounded image and its QR codes.

A PDF page carries its text layer, which is empty for a scan, and an image the
model reads either way: printed tables, stamps and handwriting live only there.
Images are capped in size, so a large scan costs no more than a page needs.
QR codes, such as a signed e-invoice's, are decoded before that reduction,
from a page rendered finely enough to read them. PNG, JPEG and WebP files are
one page each.
"""

import io

import pypdfium2 as pdfium
import zxingcpp
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 12
# A signed e-invoice's QR code is dense: decoding it needs about three pixels a module.
DPI = 300
# The longest side a page image keeps; finer detail does not help the model read.
MAX_SIDE = 1800
TEXT_LIMIT = 20_000
IMAGES = (".png", ".jpg", ".jpeg", ".webp")


def _codes(image):
    """The text of each QR code printed on a page."""
    return [code.text for code in zxingcpp.read_barcodes(image.convert("L"), formats=zxingcpp.BarcodeFormat.QRCode)
            if code.valid]


def _jpeg(image):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue(), image.size


def pages(content, suffix):
    """[{page, text, image (JPEG bytes), width, height, codes}] of a bill file; ValueError when it cannot be read."""
    suffix = suffix.lower()
    if suffix in IMAGES:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                codes = _codes(ImageOps.exif_transpose(image))
                data, (width, height) = _jpeg(image)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("The image could not be read.") from error
        return [{"page": 1, "text": "", "image": data, "width": width, "height": height, "codes": codes}]
    if suffix != ".pdf":
        raise ValueError("Bills must be PDF, PNG, JPEG or WebP files.")
    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as error:
        raise ValueError("The PDF could not be opened; it may be damaged or password-protected.") from error
    try:
        if not len(document):
            raise ValueError("The PDF has no pages.")
        if len(document) > MAX_PAGES:
            raise ValueError(f"A bill file can have at most {MAX_PAGES} pages; split larger files.")
        result = []
        for number in range(len(document)):
            page = document[number]
            # Line breaks keep a printed table's rows apart; runs of spaces carry nothing.
            lines = (" ".join(line.split()) for line in page.get_textpage().get_text_range().splitlines())
            text = "\n".join(line for line in lines if line)[:TEXT_LIMIT]
            image = page.render(scale=DPI / 72).to_pil()
            codes = _codes(image)
            data, (width, height) = _jpeg(image)
            result.append({"page": number + 1, "text": text, "image": data, "width": width, "height": height,
                           "codes": codes})
        return result
    finally:
        document.close()
