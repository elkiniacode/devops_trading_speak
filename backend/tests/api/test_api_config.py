import pytest

from app.config import REPO_ROOT, get_settings, llm_mode


def test_defaults(monkeypatch):
    for name in ("DB_PATH", "STATIC_DIR", "CORS_ORIGINS"):
        monkeypatch.delenv(name, raising=False)
    settings = get_settings()
    assert settings.db_path == REPO_ROOT / "db" / "finally.db"
    assert settings.static_dir == REPO_ROOT / "backend" / "static"
    assert settings.cors_origins == []


def test_paths_are_relative_to_the_repo_root(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", "db/dev-backend.db")
    monkeypatch.setenv("STATIC_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:3000 , http://127.0.0.1:3000,")
    settings = get_settings()
    assert settings.db_path == REPO_ROOT / "db" / "dev-backend.db"
    assert settings.static_dir == tmp_path / "out"  # absolute paths are kept
    assert settings.cors_origins == ["http://localhost:3000", "http://127.0.0.1:3000"]


@pytest.mark.parametrize(
    ("mock", "key", "mode"),
    [
        ("true", "", "mock"),
        ("TRUE", "sk-x", "mock"),
        ("false", "sk-x", "openrouter"),
        ("", "  ", "unconfigured"),
        (None, None, "unconfigured"),
    ],
)
def test_llm_mode(monkeypatch, mock, key, mode):
    for name, value in (("LLM_MOCK", mock), ("OPENROUTER_API_KEY", key)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    assert llm_mode() == mode
