import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "examples"))

from manuscript_formatter.templates import TemplateStore  # noqa: E402


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    import make_sample

    out = tmp_path_factory.mktemp("samples")
    paths = {"docx": make_sample.make_docx(out / "sample.docx")}
    try:
        paths["pdf"] = make_sample.make_pdf(out / "sample.pdf")
    except ImportError:
        pass
    return paths


@pytest.fixture
def store(tmp_path):
    return TemplateStore(user_dir=tmp_path / "user_templates")
