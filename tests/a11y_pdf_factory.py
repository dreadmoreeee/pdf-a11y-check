"""Build small PDFs byte by byte (with a correct xref table) for the tests.

No third-party library is needed, so the core tests always run.
"""
from __future__ import annotations

import re


class PdfBuilder:
    def __init__(self):
        self.objs: dict[int, bytes] = {}
        self.next = 1

    def reserve(self) -> int:
        n = self.next
        self.next += 1
        return n

    def set(self, num: int, body) -> int:
        self.objs[num] = body.encode("latin-1") if isinstance(body, str) else body
        return num

    def add(self, body) -> int:
        return self.set(self.reserve(), body)

    def add_stream(self, data: bytes, extra: str = "") -> int:
        head = f"<< /Length {len(data)} {extra} >>\nstream\n".encode("latin-1")
        return self.add(head + data + b"\nendstream")

    def build(self, root: int, info: int | None = None) -> bytes:
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        size = self.next
        offsets = {}
        for n in range(1, size):
            if n in self.objs:
                offsets[n] = len(out)
                out += f"{n} 0 obj\n".encode() + self.objs[n] + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {size}\n".encode()
        out += b"0000000000 65535 f \n"
        for n in range(1, size):
            out += (f"{offsets[n]:010d} 00000 n \n" if n in offsets else "0000000000 00000 f \n").encode()
        trailer = f"/Size {size} /Root {root} 0 R" + (f" /Info {info} 0 R" if info else "")
        out += f"trailer\n<< {trailer} >>\nstartxref\n{xref}\n%%EOF\n".encode()
        return bytes(out)


def pdf_str(s: str) -> str:
    """A PDF literal string (ASCII only in these tests)."""
    return "(" + re.sub(r"([\\()])", r"\\\1", s) + ")"


DEFAULT_TEXT = "Invoice 1042 for Example Bakery, total 115.00 CAD"


def xmp_packet(title: str | None = None, pdfua: str | None = None, creator_tool: str | None = None,
               extra: str = "") -> str:
    parts = []
    if title:
        parts.append(f"<dc:title><rdf:Alt><rdf:li xml:lang=\"x-default\">{title}</rdf:li></rdf:Alt></dc:title>")
    if pdfua:
        parts.append(f"<pdfuaid:part>{pdfua}</pdfuaid:part>")
    if creator_tool:
        parts.append(f"<xmp:CreatorTool>{creator_tool}</xmp:CreatorTool>")
    parts.append(extra)
    return ("<?xpacket begin=\"\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n"
            "<x:xmpmeta xmlns:x=\"adobe:ns:meta/\"><rdf:RDF xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\">"
            "<rdf:Description rdf:about=\"\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
            "xmlns:pdfuaid=\"http://www.aiim.org/pdfua/ns/id/\" xmlns:xmp=\"http://ns.adobe.com/xap/1.0/\">"
            + "".join(parts)
            + "</rdf:Description></rdf:RDF></x:xmpmeta>\n<?xpacket end=\"w\"?>")


def make_pdf(*, pages: int = 1, text: str | None = DEFAULT_TEXT, image_pages=(), font: str = "standard",
             tagged: bool = False, marked: bool | None = None, struct_roles=("H1", "P"),
             figures=(), rolemap: dict | None = None, title: str | None = None,
             display_doc_title: bool = False, lang: str | None = None, xmp: str | None = None,
             info: dict | None = None, fields=(), links=(), tabs: str | None = None,
             text_pages=None, mcid_refs: bool = True) -> bytes:
    """Return the bytes of a small PDF.

    font: "standard" (Helvetica, not embedded), "embedded" (TrueType with FontFile2)
          or "type0" (Identity-H CID font, embedded, no ToUnicode).
    figures: one entry per Figure tag: None (no alt), a string (Alt), or ("actual", text).
    fields: (name, tooltip or None) pairs. links: dicts with optional "uri" and "contents".
    image_pages / text_pages: 1-based page numbers with an image / with text (default: all have text).
    """
    b = PdfBuilder()
    catalog, pages_id = b.reserve(), b.reserve()
    page_ids = [b.reserve() for _ in range(pages)]
    text_pages = set(range(1, pages + 1)) if text_pages is None else set(text_pages)

    if font == "standard":
        font_id = b.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    elif font == "embedded":
        ff = b.add_stream(b"\x00\x01\x00\x00fake-truetype-program", "/Length1 26")
        fd = b.add(f"<< /Type /FontDescriptor /FontName /ABCDEF+ExampleSans /Flags 32 /FontBBox [0 0 1000 1000] "
                   f"/ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 /FontFile2 {ff} 0 R >>")
        font_id = b.add(f"<< /Type /Font /Subtype /TrueType /BaseFont /ABCDEF+ExampleSans /FirstChar 32 "
                        f"/LastChar 126 /Widths [{' '.join(['500'] * 95)}] /Encoding /WinAnsiEncoding "
                        f"/FontDescriptor {fd} 0 R >>")
    elif font == "type0":
        ff = b.add_stream(b"\x00\x01\x00\x00fake-truetype-program", "/Length1 26")
        fd = b.add(f"<< /Type /FontDescriptor /FontName /ExampleCID /Flags 4 /FontBBox [0 0 1000 1000] "
                   f"/ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 /FontFile2 {ff} 0 R >>")
        cid = b.add(f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /ExampleCID /CIDSystemInfo "
                    f"<< /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> /FontDescriptor {fd} 0 R "
                    f"/DW 500 /CIDToGIDMap /Identity >>")
        font_id = b.add(f"<< /Type /Font /Subtype /Type0 /BaseFont /ExampleCID /Encoding /Identity-H "
                        f"/DescendantFonts [{cid} 0 R] >>")
    else:
        raise ValueError(font)

    image_id = b.add_stream(b"\x80", "/Type /XObject /Subtype /Image /Width 1 /Height 1 "
                                     "/ColorSpace /DeviceGray /BitsPerComponent 8") if image_pages or figures else None

    # structure elements are created later; reserve their ids now
    struct_root = b.reserve() if tagged else None

    # annotations (all on page 1)
    annot_ids, field_ids = [], []
    for name, tu in fields:
        tu_part = f" /TU {pdf_str(tu)}" if tu else ""
        fid = b.add(f"<< /Type /Annot /Subtype /Widget /FT /Tx /T {pdf_str(name)}{tu_part} "
                    f"/Rect [72 400 272 420] /P {page_ids[0]} 0 R /F 4 >>")
        field_ids.append(fid)
        annot_ids.append(fid)
    for link in links:
        parts = ["/Type /Annot /Subtype /Link /Rect [72 300 272 320] /Border [0 0 0]"]
        if link.get("uri"):
            parts.append(f"/A << /S /URI /URI {pdf_str(link['uri'])} >>")
        if link.get("dest"):
            parts.append(f"/Dest [{page_ids[0]} 0 R /Fit]")
        if link.get("contents"):
            parts.append(f"/Contents {pdf_str(link['contents'])}")
        annot_ids.append(b.add("<< " + " ".join(parts) + " >>"))

    mcid_counter = {}
    for i, pid in enumerate(page_ids, 1):
        ops = []
        mcid = 0
        if i in text_pages and text:
            if font == "type0":
                show = "<" + "".join(f"{ord(c):04X}" for c in text) + "> Tj"
            else:
                show = f"{pdf_str(text)} Tj"
            body = f"BT /F1 12 Tf 72 720 Td {show} ET"
            ops.append(f"/P <</MCID {mcid}>> BDC {body} EMC" if tagged else body)
            mcid += 1
        if i in image_pages:
            ops.append("q 200 0 0 200 72 400 cm /Im1 Do Q")
        if i == 1 and tagged:
            for _ in figures:
                ops.append(f"/Figure <</MCID {mcid}>> BDC q 50 0 0 50 300 400 cm /Im1 Do Q EMC")
                mcid += 1
        mcid_counter[i] = mcid
        content = b.add_stream("\n".join(ops).encode("latin-1"))
        xobj = f" /XObject << /Im1 {image_id} 0 R >>" if image_id else ""
        annots = f" /Annots [{' '.join(f'{a} 0 R' for a in annot_ids)}]" if i == 1 and annot_ids else ""
        tabs_part = f" /Tabs /{tabs}" if tabs and i == 1 else ""
        b.set(pid, f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                   f"/Resources << /Font << /F1 {font_id} 0 R >>{xobj} >> /Contents {content} 0 R"
                   f"{annots}{tabs_part} >>")
    b.set(pages_id, f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {pages} >>")

    cat = [f"/Type /Catalog /Pages {pages_id} 0 R"]
    if tagged:
        doc_elem = b.reserve()
        kids = []
        # the first role gets the page 1 text (MCID 0); other roles are empty containers
        for n, role in enumerate(struct_roles):
            k = f" /K 0 /Pg {page_ids[0]} 0 R" if n == 0 and text and 1 in text_pages and mcid_refs else ""
            kids.append(b.add(f"<< /Type /StructElem /S /{role} /P {doc_elem} 0 R{k} >>"))
        first_fig_mcid = 1 if text and 1 in text_pages else 0
        for n, fig in enumerate(figures):
            alt = ""
            if isinstance(fig, tuple):
                alt = f" /ActualText {pdf_str(fig[1])}"
            elif fig:
                alt = f" /Alt {pdf_str(fig)}"
            kids.append(b.add(f"<< /Type /StructElem /S /Figure /P {doc_elem} 0 R /Pg {page_ids[0]} 0 R "
                              f"/K {first_fig_mcid + n}{alt} >>"))
        b.set(doc_elem, f"<< /Type /StructElem /S /Document /P {struct_root} 0 R "
                        f"/K [{' '.join(f'{k} 0 R' for k in kids)}] >>")
        rm = ""
        if rolemap:
            rm = " /RoleMap << " + " ".join(f"/{k} /{v}" for k, v in rolemap.items()) + " >>"
        b.set(struct_root, f"<< /Type /StructTreeRoot /K {doc_elem} 0 R{rm} >>")
        cat.append(f"/StructTreeRoot {struct_root} 0 R")
    if marked if marked is not None else tagged:
        cat.append("/MarkInfo << /Marked true >>")
    if display_doc_title:
        cat.append("/ViewerPreferences << /DisplayDocTitle true >>")
    if lang:
        cat.append(f"/Lang {pdf_str(lang)}")
    if xmp:
        data = xmp.encode("utf-8")
        cat.append(f"/Metadata {b.add_stream(data, '/Type /Metadata /Subtype /XML')} 0 R")
    if field_ids:
        cat.append(f"/AcroForm << /Fields [{' '.join(f'{f} 0 R' for f in field_ids)}] >>")
    b.set(catalog, "<< " + " ".join(cat) + " >>")

    info_items = dict(info or {})
    if title:
        info_items["Title"] = title
    info_id = b.add("<< " + " ".join(f"/{k} {pdf_str(v)}" for k, v in info_items.items()) + " >>") \
        if info_items else None
    return b.build(catalog, info_id)


def make_clean_pdf(**overrides) -> bytes:
    """A small document that passes every check."""
    opts = dict(tagged=True, font="embedded", title="Invoice 1042 - Example Bakery",
                xmp=xmp_packet(title="Invoice 1042 - Example Bakery", pdfua="1"),
                display_doc_title=True, lang="en-CA", struct_roles=("P", "H1"))
    opts.update(overrides)
    return make_pdf(**opts)
