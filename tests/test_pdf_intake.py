import subprocess
import unittest
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.main import app
from app.pdf_intake import (PDFIntakeError, MAX_REQUEST_BYTES, extract_pdf_text,
                            extract_request_pdf)
from app.portal_auth import Principal, require_employee


def pdf_bytes(text="Synthetic training request: Excel pivot tables.", pages=1, encrypted=False):
    with fitz.open() as document:
        for _ in range(pages):
            page = document.new_page()
            if text:
                page.insert_text((50, 50), text)
        options = {"encryption": fitz.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "user"} if encrypted else {}
        return document.tobytes(**options)


class PDFIntakeTests(unittest.TestCase):
    def test_local_extraction_has_text_and_safe_filename(self):
        result = extract_request_pdf(pdf_bytes(), "C:\\private\\request.pdf")
        self.assertEqual(result["filename"], "request.pdf")
        self.assertIn("pivot tables", result["text"])
        self.assertEqual(result["page_count"], 1)
        self.assertFalse(result["truncated"])

    def test_scanned_encrypted_and_invalid_pdf_fail_explicitly(self):
        for data, detail in [(pdf_bytes(text=""), "OCR"),
                             (pdf_bytes(encrypted=True), "Şifreli"),
                             (b"<html>not PDF</html>", "geçerli")]:
            with self.subTest(detail=detail), self.assertRaisesRegex(PDFIntakeError, detail):
                extract_pdf_text(data)

    def test_partial_extraction_and_truncation_are_never_silent(self):
        with fitz.open() as document:
            for _ in range(20):
                page = document.new_page()
                page.insert_textbox(fitz.Rect(40, 40, 550, 790), "Relevant requirements. " * 70)
            document.new_page()
            result = extract_pdf_text(document.tobytes())
        self.assertEqual(len(result["text"]), 5000)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_page_limit_is_enforced_before_content_extraction(self):
        with self.assertRaisesRegex(PDFIntakeError, "100 sayfa"):
            extract_pdf_text(pdf_bytes(pages=101))

    def test_expensive_parser_is_bounded_by_timeout(self):
        with patch("app.pdf_intake.subprocess.run", side_effect=subprocess.TimeoutExpired("parser", 20)):
            with self.assertRaisesRegex(PDFIntakeError, "süresi aşıldı"):
                extract_request_pdf(pdf_bytes(), "request.pdf")

    def test_employee_upload_extracts_without_creating_a_request(self):
        old_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[require_employee] = lambda: Principal(9999, "synthetic", "Synthetic", "EMPLOYEE")
        try:
            with patch("app.main.analyze_request") as analyze:
                response = TestClient(app).post("/api/requests/extract-pdf", files={"file": ("request.pdf", pdf_bytes(), "application/pdf")})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIn("pivot tables", response.json()["text"])
                analyze.assert_not_called()
            response = TestClient(app).post("/api/requests/extract-pdf", files={"file": ("too-big.pdf", b"x" * (MAX_REQUEST_BYTES + 1), "application/pdf")})
            self.assertEqual(response.status_code, 413)
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(old_overrides)

    def test_anonymous_upload_is_denied(self):
        response = TestClient(app).post("/api/requests/extract-pdf", files={"file": ("request.pdf", pdf_bytes(), "application/pdf")})
        self.assertEqual(response.status_code, 401)
