import zipfile

from manuscript_formatter.cli import main


def test_cli_process(samples, tmp_path, capsys):
    out = tmp_path / "out.zip"
    xlsx = tmp_path / "t.xlsx"
    tex = tmp_path / "tex"
    rc = main(["--template-dir", str(tmp_path / "ut"), "process", str(samples["docx"]),
               "-t", "ieee", "-o", str(out), "--excel", str(xlsx), "--latex", str(tex)])
    assert rc == 0
    assert zipfile.is_zipfile(out) and xlsx.stat().st_size > 0
    assert (tex / "main.tex").is_file()
    assert "IEEE" in capsys.readouterr().out


def test_cli_templates(tmp_path, capsys):
    ut = str(tmp_path / "ut")
    assert main(["--template-dir", ut, "templates", "list"]) == 0
    assert "elsevier" in capsys.readouterr().out
    exported = tmp_path / "e.json"
    assert main(["--template-dir", ut, "templates", "export", "elsevier", "-o", str(exported)]) == 0
    exported.write_text(exported.read_text(encoding="utf-8").replace('"elsevier"', '"mine"', 1),
                        encoding="utf-8")
    assert main(["--template-dir", ut, "templates", "import", str(exported)]) == 0
    assert main(["--template-dir", ut, "templates", "delete", "mine"]) == 0
    assert main(["--template-dir", ut, "templates", "show", "nope"]) == 1
    assert main(["--template-dir", ut, "process", "missing.docx", "-t", "elsevier"]) == 2
