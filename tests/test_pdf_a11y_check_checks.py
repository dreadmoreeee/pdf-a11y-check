import io

import pytest
from a11y_pdf_factory import make_clean_pdf, make_pdf, xmp_packet
from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions as Perm

from pdf_a11y_check import CHECKS, check_pdf
from pdf_a11y_check.checks import LANG_RE, _fonts_showing_text


def ids(report, severity=None):
    return {f.id for f in report.findings if severity is None or f.severity == severity}


def test_clean_document_passes_everything():
    r = check_pdf(make_clean_pdf(), name="clean.pdf")
    assert r.error is None
    assert r.findings == []
    assert r.score == 100
    assert {"tagged", "title", "display-doc-title", "lang", "text", "fonts-embedded", "structure",
            "headings", "pdfua-id", "metadata", "encryption"} <= set(r.passed)
    assert r.stats["tagged"] is True and r.stats["pdfua_part"] == "1"


def test_untagged_minimal_pdf():
    r = check_pdf(make_pdf())
    assert {"tagged", "title", "lang"} <= ids(r, "error")
    assert "display-doc-title" in ids(r, "warning")
    assert r.stats["tagged"] is False
    for cid in ("figure-alt", "structure", "headings", "table-headers", "role-map"):
        assert r.not_applicable[cid] == "not tagged"
    assert r.score == 100 - 3 * 15 - 2 * 5  # display-doc-title and fonts-embedded warnings


def test_untagged_with_images_mentions_alt_text():
    r = check_pdf(make_pdf(image_pages=[1]))
    assert "cannot carry alternate text" in r.finding("tagged").message


def test_structure_tree_without_marked_true():
    r = check_pdf(make_clean_pdf(marked=False))
    f = r.finding("tagged")
    assert f.severity == "warning" and "/Marked" in f.message


def test_title_missing_filename_like_and_info_only():
    assert check_pdf(make_clean_pdf(title=None, xmp=xmp_packet(pdfua="1"))).finding("title").severity == "error"
    r = check_pdf(make_clean_pdf(title="Microsoft Word - invoice_final.docx"))
    assert r.finding("title").severity == "warning"
    r = check_pdf(make_clean_pdf(title="Spring menu", xmp=xmp_packet(pdfua="1")))
    assert r.finding("title").severity == "info" and "dc:title" in r.finding("title").message
    # title only in XMP is accepted
    assert "title" in check_pdf(make_clean_pdf(title=None)).passed


def test_display_doc_title():
    assert "display-doc-title" in ids(check_pdf(make_clean_pdf(display_doc_title=False)), "warning")
    assert "display-doc-title" in check_pdf(make_clean_pdf()).passed


def test_lang_missing_and_invalid():
    assert check_pdf(make_clean_pdf(lang=None)).finding("lang").severity == "error"
    r = check_pdf(make_clean_pdf(lang="en_US"))
    assert r.finding("lang").severity == "warning"


@pytest.mark.parametrize("tag", ["en", "en-CA", "fr-CA", "zh-Hant-TW", "es-419", "sr-Latn", "x-private",
                                 "de-DE-1996"])
def test_lang_regex_accepts(tag):
    assert LANG_RE.match(tag)


@pytest.mark.parametrize("tag", ["en_US", "english language", "e", "en-", "123"])
def test_lang_regex_rejects(tag):
    assert not LANG_RE.match(tag)


def test_image_only_page_is_an_error():
    r = check_pdf(make_pdf(text=None, image_pages=[1]))
    f = r.finding("text")
    assert f.severity == "error"
    assert f.details == ["page 1: image only, looks scanned"]
    assert r.stats["text_pages"] == 0
    # Helvetica is listed in the page resources but never used, so it is not reported
    assert r.not_applicable["fonts-embedded"] == "no fonts"


def test_some_pages_without_text_is_a_warning():
    r = check_pdf(make_pdf(pages=3, text_pages=[1, 3], image_pages=[2]))
    f = r.finding("text")
    assert f.severity == "warning"
    assert f.message.startswith("1 of 3 pages")
    assert f.details == ["page 2: image only, looks scanned"]


def test_blank_page_is_reported_as_such():
    r = check_pdf(make_pdf(pages=2, text_pages=[1]))
    assert r.finding("text").details == ["page 2: no text or images"]


def test_standard_14_font_not_embedded():
    r = check_pdf(make_pdf(font="standard"))
    f = r.finding("fonts-embedded")
    assert f.severity == "warning"
    assert f.details == ["Helvetica (standard 14)"]
    assert "standard-14" in f.message


def test_only_fonts_that_show_text_count():
    content = b"BT /F1 12 Tf 14.4 TL ET\nBT /F2+0 14 Tf (Hello) Tj ET\nBT /F3 9 Tf [(A) 20 (B)] TJ ET"
    assert _fonts_showing_text(content) == {b"F2+0", b"F3"}


def test_embedded_font_passes():
    r = check_pdf(make_pdf(font="embedded"))
    assert "fonts-embedded" in r.passed and "fonts-unicode" in r.passed


def test_type0_font_embedded_via_descendant_but_no_tounicode():
    r = check_pdf(make_pdf(font="type0"))
    assert "fonts-embedded" in r.passed  # FontFile2 found through DescendantFonts
    f = r.finding("fonts-unicode")
    assert f.severity == "warning" and f.details == ["ExampleCID (Type0)"]


def test_figures_with_and_without_alt():
    r = check_pdf(make_clean_pdf(figures=[None, "Map of the store location", ("actual", "Logo: Example Bakery")]))
    f = r.finding("figure-alt")
    assert f.severity == "error"
    assert f.message.startswith("1 of 3 figures")
    assert f.details == ["/Figure on page 1"]
    assert r.stats["figures"] == 3 and r.stats["figures_with_alt"] == 2
    # a PDF/UA claim with errors is called out
    assert r.finding("pdfua-id").severity == "warning"


def test_figures_all_with_alt_pass():
    r = check_pdf(make_clean_pdf(figures=["Photo of the dining room"]))
    assert "figure-alt" in r.passed
    assert r.findings == []


def test_structure_with_only_grouping_tags():
    r = check_pdf(make_clean_pdf(struct_roles=("Div", "Span")))
    f = r.finding("structure")
    assert f.severity == "warning" and "Heuristic" in f.message and "only grouping tags" in f.message
    assert r.not_applicable.get("headings") is None
    assert r.finding("headings").severity == "info"


def test_structure_without_content_references():
    r = check_pdf(make_clean_pdf(mcid_refs=False))
    f = r.finding("structure")
    assert f.severity == "warning" and "no tag points to page content" in f.message
    assert r.stats["marked_content_refs"] == 0


def test_table_without_header_cells():
    r = check_pdf(make_clean_pdf(struct_roles=("P", "H1", "Table", "TR", "TD", "TD")))
    assert r.finding("table-headers").severity == "warning"
    r = check_pdf(make_clean_pdf(struct_roles=("P", "H1", "Table", "TR", "TH", "TD")))
    assert "table-headers" in r.passed


def test_role_map_resolves_custom_tags():
    r = check_pdf(make_clean_pdf(struct_roles=("Para", "Heading1"), rolemap={"Para": "P", "Heading1": "H1"}))
    assert "role-map" in r.passed and "headings" in r.passed
    assert r.stats["roles"]["P"] == 1


def test_role_map_problems():
    r = check_pdf(make_clean_pdf(struct_roles=("P", "H1", "Fancy", "Loop", "Odd"),
                                 rolemap={"Fancy": "Weird", "Loop": "Loop2", "Loop2": "Loop", "P": "Span"}))
    details = " | ".join(r.finding("role-map").details)
    assert "/Fancy maps to /Weird" in details
    assert "circular role mapping" in details
    assert "standard type /P is remapped" in details
    assert "/Odd is used 1 time" in details


def test_form_fields_tooltips_and_tab_order():
    r = check_pdf(make_clean_pdf(fields=[("name", "Your full name"), ("email", None)]))
    f = r.finding("form-tooltips")
    assert f.severity == "warning" and f.details == ["email"]
    assert r.stats["form_fields"] == 2
    assert r.finding("tab-order").severity == "warning"
    r = check_pdf(make_clean_pdf(fields=[("name", "Your full name")], tabs="S"))
    assert "form-tooltips" in r.passed and "tab-order" in r.passed


def test_links():
    r = check_pdf(make_clean_pdf(tabs="S", links=[
        {"uri": "https://example.ca/menu", "contents": "Full menu on example.ca"},
        {"uri": "mailto:orders@example.ca"},
        {"contents": "Broken link"},
    ]))
    target = r.finding("link-target")
    assert target.details == ["page 1"] and target.message.startswith("1 of 3 links")
    contents = r.finding("link-contents")
    assert contents.details == ["page 1: mailto:orders@example.ca"]
    r = check_pdf(make_clean_pdf(tabs="S", links=[{"dest": True, "contents": "Go to page 1"}]))
    assert {"link-target", "link-contents"} <= set(r.passed)


def _encrypt(data: bytes, permissions: int, user_password: str = "") -> bytes:
    w = PdfWriter(clone_from=PdfReader(io.BytesIO(data)))
    w.encrypt(user_password=user_password, owner_password="owner-secret", permissions_flag=permissions,
              algorithm="RC4-128")
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def test_encrypted_restrictive_permissions_block_assistive_tech():
    data = _encrypt(make_clean_pdf(), Perm.PRINT)
    r = check_pdf(data)
    assert r.error is None
    f = r.finding("encryption")
    assert f.severity == "error" and "bit 10" in f.message
    assert r.stats["permissions"]["accessibility_extraction"] is False
    assert r.stats["encrypted"] is True


def test_encrypted_copy_off_but_accessibility_on():
    r = check_pdf(_encrypt(make_clean_pdf(), Perm.PRINT | Perm.EXTRACT_TEXT_AND_GRAPHICS))
    f = r.finding("encryption")
    assert f.severity == "info" and "copying is turned off" in f.message


def test_encrypted_without_restrictions_is_info():
    r = check_pdf(_encrypt(make_clean_pdf(), Perm.all()))
    assert r.finding("encryption").severity == "info"


def test_encrypted_with_user_password():
    data = _encrypt(make_clean_pdf(), Perm.all(), user_password="open-me")
    r = check_pdf(data)
    assert r.error and "password" in r.error and r.score == 0
    r = check_pdf(data, password="wrong")
    assert "did not work" in r.error
    r = check_pdf(data, password="open-me")
    assert r.error is None and r.finding("encryption").severity == "info"


def test_metadata_leaks_are_info():
    r = check_pdf(make_clean_pdf(
        info={"Author": "jsmith", "Creator": r"C:\Users\jsmith\Documents\menu-final.docx",
              "Producer": "Example PDF Library 9.1.2"},
        xmp=xmp_packet(title="Spring menu", pdfua="1", creator_tool="Designer 5.0 on build01.corp",
                       extra="<dc:source>/home/jsmith/menus/spring.indd</dc:source>")))
    f = r.finding("metadata")
    assert f.severity == "info"
    text = "\n".join(f.details)
    assert "C:\\Users\\jsmith\\Documents\\menu-final.docx' (local Windows path)" in text
    assert "Author: 'jsmith' (looks like a login name)" in text
    assert "Producer: 'Example PDF Library 9.1.2' (software name and version)" in text
    assert "build01.corp' (internal host name)" in text
    assert "XMP source: '/home/jsmith/menus/spring.indd' (local home folder path)" in text
    # info findings do not lower the score
    assert r.score == 100


def test_normal_metadata_is_not_flagged():
    r = check_pdf(make_clean_pdf(info={"Author": "Example Bakery Ltd.", "Subject": "Menu, version 2 (2026)",
                                       "Keywords": "https://example.ca/menu"}))
    assert "metadata" in r.passed


def test_pdfua_identifier_missing_is_info():
    r = check_pdf(make_clean_pdf(xmp=xmp_packet(title="Invoice 1042 - Example Bakery")))
    assert r.finding("pdfua-id").severity == "info"


def test_pdfua_identifier_as_attribute():
    xmp = xmp_packet(title="Invoice").replace("rdf:about=\"\"", "rdf:about=\"\" pdfuaid:part=\"1\"")
    assert check_pdf(make_clean_pdf(xmp=xmp)).stats["pdfua_part"] == "1"


def test_xmp_with_entities_is_ignored_safely():
    xmp = "<?xml version=\"1.0\"?><!DOCTYPE x [<!ENTITY a \"aaaa\">]><x>&a;</x>"
    r = check_pdf(make_clean_pdf(xmp=xmp))
    assert r.error is None and "xmp_error" in r.stats


def test_file_size_threshold():
    data = make_clean_pdf()
    assert "file-size" in check_pdf(data).passed
    f = check_pdf(data, max_kb_per_page=1).finding("file-size")
    assert f.severity == "warning" and "limit 1 KB" in f.message


def test_skip_removes_checks():
    r = check_pdf(make_pdf(), skip=["tagged", "lang"])
    assert "tagged" not in ids(r) and "lang" not in ids(r)


def test_unreadable_input():
    r = check_pdf(b"this is not a pdf", name="junk.pdf")
    assert r.error and r.score == 0
    r = check_pdf("does-not-exist.pdf")
    assert "cannot read file" in r.error


def test_every_check_has_refs_or_is_quality():
    for c in CHECKS.values():
        assert c.severity in ("error", "warning", "info")
        assert c.refs or c.id in ("file-size", "metadata")
