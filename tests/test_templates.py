import json

import pytest

from manuscript_formatter.templates import JournalTemplate, TemplateError, TemplateStore


def test_builtin_templates_load(store):
    ids = store.ids()
    for expected in ("elsevier", "springer_nature", "ieee", "plos_one", "acs"):
        assert expected in ids
    assert all(t.builtin for t in store.list_all())


def test_roundtrip_and_save(store):
    tpl = store.get("elsevier")
    data = tpl.to_dict()
    data["id"] = "my_journal"
    data["name"] = "My Journal"
    data["figure"]["dpi"] = 600
    data["figure"]["color_mode"] = "CMYK"
    store.save(JournalTemplate.from_dict(data))
    loaded = store.get("my_journal")
    assert loaded.figure.dpi == 600 and loaded.figure.color_mode == "CMYK"
    assert not loaded.builtin
    store.delete("my_journal")
    with pytest.raises(TemplateError):
        store.get("my_journal")


def test_user_template_overrides_builtin(store):
    data = store.get("ieee").to_dict()
    data["name"] = "IEEE (saját)"
    store.save(JournalTemplate.from_dict(data))
    assert store.get("ieee").name == "IEEE (saját)"
    store.delete("ieee")
    assert store.get("ieee").builtin


def test_builtin_cannot_be_deleted(store):
    with pytest.raises(TemplateError):
        store.delete("elsevier")


@pytest.mark.parametrize("patch", [
    {"id": "Bad ID"},
    {"name": ""},
    {"figure": {"dpi": 10}},
    {"figure": {"color_mode": "HSV"}},
    {"figure": {"file_format": "PNG", "color_mode": "CMYK"}},
    {"figure": {"file_format": "JPEG", "color_mode": "Bilevel"}},
    {"figure": {"filename_pattern": "Fig"}},
    {"figure": {"filename_pattern": "Fig/{number}"}},
    {"figure": {"unknown_field": 1}},
    {"figure": {"dpi": "abc"}},
    {"table": {"header_fill": "red"}},
    {"table": {"border_style": "dotted"}},
    {"figure": {"single_column_mm": 200, "double_column_mm": 100}},
])
def test_invalid_templates_rejected(patch):
    data = {"id": "x", "name": "X"}
    for key, value in patch.items():
        data[key] = value
    with pytest.raises(TemplateError):
        JournalTemplate.from_dict(data)


def test_import_export(store):
    text = TemplateStore.export_json(store.get("acs")).replace('"acs"', '"acs_copy"', 1)
    tpl = store.import_json(text)
    assert tpl.id == "acs_copy"
    assert json.loads(TemplateStore.export_json(store.get("acs_copy")))["figure"]["color_mode"] == "CMYK"
    with pytest.raises(TemplateError):
        store.import_json("{not json")


def test_corrupt_user_file_is_ignored(store):
    store.user_dir.mkdir(parents=True)
    (store.user_dir / "broken.json").write_text("{]", encoding="utf-8")
    assert "broken" not in store.ids()


def test_string_coercion():
    tpl = JournalTemplate.from_dict({"id": "s", "name": "S",
                                     "figure": {"dpi": "600", "auto_trim": "false"}})
    assert tpl.figure.dpi == 600 and tpl.figure.auto_trim is False
