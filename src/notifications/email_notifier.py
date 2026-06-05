from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from loguru import logger

_REPORTS_DIR = Path(__file__).parent.parent.parent / "reports"


class EmailNotifier:
    """Write the morning brief to dated files for pickup by a Claude Routine.

    Produces:
      - reports/morning_email_<date>.html  (rich HTML, primary)
      - reports/morning_email_<date>.txt   (plain-text fallback)

    Does NOT send via SMTP.
    """

    def __init__(self, settings) -> None:
        self.settings = settings
        self._recipient = getattr(settings, "email_recipient", "") or ""
        self._date_str  = date.today().strftime("%Y-%m-%d")
        self._txt_path  = _REPORTS_DIR / f"morning_email_{self._date_str}.txt"
        self._html_path = _REPORTS_DIR / f"morning_email_{self._date_str}.html"
        self._first_write = True

    # ── HTML generation ────────────────────────────────────────────────────

    def write_html(
        self,
        bundle: dict,
        narrative: str,
        date_str: str,
        out_dir: Path,
    ) -> Path:
        """Generate the rich HTML report and write it to <out_dir>."""
        from src.report.html_report import generate_html_report

        signals = bundle.get("signals", {})
        html    = generate_html_report(bundle, narrative, signals)

        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"morning_email_{date_str}.html"
        html_path.write_text(html, encoding="utf-8")
        self._html_path = html_path
        logger.info(f"[EmailNotifier] HTML brief written → {html_path}")
        return html_path

    # ── Plain-text fallback ────────────────────────────────────────────────

    def send(self, message: str, recipient: str | None = None) -> bool:
        to = recipient or self._recipient

        if self.settings.dry_run:
            sep = "=" * 60
            if hasattr(sys.stdout, "reconfigure"):
                sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(f"\n{sep}\n[DRY RUN - EMAIL] TO: {to}\n{sep}\n{message}\n{sep}")
            logger.info("[DRY_RUN] EmailNotifier — files NOT written")
            return True

        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        if self._first_write:
            header = f"TO: {to}\nDATE: {self._date_str}\n\n"
            self._txt_path.write_text(header + message, encoding="utf-8")
            self._first_write = False
        else:
            with self._txt_path.open("a", encoding="utf-8") as f:
                f.write("\n\n---\n\n" + message)

        logger.info(f"[EmailNotifier] TXT brief written → {self._txt_path}")
        return True
