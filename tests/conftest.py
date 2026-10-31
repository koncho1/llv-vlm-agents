import pytest


@pytest.fixture(autouse=True)
def saved_outfits_path(tmp_path, monkeypatch):
    """Keep every test away from the real data/saved_outfits.json."""
    path = tmp_path / "saved_outfits.json"
    monkeypatch.setenv("SAVED_OUTFITS_PATH", str(path))
    return path
