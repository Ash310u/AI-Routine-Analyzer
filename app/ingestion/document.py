import base64

import pymupdf

from app.config import Settings


class DocumentError(ValueError):
    pass


def image_data_urls(data: bytes, settings: Settings) -> list[str]:
    """Prepare every PDF page or one image for a single model request."""
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise DocumentError(f"File exceeds {settings.max_upload_mb} MB limit")
    if data.startswith(b"%PDF-"):
        try:
            document = pymupdf.open(stream=data, filetype="pdf")
            if document.is_encrypted:
                raise DocumentError("Encrypted PDFs are not supported")
            if not 1 <= len(document) <= settings.max_pdf_pages:
                raise DocumentError(f"PDF must have 1–{settings.max_pdf_pages} pages")
            result = []
            for page in document:
                pixmap = page.get_pixmap(dpi=settings.pdf_render_dpi, alpha=False)
                result.append(_url(pixmap.tobytes("png"), "image/png"))
            return result
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as exc:
            raise DocumentError("Invalid PDF") from exc
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return [_url(data, "image/png")]
    if data.startswith(b"\xff\xd8\xff"):
        return [_url(data, "image/jpeg")]
    if data.startswith((b"GIF87a", b"GIF89a")):
        return [_url(data, "image/gif")]
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return [_url(data, "image/webp")]
    raise DocumentError("Upload a PDF, PNG, JPEG, GIF, or WebP file")


def _url(data: bytes, mime: str) -> str:
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
