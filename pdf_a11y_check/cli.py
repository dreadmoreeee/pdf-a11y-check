"""pdf-a11y-check FILE|DIR|GLOB ... [--format text|markdown|json] [--fail-on error|warning|info|never]

Exit codes: 0 no finding at or above --fail-on, 1 findings at or above --fail-on,
2 usage error or a file that could not be read.
"""
from __future__ import annotations

import argparse
import glob
import logging
import sys
from pathlib import Path

from . import __version__
from .checks import CHECKS, RANK, Report, check_pdf
from .report import FORMATS, list_checks


def expand(inputs: list[str]) -> tuple[list[Path], list[str]]:
    """Turn files, directories (searched recursively for *.pdf) and globs into a list of files."""
    files: list[Path] = []
    missing: list[str] = []

    def add_dir(d: Path):
        files.extend(sorted(p for p in d.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"))

    for item in inputs:
        p = Path(item)
        if p.is_dir():
            add_dir(p)
        elif p.is_file():
            files.append(p)
        elif glob.has_magic(item):
            matches = sorted(glob.glob(item, recursive=True))
            found = False
            for m in matches:
                mp = Path(m)
                if mp.is_dir():
                    add_dir(mp)
                    found = True
                elif mp.suffix.lower() == ".pdf":
                    files.append(mp)
                    found = True
            if not found:
                missing.append(item)
        else:
            missing.append(item)
    seen, unique = set(), []
    for f in files:
        k = str(f.resolve()).lower()
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique, missing


def _skip_list(values: list[str]) -> set[str]:
    out = {s.strip() for v in values for s in v.split(",") if s.strip()}
    unknown = out - set(CHECKS)
    if unknown:
        raise SystemExit(f"error: unknown check id(s) for --skip: {', '.join(sorted(unknown))} "
                         "(see --list-checks)")
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="pdf-a11y-check",
        description="Automated accessibility and quality checks for PDF files (not a full PDF/UA validation).")
    p.add_argument("paths", nargs="*", help="PDF files, directories or glob patterns")
    p.add_argument("-f", "--format", choices=["text", "markdown", "md", "json"], default="text")
    p.add_argument("-o", "--output", type=Path, help="write the report to this file instead of stdout")
    p.add_argument("--fail-on", choices=["error", "warning", "info", "never"], default="error",
                   help="exit 1 when a finding at or above this severity exists (default: error)")
    p.add_argument("--max-kb-per-page", type=float, default=500, metavar="KB",
                   help="warn when the file is larger than this per page (default: 500)")
    p.add_argument("--skip", action="append", default=[], metavar="ID[,ID]", help="check ids to skip")
    p.add_argument("--password", help="password for encrypted files (an empty password is always tried)")
    p.add_argument("--list-checks", action="store_true", help="list the checks and exit")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    a = p.parse_args(argv)

    if a.list_checks:
        sys.stdout.write(list_checks())
        return 0
    if not a.paths:
        p.print_usage(sys.stderr)
        print("pdf-a11y-check: error: give at least one PDF file, directory or glob", file=sys.stderr)
        return 2
    try:
        skip = _skip_list(a.skip)
    except SystemExit as e:
        print(e, file=sys.stderr)
        return 2

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    files, missing = expand(a.paths)
    reports: list[Report] = [Report(path=m, error="no such file, or no PDF matched") for m in missing]
    reports += [check_pdf(f, name=f.as_posix(), max_kb_per_page=a.max_kb_per_page, password=a.password, skip=skip)
                for f in files]
    if not reports:
        print("pdf-a11y-check: error: no PDF files found", file=sys.stderr)
        return 2

    text = FORMATS[a.format](reports)
    if a.output:
        a.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)

    if any(r.error for r in reports):
        return 2
    if a.fail_on != "never":
        limit = RANK[a.fail_on]
        if any(RANK[f.severity] >= limit for r in reports for f in r.findings):
            return 1
    return 0
