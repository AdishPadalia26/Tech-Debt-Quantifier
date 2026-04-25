"""Compatibility import shim for PDF report generation."""

from reports.pdf_generator import TechDebtPDFGenerator, generate_pdf_report

__all__ = ["TechDebtPDFGenerator", "generate_pdf_report"]
