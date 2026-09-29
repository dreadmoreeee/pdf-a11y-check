import json
import subprocess
import sys
from pathlib import Path

import pytest
from a11y_pdf_factory import make_clean_pdf, make_pdf

from pdf_a11y_check.cli import main

TOOL_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture
def files(tmp_path):
    good = tmp_path / "menus" / "clean.pdf"
    bad = tmp_path / "menus" / "untagged.PDF"
    good.parent.mkdir()
    good.write_bytes(make_clean_pdf())
    bad.write_bytes(make_pdf(title="Spring menu"))
    (tmp_path / "menus" / "notes.txt").write_text("not a pdf")
    return good, bad


def test_exit_0_on_clean_file(files, capsys):
    assert main([str(files[0])]) == 0
    out = capsys.readouterr().out
    assert "score 100/100" in out and "0 error(s), 0 warning(s), 0 info" in out
    assert "not a full PDF/UA conformance validation" in out


def test_exit_1_when_findings_reach_fail_on(files, capsys):
    assert main([str(files[1])]) == 1
    out = capsys.readouterr().out
    assert "ERROR    tagged" in out and "WCAG 1.3.1" in out
    assert main([str(files[1]), "--fail-on", "never"]) == 0
    capsys.readouterr()


def test_fail_on_levels(tmp_path, capsys):
    # only info findings: missing PDF/UA id
    f = tmp_path / "info-only.pdf"
    from a11y_pdf_factory import xmp_packet
    f.write_bytes(make_clean_pdf(xmp=xmp_packet(title="Invoice 1042 - Example Bakery")))
    assert main([str(f)]) == 0
    assert main([str(f), "--fail-on", "warning"]) == 0
    assert main([str(f), "--fail-on", "info"]) == 1
    capsys.readouterr()


def test_exit_2_for_unreadable_or_missing(tmp_path, files, capsys):
    junk = tmp_path / "junk.pdf"
    junk.write_bytes(b"%PDF-1.7 nothing here")
    assert main([str(junk)]) == 2
    assert "UNREADABLE" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.pdf")]) == 2
    assert main([str(files[0]), str(tmp_path / "missing.pdf")]) == 2  # unreadable wins over findings
    capsys.readouterr()


def test_usage_errors_exit_2(capsys):
    assert main([]) == 2
    assert main(["x.pdf", "--skip", "no-such-check"]) == 2
    with pytest.raises(SystemExit) as e:
        main(["--format", "xml", "x.pdf"])
    assert e.value.code == 2
    capsys.readouterr()


def test_directory_and_glob(files, capsys):
    folder = files[0].parent
    assert main([str(folder), "--fail-on", "never"]) == 0
    out = capsys.readouterr().out
    assert "clean.pdf" in out and "untagged.PDF" in out and "notes.txt" not in out
    assert "2 file(s):" in out
    assert main([str(folder / "*.pdf"), str(folder / "clean.pdf"), "--fail-on", "never"]) == 0
    out = capsys.readouterr().out
    assert out.count("clean.pdf") == 1  # duplicates removed


def test_json_output(files, capsys):
    assert main([str(files[0].parent), "--format", "json"]) == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["tool"] == "pdf-a11y-check"
    assert doc["summary"]["files"] == 2 and doc["summary"]["errors"] >= 2
    by_name = {Path(f["path"]).name: f for f in doc["files"]}
    assert by_name["clean.pdf"]["score"] == 100
    untagged = by_name["untagged.PDF"]
    tagged = next(f for f in untagged["findings"] if f["id"] == "tagged")
    assert tagged["severity"] == "error" and "PDF/UA 7.1" in tagged["refs"]
    assert untagged["not_applicable"]["figure-alt"] == "not tagged"


def test_markdown_output_to_file(files, tmp_path, capsys):
    out_file = tmp_path / "report.md"
    assert main([str(files[1]), "--format", "markdown", "-o", str(out_file)]) == 1
    assert capsys.readouterr().out == ""
    md = out_file.read_text(encoding="utf-8")
    assert md.startswith("# PDF accessibility report")
    assert "| File | Pages | Score | Errors | Warnings | Info |" in md
    assert "| error | `tagged` |" in md
    assert "- `fonts-embedded`: Helvetica (standard 14)" in md
    assert "manual review is still needed" in md


def test_skip_and_max_kb(files, capsys):
    main([str(files[0]), "--max-kb-per-page", "1", "--format", "json"])
    doc = json.loads(capsys.readouterr().out)
    assert any(f["id"] == "file-size" for f in doc["files"][0]["findings"])
    main([str(files[1]), "--skip", "tagged,lang", "--skip", "title", "--format", "json"])
    found = {f["id"] for f in json.loads(capsys.readouterr().out)["files"][0]["findings"]}
    assert not found & {"tagged", "lang", "title"}


def test_list_checks(capsys):
    assert main(["--list-checks"]) == 0
    out = capsys.readouterr().out
    assert "figure-alt" in out and "PDF1" in out and "metadata" in out


def test_module_entry_point(files):
    p = subprocess.run([sys.executable, "-m", "pdf_a11y_check", str(files[0])], cwd=TOOL_DIR,
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert "score 100/100" in p.stdout


def test_sources_are_ascii():
    for path in list((TOOL_DIR / "pdf_a11y_check").glob("*.py")) + list((TOOL_DIR / "tests").glob("*.py")):
        path.read_bytes().decode("ascii")
