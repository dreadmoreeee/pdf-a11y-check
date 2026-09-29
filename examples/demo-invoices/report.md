# PDF accessibility report

| File | Pages | Score | Errors | Warnings | Info |
|---|---:|---:|---:|---:|---:|
| examples/demo-invoices/invoice-nb-en.pdf | 1 | 75/100 | 1 | 2 | 2 |
| examples/demo-invoices/invoice-on-en.pdf | 1 | 75/100 | 1 | 2 | 2 |
| examples/demo-invoices/invoice-qc-fr.pdf | 1 | 75/100 | 1 | 2 | 2 |

## examples/demo-invoices/invoice-nb-en.pdf

| Severity | Check | Finding | Reference |
|---|---|---|---|
| error | `tagged` | The PDF is not tagged (no structure tree). Screen readers have to guess the reading order and cannot tell headings, lists, tables or images apart. Export with 'tagged PDF' turned on, or add tags in a PDF editor. | WCAG 1.3.1, WCAG 1.3.2, PDF/UA 7.1 |
| warning | `display-doc-title` | /ViewerPreferences /DisplayDocTitle is not true, so viewers show the file name in the window title instead of the document title. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| warning | `fonts-embedded` | Not embedded: 2 of 2 fonts (standard-14 fonts, which viewers are expected to supply). Viewers substitute a local font, so spacing and glyphs can differ between devices, and PDF/UA requires every font to be embedded. | PDF/UA 7.21.4.1 |
| info | `title` | Title 'Invoice TW-2026-0101' is set in the Info dictionary only; PDF/UA expects it in the XMP metadata (dc:title) as well. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| info | `pdfua-id` | No PDF/UA identifier (pdfuaid:part) in the XMP metadata. Add it only after the file has been checked against PDF/UA: it is a claim of conformance. | PDF/UA 5 |

Details:

- `fonts-embedded`: Helvetica (standard 14); Helvetica-Bold (standard 14)

Passed: `encryption`, `lang`, `text`, `fonts-unicode`, `file-size`, `metadata`

Not applicable: `figure-alt` (not tagged), `structure` (not tagged), `headings` (not tagged), `table-headers` (not tagged), `role-map` (not tagged), `tab-order` (no annotations), `form-tooltips` (no form fields), `link-target` (no links), `link-contents` (no links)

## examples/demo-invoices/invoice-on-en.pdf

| Severity | Check | Finding | Reference |
|---|---|---|---|
| error | `tagged` | The PDF is not tagged (no structure tree). Screen readers have to guess the reading order and cannot tell headings, lists, tables or images apart. Export with 'tagged PDF' turned on, or add tags in a PDF editor. | WCAG 1.3.1, WCAG 1.3.2, PDF/UA 7.1 |
| warning | `display-doc-title` | /ViewerPreferences /DisplayDocTitle is not true, so viewers show the file name in the window title instead of the document title. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| warning | `fonts-embedded` | Not embedded: 2 of 2 fonts (standard-14 fonts, which viewers are expected to supply). Viewers substitute a local font, so spacing and glyphs can differ between devices, and PDF/UA requires every font to be embedded. | PDF/UA 7.21.4.1 |
| info | `title` | Title 'Invoice TW-2026-0103' is set in the Info dictionary only; PDF/UA expects it in the XMP metadata (dc:title) as well. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| info | `pdfua-id` | No PDF/UA identifier (pdfuaid:part) in the XMP metadata. Add it only after the file has been checked against PDF/UA: it is a claim of conformance. | PDF/UA 5 |

Details:

- `fonts-embedded`: Helvetica (standard 14); Helvetica-Bold (standard 14)

Passed: `encryption`, `lang`, `text`, `fonts-unicode`, `file-size`, `metadata`

Not applicable: `figure-alt` (not tagged), `structure` (not tagged), `headings` (not tagged), `table-headers` (not tagged), `role-map` (not tagged), `tab-order` (no annotations), `form-tooltips` (no form fields), `link-target` (no links), `link-contents` (no links)

## examples/demo-invoices/invoice-qc-fr.pdf

| Severity | Check | Finding | Reference |
|---|---|---|---|
| error | `tagged` | The PDF is not tagged (no structure tree). Screen readers have to guess the reading order and cannot tell headings, lists, tables or images apart. Export with 'tagged PDF' turned on, or add tags in a PDF editor. | WCAG 1.3.1, WCAG 1.3.2, PDF/UA 7.1 |
| warning | `display-doc-title` | /ViewerPreferences /DisplayDocTitle is not true, so viewers show the file name in the window title instead of the document title. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| warning | `fonts-embedded` | Not embedded: 2 of 2 fonts (standard-14 fonts, which viewers are expected to supply). Viewers substitute a local font, so spacing and glyphs can differ between devices, and PDF/UA requires every font to be embedded. | PDF/UA 7.21.4.1 |
| info | `title` | Title 'Facture TW-2026-0102' is set in the Info dictionary only; PDF/UA expects it in the XMP metadata (dc:title) as well. | WCAG 2.4.2, PDF18, PDF/UA 7.1 |
| info | `pdfua-id` | No PDF/UA identifier (pdfuaid:part) in the XMP metadata. Add it only after the file has been checked against PDF/UA: it is a claim of conformance. | PDF/UA 5 |

Details:

- `fonts-embedded`: Helvetica (standard 14); Helvetica-Bold (standard 14)

Passed: `encryption`, `lang`, `text`, `fonts-unicode`, `file-size`, `metadata`

Not applicable: `figure-alt` (not tagged), `structure` (not tagged), `headings` (not tagged), `table-headers` (not tagged), `role-map` (not tagged), `tab-order` (no annotations), `form-tooltips` (no form fields), `link-target` (no links), `link-contents` (no links)

> Automated checks only: this is not a full PDF/UA conformance validation (use PAC or veraPDF for that) and a manual review is still needed.
