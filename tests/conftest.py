import os

import pytest


@pytest.fixture(autouse=True)
def traces_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACE_FILE", str(tmp_path / "traces.jsonl"))


os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
