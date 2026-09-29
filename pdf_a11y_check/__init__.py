"""pdf-a11y-check: automated accessibility and quality checks for PDF files."""
__version__ = "1.0.0"

from .checks import CHECKS, Finding, Report, check_pdf  # noqa: E402

__all__ = ["CHECKS", "Finding", "Report", "check_pdf", "__version__"]
