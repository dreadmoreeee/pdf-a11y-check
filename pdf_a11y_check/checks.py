"""Automated accessibility and quality checks for one PDF file.

These are heuristics over the file structure (tags, metadata, fonts, annotations).
They catch common, machine-detectable problems; they are not a PDF/UA conformance
validation and do not replace a manual review with a screen reader.
"""
from __future__ import annotations

import io
import os
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from pypdf.generic import IndirectObject

SEVERITIES = ("info", "warning", "error")
RANK = {"info": 1, "warning": 2, "error": 3}


@dataclass(frozen=True)
class Check:
    id: str
    severity: str  # highest severity this check can report
    refs: tuple[str, ...]
    title: str


CHECKS: dict[str, Check] = {c.id: c for c in (
    Check("tagged", "error", ("WCAG 1.3.1", "WCAG 1.3.2", "PDF/UA 7.1"),
          "Tagged PDF: structure tree and /MarkInfo /Marked true"),
    Check("title", "error", ("WCAG 2.4.2", "PDF18", "PDF/UA 7.1"),
          "Document title in Info /Title or XMP dc:title"),
    Check("display-doc-title", "warning", ("WCAG 2.4.2", "PDF18", "PDF/UA 7.1"),
          "/ViewerPreferences /DisplayDocTitle true"),
    Check("lang", "error", ("WCAG 3.1.1", "PDF16", "PDF/UA 7.2"),
          "Document language /Lang in the catalog (BCP 47)"),
    Check("text", "error", ("WCAG 1.1.1", "WCAG 1.4.5", "PDF7"),
          "Pages have extractable text (not scanned or image-only)"),
    Check("fonts-embedded", "warning", ("PDF/UA 7.21.4.1",),
          "Fonts are embedded (FontFile, FontFile2, FontFile3)"),
    Check("fonts-unicode", "warning", ("WCAG 1.3.1", "PDF/UA 7.21.7"),
          "Fonts map to Unicode (ToUnicode or a standard encoding)"),
    Check("figure-alt", "error", ("WCAG 1.1.1", "PDF1", "PDF/UA 7.3"),
          "Figure tags have /Alt or /ActualText"),
    Check("structure", "warning", ("WCAG 1.3.1", "WCAG 1.3.2", "PDF/UA 7.1"),
          "Heuristic: tags describe content and point to page content"),
    Check("headings", "info", ("WCAG 1.3.1", "WCAG 2.4.6", "PDF9", "PDF/UA 7.4"),
          "Heuristic: heading tags (H, H1-H6) are present"),
    Check("table-headers", "warning", ("WCAG 1.3.1", "PDF6", "PDF/UA 7.5"),
          "Table tags have header cells (TH)"),
    Check("role-map", "warning", ("PDF/UA 7.1",),
          "Role map: custom tags map to standard types, no cycles or remapped standard types"),
    Check("tab-order", "warning", ("WCAG 2.4.3", "PDF3", "PDF/UA 7.18.3"),
          "Pages with annotations use /Tabs /S (structure order)"),
    Check("form-tooltips", "warning", ("WCAG 1.3.1", "WCAG 3.3.2", "WCAG 4.1.2", "PDF10", "PDF12", "PDF/UA 7.18"),
          "Form fields have a tooltip (/TU)"),
    Check("link-target", "warning", ("WCAG 2.4.4", "PDF11"),
          "Link annotations have an action or destination"),
    Check("link-contents", "warning", ("WCAG 2.4.4", "PDF13", "PDF/UA 7.18.5"),
          "Link annotations have a description in /Contents"),
    Check("encryption", "error", ("PDF/UA 7.16",),
          "Encryption permissions do not block assistive technology"),
    Check("file-size", "warning", (),
          "File size per page below a limit (quality check)"),
    Check("metadata", "info", (),
          "Metadata does not expose local paths, user names, hosts or software versions"),
    Check("pdfua-id", "info", ("PDF/UA 5",),
          "PDF/UA identifier (pdfuaid:part) in XMP"),
)}


@dataclass
class Finding:
    id: str
    severity: str
    message: str
    refs: list[str]
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "severity": self.severity, "message": self.message,
                "refs": self.refs, "details": self.details}


@dataclass
class Report:
    path: str
    size: int = 0
    pages: int = 0
    findings: list[Finding] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    not_applicable: dict[str, str] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    error: str | None = None

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def score(self) -> int:
        """Rough 0-100 summary: -15 per error, -5 per warning, info is free."""
        if self.error:
            return 0
        return max(0, 100 - 15 * self.count("error") - 5 * self.count("warning"))

    def worst(self) -> str | None:
        ranks = [RANK[f.severity] for f in self.findings]
        return SEVERITIES[max(ranks) - 1] if ranks else None

    def finding(self, cid: str) -> Finding | None:
        return next((f for f in self.findings if f.id == cid), None)

    def to_dict(self) -> dict:
        return {"path": self.path, "size": self.size, "pages": self.pages, "score": self.score,
                "error": self.error,
                "counts": {s: self.count(s) for s in ("error", "warning", "info")},
                "findings": [f.to_dict() for f in self.findings],
                "passed": self.passed, "not_applicable": self.not_applicable, "stats": self.stats}


# ---------------------------------------------------------------- helpers

STANDARD_14 = frozenset("""Times-Roman Times-Bold Times-Italic Times-BoldItalic Helvetica Helvetica-Bold
Helvetica-Oblique Helvetica-BoldOblique Courier Courier-Bold Courier-Oblique Courier-BoldOblique
Symbol ZapfDingbats""".split())

STANDARD_TYPES = frozenset("""Document Part Art Sect Div BlockQuote Caption TOC TOCI Index NonStruct Private
P H H1 H2 H3 H4 H5 H6 L LI Lbl LBody Table TR TH TD THead TBody TFoot Span Quote Note Reference BibEntry
Code Link Annot Ruby RB RT RP Warichu WT WP Figure Formula Form
DocumentFragment Aside Title FENote Sub Em Strong Artifact""".split())

GROUPING_TYPES = frozenset("Document DocumentFragment Part Art Sect Div NonStruct Private Span Artifact".split())
HEADING_TYPES = frozenset("H H1 H2 H3 H4 H5 H6".split())
STANDARD_ENCODINGS = frozenset(("/WinAnsiEncoding", "/MacRomanEncoding", "/StandardEncoding", "/PDFDocEncoding"))

LANG_RE = re.compile(
    r"^(?:[A-Za-z]{2,3}(?:-[A-Za-z]{3}){0,3}|[A-Za-z]{4,8})"  # language (+ extlang)
    r"(?:-[A-Za-z]{4})?"                                       # script
    r"(?:-(?:[A-Za-z]{2}|\d{3}))?"                             # region
    r"(?:-(?:[A-Za-z0-9]{5,8}|\d[A-Za-z0-9]{3}))*"             # variants
    r"(?:-[0-9A-WY-Za-wy-z](?:-[A-Za-z0-9]{2,8})+)*"            # extensions
    r"(?:-[xX](?:-[A-Za-z0-9]{1,8})+)?$"                       # private use
    r"|^[xX](?:-[A-Za-z0-9]{1,8})+$")

FILENAME_TITLE_RE = re.compile(
    r"(\.(docx?|xlsx?|pptx?|indd|odt|ods|odp|rtf|txt|pages|pdf|html?|psd|ai)$)|^microsoft (word|excel|powerpoint) - "
    r"|^(untitled|document|untitled document|title)$", re.I)

XMP_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "dc": "http://purl.org/dc/elements/1.1/",
    "pdfuaid": "http://www.aiim.org/pdfua/ns/id/",
}
MAX_DETAILS = 10
MIN_TEXT_CHARS = 20  # letters/digits on a page before it counts as "has text"


def _r(obj):
    """Resolve an indirect reference (pypdf objects resolve to themselves)."""
    return obj.get_object() if obj is not None and hasattr(obj, "get_object") else obj


def _get(d, key):
    return _r(d.get(key)) if isinstance(d, dict) else None


def _text(obj) -> str:
    obj = _r(obj)
    if obj is None:
        return ""
    if isinstance(obj, bytes):
        return obj.decode("latin-1", "replace").strip()
    return str(obj).strip()


def _name(obj) -> str:
    obj = _r(obj)
    return str(obj)[1:] if isinstance(obj, str) and str(obj).startswith("/") else _text(obj)


def _key(raw, obj):
    if isinstance(raw, IndirectObject):
        return ("ref", raw.idnum, raw.generation)
    return ("id", id(obj))


def _cap(items: list[str], limit: int = MAX_DETAILS) -> list[str]:
    items = list(items)
    if len(items) <= limit:
        return items
    return items[:limit] + [f"... and {len(items) - limit} more"]


def _pages_str(nums: list[int]) -> str:
    return ", ".join(str(n) for n in nums[:20]) + (" ..." if len(nums) > 20 else "")


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


class _Out:
    def __init__(self, report: Report, skip: set[str]):
        self.report, self.skip = report, skip

    def add(self, cid: str, severity: str, message: str, details=()) -> None:
        if cid in self.skip:
            return
        refs = list(CHECKS[cid].refs)
        self.report.findings.append(Finding(cid, severity, message, refs, _cap(list(details))))

    def ok(self, cid: str) -> None:
        if cid not in self.skip:
            self.report.passed.append(cid)

    def na(self, cid: str, reason: str) -> None:
        if cid not in self.skip:
            self.report.not_applicable[cid] = reason


# ---------------------------------------------------------------- XMP

@dataclass
class _Xmp:
    present: bool = False
    titles: list[str] = field(default_factory=list)
    pdfua_part: str | None = None
    values: list[tuple[str, str]] = field(default_factory=list)  # (local name, text) for leak scanning
    error: str | None = None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_xmp(root) -> _Xmp:
    x = _Xmp()
    meta = _get(root, "/Metadata")
    if meta is None or not hasattr(meta, "get_data"):
        return x
    try:
        data = meta.get_data()
    except Exception as e:  # noqa: BLE001 - broken stream filters
        return _Xmp(present=True, error=f"cannot read XMP stream: {e}")
    x.present = True
    if len(data) > 4_000_000 or b"<!ENTITY" in data:
        x.error = "XMP skipped (too large or uses entity declarations)"
        return x
    try:
        tree = ET.fromstring(data.strip())
    except ET.ParseError as e:
        x.error = f"XMP is not well-formed XML: {e}"
        return x
    title_tag = "{%s}title" % XMP_NS["dc"]
    part_tag = "{%s}part" % XMP_NS["pdfuaid"]
    rdf = "{%s}" % XMP_NS["rdf"]

    def visit(el, label: str, depth: int):
        if not isinstance(el.tag, str) or depth > 50:
            return
        if el.tag == title_tag:
            t = " ".join(s.strip() for s in el.itertext() if s.strip())
            if t:
                x.titles.append(t)
        if el.tag == part_tag and (el.text or "").strip():
            x.pdfua_part = el.text.strip()
        if part_tag in el.attrib:
            x.pdfua_part = el.attrib[part_tag].strip()
        # rdf:li / rdf:Alt / rdf:Description keep the name of the property that holds them
        if not el.tag.startswith(rdf) and _local(el.tag) != "xmpmeta":
            label = _local(el.tag)
        if el.text and el.text.strip() and label:
            x.values.append(("XMP " + label, el.text.strip()))
        for k, v in el.attrib.items():
            if not k.startswith(rdf) and v.strip():
                x.values.append(("XMP " + _local(k), v.strip()))
        for child in el:
            visit(child, label, depth + 1)

    visit(tree, "", 0)
    return x


# ---------------------------------------------------------------- metadata leaks

LEAK_PATTERNS = [
    ("local Windows path", re.compile(r"\b[A-Za-z]:[\\/][^\s\"<>|]+")),
    ("network share path", re.compile(r"\\\\[A-Za-z0-9._$-]+\\[^\s\"<>|]+")),
    ("local home folder path", re.compile(r"(?<![\w.:/])/(?:home|Users|root)/[^\s\"<>|]+")),
    ("file:// URL", re.compile(r"\bfile:/+[^\s\"<>]+", re.I)),
    ("internal host name", re.compile(
        r"\b(?:localhost|[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:local|lan|internal|intranet|corp|localdomain|home\.arpa))\b",
        re.I)),
    ("private IP address", re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b")),
    ("DOMAIN\\user account", re.compile(r"\b[A-Z][A-Z0-9-]{1,14}\\[A-Za-z][\w.-]+")),
]
VERSION_RE = re.compile(r"\d+\.\d+")
SOFTWARE_KEYS = {"Creator", "Producer", "CreatorTool", "softwareAgent"}
LOGIN_RE = re.compile(r"^[a-z][a-z0-9._-]{2,20}$")


def _leaks(values: list[tuple[str, str]]) -> list[str]:
    out: list[str] = []
    seen: set[tuple[str, str]] = set()

    def add(where: str, value: str, what: str):
        if (value, what) not in seen:
            seen.add((value, what))
            shown = value if len(value) <= 80 else value[:77] + "..."
            out.append(f"{where}: '{shown}' ({what})")

    for where, value in values:
        key = where.split()[-1]
        for what, rx in LEAK_PATTERNS:
            for m in rx.finditer(value):
                add(where, m.group(0), what)
        if key in SOFTWARE_KEYS and VERSION_RE.search(value):
            add(where, value, "software name and version")
        if key in ("Author", "creator") and LOGIN_RE.match(value):
            add(where, value, "looks like a login name")
    return out


# ---------------------------------------------------------------- resources

TEXT_SHOW_RE = re.compile(rb"(?:\)|>|\])\s*(?:Tj|TJ|'|\")")
DO_RE = re.compile(rb"/([^\s/\[\]()<>{}%]+)\s+Do\b")
FONT_USE_RE = re.compile(rb"/([^\s/\[\]()<>{}%]+)\s+[-+\d.]+\s+Tf\b|(?:\)|>|\])\s*(?:Tj|TJ|'|\")")


def _fonts_showing_text(content: bytes) -> set[bytes]:
    """Font resource names that are selected (Tf) and then used to show text (Tj, TJ, ', ")."""
    used, current = set(), None
    for m in FONT_USE_RE.finditer(content):
        if m.group(1):
            current = m.group(1)
        elif current:
            used.add(current)
    return used


def _used(name, used: set[bytes] | None) -> bool:
    return used is None or str(name)[1:].encode("latin-1", "replace") in used


def _scan_resources(raw_res, content: bytes | None, fonts: dict, seen: set, depth: int = 0) -> int:
    """Collect the fonts the content uses into `fonts`; return the number of images it draws.

    Resource dictionaries often list fonts and images that are never used (shared resources,
    a default font), so only fonts that show text and images drawn with Do in `content` count.
    When the content cannot be read (content=None) every resource counts.
    """
    res = _r(raw_res)
    if not isinstance(res, dict) or depth > 12:
        return 0
    used_fonts = _fonts_showing_text(content) if content is not None else None
    used_xobjects = set(DO_RE.findall(content)) if content is not None else None
    images = 0
    font_dict = _get(res, "/Font")
    if isinstance(font_dict, dict):
        for name, ref in font_dict.items():
            f = _r(ref)
            if isinstance(f, dict) and _used(name, used_fonts):
                k = _key(ref, f)
                if k not in fonts:
                    fonts[k] = f
                    if f.get("/Subtype") == "/Type3":
                        _scan_resources(f.get("/Resources"), None, fonts, seen, depth + 1)
    xobjects = _get(res, "/XObject")
    if isinstance(xobjects, dict):
        for name, ref in xobjects.items():
            x = _r(ref)
            if not isinstance(x, dict) or not _used(name, used_xobjects):
                continue
            subtype = x.get("/Subtype")
            if subtype == "/Image":
                images += 1
            elif subtype == "/Form":
                k = _key(ref, x)
                if k not in seen:
                    seen.add(k)
                    try:
                        data = x.get_data()
                    except Exception:  # noqa: BLE001
                        data = None
                    images += _scan_resources(x.get("/Resources"), data, fonts, seen, depth + 1)
    return images


def _font_label(f: dict) -> str:
    base = _name(f.get("/BaseFont")) or "(unnamed)"
    return base.split("+", 1)[1] if re.match(r"^[A-Z]{6}\+", base) else base


def _font_embedded(f: dict) -> bool:
    subtype = f.get("/Subtype")
    if subtype == "/Type3":
        return True  # glyphs are content streams inside the PDF
    desc = f
    if subtype == "/Type0":
        kids = _get(f, "/DescendantFonts")
        desc = _r(kids[0]) if isinstance(kids, list) and kids else {}
    fd = _get(desc, "/FontDescriptor")
    return isinstance(fd, dict) and any(k in fd for k in ("/FontFile", "/FontFile2", "/FontFile3"))


def _font_unicode_problem(f: dict) -> str | None:
    """Return 'warning'/'info' when text in this font may not map to Unicode."""
    if "/ToUnicode" in f:
        return None
    subtype = f.get("/Subtype")
    if subtype == "/Type0":
        enc = _name(f.get("/Encoding"))
        kids = _get(f, "/DescendantFonts")
        desc = _r(kids[0]) if isinstance(kids, list) and kids else {}
        info = _get(desc, "/CIDSystemInfo")
        ordering = _text(_get(info, "/Ordering")) if isinstance(info, dict) else ""
        if enc in ("Identity-H", "Identity-V") or ordering in ("Identity", ""):
            return "warning"
        return None  # predefined CJK CMaps can be mapped by readers
    if subtype == "/Type3":
        return "info"
    base = _font_label(f)
    if base in ("Symbol", "ZapfDingbats"):
        return "info"
    enc = _r(f.get("/Encoding"))
    if enc is None:
        fd = _get(f, "/FontDescriptor")
        flags = int(_r(fd.get("/Flags", 0)) or 0) if isinstance(fd, dict) else 0
        symbolic = bool(flags & 4) and not (flags & 32)
        return "info" if symbolic and base not in STANDARD_14 else None
    if isinstance(enc, dict):
        if "/Differences" in enc:
            return "info"
        return None
    return None if str(enc) in STANDARD_ENCODINGS else "info"


# ---------------------------------------------------------------- structure tree

@dataclass
class _Struct:
    elements: list[dict] = field(default_factory=list)
    roles: Counter = field(default_factory=Counter)
    mcids: int = 0
    objrs: int = 0
    unknown: Counter = field(default_factory=Counter)


def _resolve_role(name: str, rolemap: dict[str, str]) -> tuple[str, str | None]:
    seen = [name]
    cur = name
    while cur not in STANDARD_TYPES:
        nxt = rolemap.get(cur)
        if nxt is None:
            return cur, None if cur == name else f"/{name} maps to /{cur}, which is not a standard type"
        if nxt in seen:
            return cur, "circular role mapping: " + " -> ".join("/" + s for s in seen + [nxt])
        seen.append(nxt)
        cur = nxt
    return cur, None


def _walk_struct(tree_root: dict, rolemap: dict[str, str]) -> _Struct:
    st = _Struct()
    stack = [tree_root.get("/K")]
    seen: set = set()
    steps = 0
    while stack and steps < 500_000:
        steps += 1
        raw = stack.pop()
        if isinstance(raw, IndirectObject):
            k = (raw.idnum, raw.generation)
            if k in seen:
                continue
            seen.add(k)
        node = _r(raw)
        if isinstance(node, list):
            stack.extend(reversed(node))
            continue
        if isinstance(node, int):
            st.mcids += 1
            continue
        if not isinstance(node, dict):
            continue
        typ = node.get("/Type")
        if typ == "/MCR":
            st.mcids += 1
            continue
        if typ == "/OBJR":
            st.objrs += 1
            continue
        s = node.get("/S")
        if s is None:
            continue
        name = _name(s)
        role, _problem = _resolve_role(name, rolemap)
        node_role = role if role in STANDARD_TYPES else None
        st.elements.append({"node": node, "name": name, "role": node_role})
        st.roles[node_role or name] += 1
        if node_role is None:
            st.unknown[name] += 1
        if node.get("/K") is not None:
            stack.append(node.get("/K"))
    return st


# ---------------------------------------------------------------- main entry

def check_pdf(source, *, name: str | None = None, max_kb_per_page: float = 500,
              password: str | None = None, skip=()) -> Report:
    """Run every check on a PDF given as a path or as bytes and return a Report."""
    skip = {s.strip() for s in skip if s and s.strip()}
    if isinstance(source, (bytes, bytearray)):
        report = Report(path=name or "<bytes>", size=len(source))
        stream = io.BytesIO(bytes(source))
    else:
        path = Path(source)
        report = Report(path=name or str(source))
        try:
            report.size = os.path.getsize(path)
            stream = io.BytesIO(path.read_bytes())
        except OSError as e:
            report.error = f"cannot read file: {e.strerror or e}"
            return report
    try:
        reader = PdfReader(stream, strict=False)
    except Exception as e:  # noqa: BLE001 - pypdf raises many types on garbage
        report.error = f"not a readable PDF: {e}"
        return report

    out = _Out(report, skip)
    try:
        if not _open_encrypted(reader, password, report, out):
            return report
        _run(reader, report, out, max_kb_per_page)
    except Exception as e:  # noqa: BLE001 - keep one broken file from stopping a batch
        report.error = f"could not analyse the PDF: {type(e).__name__}: {e}"
    return report


def _open_encrypted(reader: PdfReader, password, report: Report, out: _Out) -> bool:
    report.stats["encrypted"] = bool(reader.is_encrypted)
    if not reader.is_encrypted:
        out.ok("encryption")
        return True
    try:
        result = reader.decrypt(password or "")
    except Exception as e:  # noqa: BLE001 - e.g. AES without a crypto library
        report.error = f"encrypted PDF could not be decrypted: {e}"
        return False
    if not result:
        report.error = ("encrypted PDF needs a password to open"
                        + (" (the password given did not work)" if password else "; use --password"))
        return False
    enc = _r(reader.trailer.get("/Encrypt"))
    p = int(_r(enc.get("/P", -1))) & 0xFFFFFFFF if isinstance(enc, dict) else 0xFFFFFFFF
    revision = int(_r(enc.get("/R", 2))) if isinstance(enc, dict) else 2
    copy_ok = bool(p & (1 << 4))
    at_ok = bool(p & (1 << 9)) if revision >= 3 else copy_ok
    report.stats["permissions"] = {"P": p - (1 << 32) if p & (1 << 31) else p, "R": revision,
                                   "copy": copy_ok, "accessibility_extraction": at_ok}
    if not at_ok:
        out.add("encryption", "error",
                "The file is encrypted and its permissions turn off text extraction for accessibility "
                "(permission bit 10). Screen readers that respect permissions cannot read it. "
                "Allow 'content accessibility' (or remove the restrictions) when saving.")
    elif not copy_ok:
        out.add("encryption", "info",
                "The file is encrypted and copying is turned off, but text extraction for accessibility is "
                "allowed, so current screen readers can read it. Some older tools rely on the copy permission.")
    else:
        out.add("encryption", "info",
                "The file is encrypted (owner password only); its permissions do not block assistive technology.")
    return True


def _run(reader: PdfReader, report: Report, out: _Out, max_kb_per_page: float) -> None:
    root = _r(reader.trailer.get("/Root"))
    if not isinstance(root, dict):
        raise ValueError("no document catalog")
    pages = list(reader.pages)
    report.pages = len(pages)
    if not pages:
        report.error = "the PDF has no pages"
        return
    page_num = {}
    for i, pg in enumerate(pages, 1):
        ref = getattr(pg, "indirect_reference", None)
        if ref is not None:
            page_num[(ref.idnum, ref.generation)] = i

    info = _r(reader.trailer.get("/Info"))
    info = info if isinstance(info, dict) else {}
    xmp = _parse_xmp(root)
    if xmp.error:
        report.stats["xmp_error"] = xmp.error

    # ---- per-page scan: text, images, fonts, annotations
    fonts: dict = {}
    no_text: list[tuple[int, str]] = []
    text_pages = 0
    images_total = 0
    annots_pages: list[int] = []
    tabs_bad: list[int] = []
    links: list[tuple[int, dict]] = []
    for i, page in enumerate(pages, 1):
        try:
            txt = page.extract_text() or ""
        except Exception:  # noqa: BLE001
            txt = ""
        try:
            content = page.get_contents()
            data = content.get_data() if content is not None else b""
        except Exception:  # noqa: BLE001
            data = None
        images = _scan_resources(page.get("/Resources"), data, fonts, set())
        images_total += images
        data = data or b""
        if sum(ch.isalnum() for ch in txt) >= MIN_TEXT_CHARS:
            text_pages += 1
        elif images:
            no_text.append((i, "image only, looks scanned"))
        elif TEXT_SHOW_RE.search(data):
            no_text.append((i, "text is drawn but cannot be extracted"))
        else:
            no_text.append((i, "no text or images"))
        annots = _get(page, "/Annots")
        page_annots = [a for a in (_r(x) for x in annots) if isinstance(a, dict)] if isinstance(annots, list) else []
        visible = [a for a in page_annots if a.get("/Subtype") != "/Popup"]
        if visible:
            annots_pages.append(i)
            if _name(page.get("/Tabs")) != "S":
                tabs_bad.append(i)
        links += [(i, a) for a in page_annots if a.get("/Subtype") == "/Link"]
    report.stats.update(text_pages=text_pages, images=images_total, fonts=len(fonts))

    # ---- tagged
    mark = _get(root, "/MarkInfo")
    marked = isinstance(mark, dict) and bool(_r(mark.get("/Marked")))
    suspects = isinstance(mark, dict) and bool(_r(mark.get("/Suspects")))
    tree_root = _get(root, "/StructTreeRoot")
    has_tree = isinstance(tree_root, dict)
    report.stats["tagged"] = has_tree and marked
    if not has_tree:
        msg = ("The PDF is not tagged (no structure tree). Screen readers have to guess the reading order "
               "and cannot tell headings, lists, tables or images apart.")
        if images_total:
            msg += f" The {_plural(images_total, 'image')} on the pages cannot carry alternate text without tags."
        msg += " Export with 'tagged PDF' turned on, or add tags in a PDF editor."
        out.add("tagged", "error", msg)
    elif not marked:
        out.add("tagged", "warning",
                "A structure tree exists but /MarkInfo /Marked is not true, so some readers ignore the tags.")
    elif suspects:
        out.add("tagged", "warning",
                "/MarkInfo /Suspects is true: the tags were flagged as possibly unreliable by the producer.")
    else:
        out.ok("tagged")

    # ---- title and DisplayDocTitle
    info_title = _text(info.get("/Title"))
    titles = [t for t in [info_title] + xmp.titles if t]
    report.stats["title"] = titles[0] if titles else None
    if not titles:
        out.add("title", "error",
                "No document title. Screen readers and browser tabs announce the file name instead. "
                "Set a descriptive title (e.g. 'Invoice INV-1042 - Example Bakery').")
    elif FILENAME_TITLE_RE.search(titles[0]):
        out.add("title", "warning",
                f"The title '{titles[0]}' looks like a file name or a placeholder; use a descriptive title.")
    elif not xmp.titles:
        out.add("title", "info",
                f"Title '{titles[0]}' is set in the Info dictionary only; PDF/UA expects it in the XMP "
                "metadata (dc:title) as well.")
    else:
        out.ok("title")

    prefs = _get(root, "/ViewerPreferences")
    display = isinstance(prefs, dict) and bool(_r(prefs.get("/DisplayDocTitle")))
    if display:
        out.ok("display-doc-title")
    else:
        out.add("display-doc-title", "warning",
                "/ViewerPreferences /DisplayDocTitle is not true, so viewers show the file name in the "
                "window title instead of the document title.")

    # ---- language
    lang = _text(root.get("/Lang"))
    report.stats["lang"] = lang or None
    if not lang:
        out.add("lang", "error",
                "No document language (/Lang). Screen readers may read the text with the wrong voice and "
                "pronunciation. Set it, e.g. 'en-CA' or 'fr-CA'.")
    elif not LANG_RE.match(lang):
        out.add("lang", "warning", f"/Lang '{lang}' does not look like a BCP 47 language tag (e.g. 'en-CA').")
    else:
        out.ok("lang")

    # ---- extractable text
    if text_pages == 0:
        out.add("text", "error",
                "No page has extractable text. The file looks scanned or image-only, so screen readers "
                "get nothing. Run OCR and tag the result, or export from the original document.",
                [f"page {n}: {why}" for n, why in no_text])
    elif no_text:
        out.add("text", "warning",
                f"{len(no_text)} of {len(pages)} pages have no extractable text.",
                [f"page {n}: {why}" for n, why in no_text])
    else:
        out.ok("text")

    # ---- fonts
    if not fonts:
        out.na("fonts-embedded", "no fonts")
        out.na("fonts-unicode", "no fonts")
    else:
        not_embedded = sorted({_font_label(f) for f in fonts.values() if not _font_embedded(f)})
        report.stats["fonts_not_embedded"] = len(not_embedded)
        if not_embedded:
            std = [n for n in not_embedded if n in STANDARD_14]
            if std and len(std) == len(not_embedded):
                kind = " (standard-14 fonts, which viewers are expected to supply)"
            else:
                kind = f" ({len(std)} of them standard-14)" if std else ""
            out.add("fonts-embedded", "warning",
                    f"Not embedded: {len(not_embedded)} of {_plural(len(fonts), 'font')}{kind}. Viewers "
                    "substitute a local font, so spacing and glyphs can differ between devices, and PDF/UA "
                    "requires every font to be embedded.",
                    [n + (" (standard 14)" if n in STANDARD_14 else "") for n in not_embedded])
        else:
            out.ok("fonts-embedded")
        problems = {}
        for f in fonts.values():
            sev = _font_unicode_problem(f)
            if sev:
                label = f"{_font_label(f)} ({_name(f.get('/Subtype')) or 'font'})"
                problems[label] = "warning" if sev == "warning" or problems.get(label) == "warning" else "info"
        if problems:
            sev = "warning" if "warning" in problems.values() else "info"
            out.add("fonts-unicode", sev,
                    f"{_plural(len(problems), 'font')} without a ToUnicode map or a standard encoding. "
                    "Text in these fonts may be read out or copied as the wrong characters.",
                    sorted(problems))
        else:
            out.ok("fonts-unicode")

    # ---- structure tree checks
    tag_checks = ("figure-alt", "structure", "headings", "table-headers", "role-map")
    if not has_tree:
        for cid in tag_checks:
            out.na(cid, "not tagged")
    else:
        _structure_checks(tree_root, report, out, text_pages, page_num)

    # ---- tab order
    if not annots_pages:
        out.na("tab-order", "no annotations")
    elif tabs_bad:
        out.add("tab-order", "warning",
                f"{_plural(len(tabs_bad), 'page')} with links or form fields do not set /Tabs /S, so the Tab key "
                "may not follow the reading order.",
                [f"pages {_pages_str(tabs_bad)}"])
    else:
        out.ok("tab-order")

    # ---- forms
    _form_checks(root, report, out)

    # ---- links
    report.stats["links"] = len(links)
    if not links:
        out.na("link-target", "no links")
        out.na("link-contents", "no links")
    else:
        no_target, no_contents = [], []
        for n, a in links:
            label = f"page {n}"
            action = _get(a, "/A")
            uri = _text(_get(action, "/URI")) if isinstance(action, dict) else ""
            if uri:
                label += f": {uri}"
            if not _link_has_target(a, action):
                no_target.append(label)
            if not _text(a.get("/Contents")):
                no_contents.append(label)
        if no_target:
            out.add("link-target", "warning",
                    f"{len(no_target)} of {_plural(len(links), 'link')} have no action or destination, so "
                    "activating them does nothing.", no_target)
        else:
            out.ok("link-target")
        if no_contents:
            out.add("link-contents", "warning",
                    f"{len(no_contents)} of {_plural(len(links), 'link')} have no /Contents description. "
                    "PDF/UA asks each link to describe where it goes (e.g. 'Email billing@example.ca').",
                    no_contents)
        else:
            out.ok("link-contents")

    # ---- file size per page
    per_page = report.size / len(pages)
    report.stats["kb_per_page"] = round(per_page / 1024, 1)
    if report.size and per_page > max_kb_per_page * 1024:
        out.add("file-size", "warning",
                f"{per_page / 1024:,.0f} KB per page (limit {max_kb_per_page:g} KB). Large files are slow on "
                "mobile data; check image resolution and compression.")
    else:
        out.ok("file-size")

    # ---- metadata leaks
    values = [(_name(k), _text(v)) for k, v in info.items() if _text(v)]
    values += xmp.values
    leaks = _leaks(values)
    if leaks:
        out.add("metadata", "info",
                "Metadata may reveal internal details. This is not an accessibility problem, but anyone can "
                "read it in the document properties; remove what is not meant to be public.", leaks)
    else:
        out.ok("metadata")

    # ---- PDF/UA identifier (last: it looks at the other results)
    report.stats["pdfua_part"] = xmp.pdfua_part
    if not xmp.pdfua_part:
        out.add("pdfua-id", "info",
                "No PDF/UA identifier (pdfuaid:part) in the XMP metadata. Add it only after the file has been "
                "checked against PDF/UA: it is a claim of conformance.")
    else:
        errors = report.count("error")
        if errors:
            out.add("pdfua-id", "warning",
                    f"The file declares PDF/UA-{xmp.pdfua_part}, but these automated checks found "
                    f"{_plural(errors, 'error')}.")
        else:
            out.ok("pdfua-id")

    order = list(CHECKS)
    report.findings.sort(key=lambda f: (-RANK[f.severity], order.index(f.id)))


def _link_has_target(annot: dict, action) -> bool:
    if annot.get("/Dest") is not None:
        return True
    if not isinstance(action, dict):
        return False
    kind = _name(action.get("/S"))
    if kind == "URI":
        return bool(_text(_get(action, "/URI")))
    if kind in ("GoTo", "GoToR", "GoToE"):
        return action.get("/D") is not None
    return bool(kind)


def _structure_checks(tree_root: dict, report: Report, out: _Out, text_pages: int, page_num: dict) -> None:
    raw_map = _get(tree_root, "/RoleMap")
    rolemap = {_name(k): _name(v) for k, v in raw_map.items()} if isinstance(raw_map, dict) else {}
    st = _walk_struct(tree_root, rolemap)
    report.stats["roles"] = dict(st.roles.most_common())
    report.stats["marked_content_refs"] = st.mcids

    # figures
    figures = [e for e in st.elements if e["role"] == "Figure"]
    missing = []
    for e in figures:
        node = e["node"]
        if not (_text(node.get("/Alt")) or _text(node.get("/ActualText"))):
            pg = node.get("/Pg")
            n = page_num.get((pg.idnum, pg.generation)) if isinstance(pg, IndirectObject) else None
            missing.append(f"/{e['name']}" + (f" on page {n}" if n else ""))
    report.stats["figures"] = len(figures)
    report.stats["figures_with_alt"] = len(figures) - len(missing)
    if not figures:
        out.na("figure-alt", "no Figure tags")
    elif missing:
        out.add("figure-alt", "error",
                f"{len(missing)} of {_plural(len(figures), 'figure')} have no alternate text (/Alt). Screen "
                "readers skip them or read 'image'. Describe each meaningful image; mark decorative ones "
                "as artifacts instead.", missing)
    else:
        out.ok("figure-alt")

    # role mix (heuristic)
    roles = set(st.roles)
    problems = []
    if not st.elements:
        problems.append("the structure tree is empty")
    else:
        if roles <= GROUPING_TYPES:
            problems.append("only grouping tags (" + ", ".join(sorted(roles)) + "); nothing is tagged as a "
                            "paragraph, heading, list or table")
        if st.mcids == 0 and text_pages:
            problems.append("no tag points to page content (no marked-content references)")
    if problems:
        out.add("structure", "warning",
                "Heuristic: the tags may not describe the content: " + "; ".join(problems) + ".",
                ["role mix: " + ", ".join(f"{k} {v}" for k, v in st.roles.most_common(12))] if st.roles else [])
    else:
        out.ok("structure")

    # headings (heuristic)
    if not st.elements or text_pages == 0:
        out.na("headings", "no tagged text")
    elif roles & HEADING_TYPES:
        out.ok("headings")
    else:
        out.add("headings", "info",
                "Heuristic: no heading tags (H, H1-H6). Headings let screen reader users jump between "
                "sections; add them if the document has sections.")

    # tables
    tables = st.roles.get("Table", 0)
    if not tables:
        out.na("table-headers", "no Table tags")
    elif st.roles.get("TH", 0) == 0:
        out.add("table-headers", "warning",
                f"{_plural(tables, 'table')} but no header cells (TH). Screen readers cannot say which "
                "column a value belongs to. Tag the header row as TH (skip this for layout-only tables).")
    else:
        out.ok("table-headers")

    # role map
    issues = []
    for name, target in rolemap.items():
        if name in STANDARD_TYPES:
            issues.append(f"standard type /{name} is remapped to /{target}")
        else:
            _role, problem = _resolve_role(name, rolemap)
            if problem:
                issues.append(problem)
    for name, n in st.unknown.items():
        if name not in rolemap:
            issues.append(f"/{name} is used {_plural(n, 'time')} but is not a standard type and has no role map entry")
    if issues:
        out.add("role-map", "warning",
                "Custom tags that do not resolve to standard types: assistive technology cannot tell what "
                "they are.", sorted(set(issues)))
    elif not rolemap:
        out.na("role-map", "no role map")
    else:
        out.ok("role-map")


def _form_checks(root: dict, report: Report, out: _Out) -> None:
    acro = _get(root, "/AcroForm")
    fields_arr = _get(acro, "/Fields") if isinstance(acro, dict) else None
    terminal: list[tuple[str, str]] = []
    seen: set = set()

    def walk(arr, parent: str, depth: int):
        if not isinstance(arr, list) or depth > 30:
            return
        for raw in arr:
            f = _r(raw)
            if not isinstance(f, dict):
                continue
            k = _key(raw, f)
            if k in seen:
                continue
            seen.add(k)
            t = _text(f.get("/T"))
            full = f"{parent}.{t}" if parent and t else (t or parent or "(unnamed)")
            kids = _get(f, "/Kids")
            field_kids = [x for x in kids if isinstance(_r(x), dict) and "/T" in _r(x)] if isinstance(kids, list) else []
            if field_kids:
                walk(field_kids, full, depth + 1)
            else:
                terminal.append((full, _text(f.get("/TU"))))

    walk(fields_arr, "", 0)
    report.stats["form_fields"] = len(terminal)
    if not terminal:
        out.na("form-tooltips", "no form fields")
        return
    missing = [name for name, tu in terminal if not tu]
    if missing:
        out.add("form-tooltips", "warning",
                f"{len(missing)} of {_plural(len(terminal), 'form field')} have no tooltip (/TU). Screen "
                "readers use it as the field's name, so users hear only 'edit text'.", missing)
    else:
        out.ok("form-tooltips")
