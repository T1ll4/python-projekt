"""A Streamlit felület füstteszte (streamlit.testing.AppTest)."""

from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders(tmp_path, monkeypatch):
    monkeypatch.setenv("MF_TEMPLATE_DIR", str(tmp_path / "ut"))
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    assert not at.exception
    assert any("Journal Figure Formatter" in t.value for t in at.title)
    assert len(at.tabs) >= 3


def test_app_saves_new_template(tmp_path, monkeypatch):
    monkeypatch.setenv("MF_TEMPLATE_DIR", str(tmp_path / "ut"))
    at = st_testing.AppTest.from_file(APP, default_timeout=60)
    at.run()
    at.text_input(key="tpl___new___id").set_value("teszt_folyoirat")
    at.text_input(key="tpl___new___name").set_value("Teszt Folyóirat")
    at.number_input(key="tpl___new___figure_dpi").set_value(600)
    at.button(key="FormSubmitter:form___new__-💾 Mentés").click()
    at.run()
    assert not at.exception
    assert any("Sablon mentve" in s.value for s in at.success)
    assert (tmp_path / "ut" / "teszt_folyoirat.json").is_file()
