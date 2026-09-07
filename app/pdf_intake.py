"""Bounded, local-only extraction of request attachments in an isolated process."""
from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys

MAX_REQUEST_BYTES = 10 * 1024 * 1024
MAX_REQUEST_PAGES = 100
MAX_REQUEST_TEXT = 5000


class PDFIntakeError(ValueError):
    pass


def extract_pdf_text(data: bytes) -> dict:
    import fitz

    if not data or len(data) > MAX_REQUEST_BYTES:
        raise PDFIntakeError("PDF boş olmamalı ve 10 MB sınırını aşmamalı.")
    if b"%PDF-" not in data[:1024]:
        raise PDFIntakeError("Dosya geçerli bir PDF değil.")
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.needs_pass:
                raise PDFIntakeError("Şifreli PDF okunamıyor. Şifresiz bir kopya yükleyin.")
            if not 0 < document.page_count <= MAX_REQUEST_PAGES:
                raise PDFIntakeError("Talep eki en fazla 100 sayfa olabilir. İlgili sayfaları ayrı bir PDF olarak yükleyin.")
            sections, empty_pages, text_length = [], 0, 0
            for page in document:
                content = page.get_text("text", sort=True).strip()
                if not content:
                    empty_pages += 1
                    continue
                # Retain at most one character beyond the UI limit to detect truncation.
                if text_length <= MAX_REQUEST_TEXT:
                    fragment = content[: MAX_REQUEST_TEXT + 1 - text_length]
                    sections.append(fragment)
                    text_length += len(fragment) + 2
            text = "\n\n".join(sections).strip()
            if not text:
                raise PDFIntakeError("PDF'de okunabilir metin bulunamadı. Taranmış belgeyi metin tanıma (OCR) işleminden geçirerek yükleyin.")
            warnings = []
            if empty_pages:
                warnings.append(f"{empty_pages} sayfadan metin çıkarılamadı; bu sayfalar boş veya taranmış olabilir. İçeriği kontrol edin.")
            truncated = len(text) > MAX_REQUEST_TEXT
            if truncated:
                warnings.append("Metin 5.000 karakterle sınırlandı. Talebiniz için gerekli bölümleri kontrol ederek düzenleyin.")
            return {"text": text[:MAX_REQUEST_TEXT], "page_count": document.page_count,
                    "truncated": truncated, "warnings": warnings}
    except PDFIntakeError:
        raise
    except Exception as error:
        raise PDFIntakeError("PDF okunamadı. Dosya bozuk veya desteklenmeyen bir yapıda olabilir.") from error


def extract_request_pdf(data: bytes, filename: str) -> dict:
    """No document is persisted or sent to an AI provider at this stage."""
    if not filename.lower().endswith(".pdf"):
        raise PDFIntakeError("Yalnızca PDF yüklenebilir.")
    if len(data) > MAX_REQUEST_BYTES:
        raise PDFIntakeError("Talep eki en fazla 10 MB olabilir.")
    try:
        process = subprocess.run([sys.executable, "-m", "app.pdf_intake"], input=data,
                                 capture_output=True, timeout=20,
                                 cwd=str(Path(__file__).resolve().parents[1]))
        result = json.loads(process.stdout)
    except subprocess.TimeoutExpired as error:
        raise PDFIntakeError("PDF okuma süresi aşıldı. İlgili sayfaları içeren daha küçük bir PDF yükleyin.") from error
    except (OSError, ValueError) as error:
        raise PDFIntakeError("PDF okuyucu başlatılamadı. Yeniden deneyin veya yöneticinizle iletişime geçin.") from error
    if process.returncode != 0 or "error" in result:
        raise PDFIntakeError(result.get("error", "PDF okunamadı."))
    return {"filename": PureWindowsPath(filename).name[:200], **result}


if __name__ == "__main__":
    try:
        print(json.dumps(extract_pdf_text(sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)), ensure_ascii=True))
    except PDFIntakeError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True))
        raise SystemExit(1)
