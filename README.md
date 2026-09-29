# pdf-a11y-check

Automated **accessibility and quality checks** for the PDFs small businesses publish: invoices, menus, brochures, forms. One command, a plain-language report, and an exit code for CI.

```
pdf-a11y-check invoices/ menus/*.pdf --format markdown -o report.md
```

Each finding has an id, a severity (error, warning, info), a message that says what goes wrong for the reader, and a reference to WCAG 2.x, the WCAG PDF techniques (PDF1, PDF3, PDF16, PDF18...) or PDF/UA (ISO 14289-1).

- **Tags**: structure tree and `/MarkInfo /Marked true`; figures with `/Alt` or `/ActualText` (counted with and without); heading and table header tags; role map sanity; `/Tabs /S` on pages with links or fields.
- **Title and language**: Info `/Title` and XMP `dc:title`, titles that look like file names, `/DisplayDocTitle`, `/Lang` as a BCP 47 tag.
- **Real text**: pages where nothing can be extracted are reported as image-only (scanned) or "text drawn but not extractable".
- **Fonts**: embedded or not (including the descendant font of Type0 fonts; standard-14 fonts named as such), and fonts without a ToUnicode map.
- **Forms and links**: fields without a tooltip (`/TU`), links without an action or destination, links without a `/Contents` description.
- **Encryption**: tries the empty password and flags permissions that turn off extraction for accessibility (bit 10).
- **Quality**: file size per page, and metadata that exposes local paths (`C:\Users\...`, `/home/...`), login names, internal host names or software versions (info only: not an accessibility problem, but worth knowing before publishing).
- **PDF/UA identifier** (`pdfuaid:part`) in XMP, with a warning when a file claims PDF/UA and still has errors.

Only runtime dependency: [pypdf](https://github.com/py-pdf/pypdf) (BSD). Python 3.10+.

**This is a set of automated checks, not a PDF/UA conformance validation.** It does not check reading order against the visual layout, colour contrast, whether alt text is any good, or the hundreds of Matterhorn Protocol conditions that [PAC](https://pac.pdf-accessibility.org/) and [veraPDF](https://verapdf.org/) test. Use it to catch the common problems early and in CI; a manual review with a screen reader is still needed.

## Measured result

Three invoices made with my [invoice-pdf-canada](https://github.com/dreadmoreeee/invoice-pdf-canada) (invented customers, see [examples/make_demo_invoices.py](examples/make_demo_invoices.py)):

```
$ python -m pdf_a11y_check examples/demo-invoices/invoice-nb-en.pdf
examples/demo-invoices/invoice-nb-en.pdf
  1 page(s), 2,580 bytes, score 75/100
  ERROR    tagged             The PDF is not tagged (no structure tree). Screen readers have to guess the reading order and cannot tell headings, lists, tables or images apart. Export with 'tagged PDF' turned on, or add tags in a PDF editor.  [WCAG 1.3.1, WCAG 1.3.2, PDF/UA 7.1]
  WARNING  display-doc-title  /ViewerPreferences /DisplayDocTitle is not true, so viewers show the file name in the window title instead of the document title.  [WCAG 2.4.2, PDF18, PDF/UA 7.1]
  WARNING  fonts-embedded     Not embedded: 2 of 2 fonts (standard-14 fonts, which viewers are expected to supply). Viewers substitute a local font, so spacing and glyphs can differ between devices, and PDF/UA requires every font to be embedded.  [PDF/UA 7.21.4.1]
                              - Helvetica (standard 14)
                              - Helvetica-Bold (standard 14)
  INFO     title              Title 'Invoice TW-2026-0101' is set in the Info dictionary only; PDF/UA expects it in the XMP metadata (dc:title) as well.  [WCAG 2.4.2, PDF18, PDF/UA 7.1]
  INFO     pdfua-id           No PDF/UA identifier (pdfuaid:part) in the XMP metadata. Add it only after the file has been checked against PDF/UA: it is a claim of conformance.  [PDF/UA 5]
  passed: encryption, lang, text, fonts-unicode, file-size, metadata
  not applicable: figure-alt (not tagged), structure (not tagged), headings (not tagged), table-headers (not tagged), role-map (not tagged), tab-order (no annotations), form-tooltips (no form fields), link-target (no links), link-contents (no links)
  1 error(s), 2 warning(s), 2 info

Automated checks only: this is not a full PDF/UA conformance validation (use PAC or veraPDF for that) and a manual review is still needed.

$ python -m pdf_a11y_check examples/demo-invoices
...
3 file(s): 3 error(s), 6 warning(s), 6 info, average score 75/100

$ echo $?
1

$ python -m pytest -q
.................................................................
65 passed in 1.07s
```

What this says about the invoices: they already get the basics right (a title, `/Lang` set to `en-CA` or `fr-CA`, real extractable text, no metadata leaks, about 2.5 KB per page). What they lack is structure: they are not tagged, so a screen reader reads the text without knowing which part is the table of lines and which is the total. Setting `DisplayDocTitle` and an XMP title are small changes; tagging and embedding a font are the larger next steps for invoice-pdf-canada. The full reports are in [examples/demo-invoices/report.md](examples/demo-invoices/report.md) and [report.json](examples/demo-invoices/report.json).

The tests build small PDFs byte by byte (tagged and untagged, figures with and without alt text, form fields, links, a Type0 font, restrictive encryption written with pypdf, leaky metadata, a PDF/UA claim), and repeat the main cases with PDFs made by ReportLab when it is installed.


**What I fixed in invoice-pdf-canada after this run.** Two findings were cheap to fix, so I fixed them in the generator: it now sets `/DisplayDocTitle true` and writes the title into the XMP metadata as well. The PDFs in `examples/demo-invoices/` are the regenerated ones:

```
$ python -m pdf_a11y_check examples/demo-invoices/invoice-nb-en.pdf
  1 page(s), 3,211 bytes, score 80/100
  ERROR    tagged             The PDF is not tagged (no structure tree). ...
  WARNING  fonts-embedded     Not embedded: 2 of 2 fonts (standard-14 fonts, ...)
  INFO     pdfua-id           No PDF/UA identifier (pdfuaid:part) in the XMP metadata. ...
  passed: encryption, title, display-doc-title, lang, text, fonts-unicode, file-size, metadata
```

Score 75 -> 80. The two that remain need real work, and I left them as they are rather than hide them: a tagged structure tree (headings, table headers, reading order) and embedded fonts instead of the standard 14.

## Install

```bash
pip install git+https://github.com/dreadmoreeee/pdf-a11y-check
pdf-a11y-check brochure.pdf                 # or: python -m pdf_a11y_check brochure.pdf
```

For development: `pip install -e ".[dev]"` (pytest and ReportLab) then `python -m pytest -q`.

## CLI

```
pdf-a11y-check FILE|DIR|GLOB ... [--format text|markdown|json] [-o report.md]
               [--fail-on error|warning|info|never] [--max-kb-per-page 500]
               [--skip ID[,ID]] [--password PW] [--list-checks]
```

- Directories are searched recursively for `*.pdf`; globs like `site/**/*.pdf` work on every OS.
- Exit codes: **0** nothing at or above `--fail-on` (default `error`), **1** findings at or above it, **2** usage error or a file that could not be read (for example encrypted with an unknown password).
- Score: 100 minus 15 per error and 5 per warning, per file. It is a rough way to compare files and track progress, not a grade.
- `--list-checks` prints every check id with its references. [examples/github-actions-pdf-a11y.yml](examples/github-actions-pdf-a11y.yml) runs it in GitHub Actions and puts the Markdown report in the job summary.

```python
from pdf_a11y_check import check_pdf

report = check_pdf("menu.pdf")
report.score                       # 0-100
[(f.id, f.severity) for f in report.findings]
report.stats["figures_with_alt"], report.stats["figures"]
```

## Limitations

- The structure checks are heuristics: they look at which tags exist and whether they point to page content, not whether the order matches what a sighted reader sees.
- Alt text is checked for presence, not quality. Language changes inside the document (PDF19) are not checked.
- Only fonts that actually show text on a page are checked; fonts used only in form field appearances are not.
- AES-encrypted files need `cryptography` (or `pycryptodome`) installed for pypdf to open them; without it they are reported as unreadable (exit 2).

## Author

Marvin Palencia, founder of [DeMark Studio](https://demarkstudio.ca), Miramichi, New Brunswick, Canada. Portfolio: [marvin.demarkstudio.ca](https://marvin.demarkstudio.ca)

MIT License.
