"""Render reports as plain text, Markdown or JSON."""
from __future__ import annotations

import json

from . import __version__
from .checks import CHECKS, Report

NOTE = ("Automated checks only: this is not a full PDF/UA conformance validation "
        "(use PAC or veraPDF for that) and a manual review is still needed.")


def _counts(e: int, w: int, i: int) -> str:
    return f"{e} error(s), {w} warning(s), {i} info"


def summary(reports: list[Report]) -> dict:
    ok = [r for r in reports if not r.error]
    return {
        "files": len(reports),
        "unreadable": len(reports) - len(ok),
        "errors": sum(r.count("error") for r in ok),
        "warnings": sum(r.count("warning") for r in ok),
        "info": sum(r.count("info") for r in ok),
        "average_score": round(sum(r.score for r in ok) / len(ok)) if ok else None,
    }


def to_text(reports: list[Report]) -> str:
    lines: list[str] = []
    for r in reports:
        lines.append(r.path)
        if r.error:
            lines.append(f"  UNREADABLE  {r.error}")
            lines.append("")
            continue
        lines.append(f"  {r.pages} page(s), {r.size:,} bytes, score {r.score}/100")
        for f in r.findings:
            refs = f"  [{', '.join(f.refs)}]" if f.refs else ""
            lines.append(f"  {f.severity.upper():<8} {f.id:<18} {f.message}{refs}")
            lines += [f"  {'':<8} {'':<18} - {d}" for d in f.details]
        if r.passed:
            lines.append("  passed: " + ", ".join(r.passed))
        if r.not_applicable:
            lines.append("  not applicable: " + ", ".join(f"{k} ({v})" for k, v in r.not_applicable.items()))
        lines.append("  " + _counts(r.count("error"), r.count("warning"), r.count("info")))
        lines.append("")
    if len(reports) > 1:
        s = summary(reports)
        tail = f"{s['files']} file(s): {_counts(s['errors'], s['warnings'], s['info'])}"
        if s["average_score"] is not None:
            tail += f", average score {s['average_score']}/100"
        if s["unreadable"]:
            tail += f", {s['unreadable']} unreadable"
        lines.append(tail)
    lines.append(NOTE)
    return "\n".join(lines) + "\n"


def _cell(s: str) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def to_markdown(reports: list[Report]) -> str:
    out = ["# PDF accessibility report", "",
           "| File | Pages | Score | Errors | Warnings | Info |", "|---|---:|---:|---:|---:|---:|"]
    for r in reports:
        if r.error:
            out.append(f"| {_cell(r.path)} | - | unreadable | - | - | - |")
        else:
            out.append(f"| {_cell(r.path)} | {r.pages} | {r.score}/100 | {r.count('error')} | "
                       f"{r.count('warning')} | {r.count('info')} |")
    for r in reports:
        out += ["", f"## {_cell(r.path)}", ""]
        if r.error:
            out.append(f"Unreadable: {_cell(r.error)}")
            continue
        if r.findings:
            out += ["| Severity | Check | Finding | Reference |", "|---|---|---|---|"]
            for f in r.findings:
                out.append(f"| {f.severity} | `{f.id}` | {_cell(f.message)} | {_cell(', '.join(f.refs))} |")
            detailed = [f for f in r.findings if f.details]
            if detailed:
                out += ["", "Details:", ""]
                for f in detailed:
                    out.append(f"- `{f.id}`: " + "; ".join(_cell(d) for d in f.details))
        else:
            out.append("No findings.")
        if r.passed:
            out += ["", "Passed: " + ", ".join(f"`{c}`" for c in r.passed)]
        if r.not_applicable:
            out += ["", "Not applicable: " + ", ".join(f"`{k}` ({v})" for k, v in r.not_applicable.items())]
    out += ["", f"> {NOTE}", ""]
    return "\n".join(out)


def to_json(reports: list[Report]) -> str:
    doc = {"tool": "pdf-a11y-check", "version": __version__, "note": NOTE,
           "summary": summary(reports), "files": [r.to_dict() for r in reports]}
    return json.dumps(doc, indent=2, ensure_ascii=True) + "\n"


def list_checks() -> str:
    rows = [f"{c.id:<18} {c.severity:<8} {c.title}" + (f"  [{', '.join(c.refs)}]" if c.refs else "")
            for c in CHECKS.values()]
    return "\n".join(rows) + "\n"


FORMATS = {"text": to_text, "markdown": to_markdown, "md": to_markdown, "json": to_json}
