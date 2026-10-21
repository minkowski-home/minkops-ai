"""Bill documents as the pages a session reads: each page's text layer and a bounded image.

A PDF page carries its text layer, which is empty for a scan, and an image the
model reads either way: printed tables, stamps and handwriting live only there.
Images are rendered at a fixed resolution and capped in size, so a large scan
costs no more than a page needs. PNG, JPEG and WebP files are one page each.
"""

import io

import pypdfium2 as pdfium
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PAGES = 12
DPI = 150
# The longest side a page image keeps; finer detail does not help the model read.
MAX_SIDE = 1800
TEXT_LIMIT = 20_000
IMAGES = (".png", ".jpg", ".jpeg", ".webp")


def _jpeg(image):
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82, optimize=True)
    return buffer.getvalue(), image.size


def pages(content, suffix):
    """[{page, text, image (JPEG bytes), width, height}] of a bill file; ValueError when it cannot be read."""
    suffix = suffix.lower()
    if suffix in IMAGES:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                data, (width, height) = _jpeg(image)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("The image could not be read.") from error
        return [{"page": 1, "text": "", "image": data, "width": width, "height": height}]
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
            data, (width, height) = _jpeg(page.render(scale=DPI / 72).to_pil())
            result.append({"page": number + 1, "text": text, "image": data, "width": width, "height": height})
        return result
    finally:
        document.close()
