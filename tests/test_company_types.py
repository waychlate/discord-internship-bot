import sqlite3
from unittest import mock

import pytest

from src import company_types
from src.company_types import CompanyTyper, normalize


@pytest.fixture
def typer(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    y = tmp_path / "types.yaml"
    y.write_text("anduril: defense\nthe toro company: industrial\n")
    return CompanyTyper({}, str(tmp_path / "jobs.db"), str(y))


def gemini_reply(text):
    r = mock.Mock()
    r.json.return_value = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    return r


def test_normalize():
    assert normalize("Anduril Industries, Inc.") == "anduril industries"
    assert normalize("The Toro Company") == "toro"
    assert normalize("Sierra Nevada Corp") == "sierra nevada"


def test_yaml_hit_and_normalization(typer):
    assert typer.label("Anduril") == "defense"
    assert typer.label("ANDURIL, Inc.") == "defense"
    assert typer.label("Toro Co") == "industrial"


def test_real_yaml_covers_config_companies():
    import yaml
    cfg = yaml.safe_load(open("config.yaml"))
    t = CompanyTyper(cfg, ":memory:")
    missing = [c["name"] for c in cfg["sources"]["companies"] if normalize(c["name"]) not in t.table]
    assert not missing


def test_cache_hit(typer):
    with sqlite3.connect(typer.db_path) as c:
        c.execute("INSERT INTO company_types VALUES ('acme', 'semiconductor')")
    assert typer.label("Acme LLC") == "semiconductor"


def test_no_key_is_other_and_not_cached(typer):
    with mock.patch.object(company_types.requests, "post") as post:
        assert typer.label("Acme") == "other"
    post.assert_not_called()


def test_gemini_success_cached(typer, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with mock.patch.object(company_types.requests, "post", return_value=gemini_reply(" Aerospace.\n")) as post:
        assert typer.label("Acme Rockets") == "aerospace"
        assert typer.label("Acme Rockets Inc") == "aerospace"
    assert post.call_count == 1


def test_gemini_invalid_answer(typer, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with mock.patch.object(company_types.requests, "post", return_value=gemini_reply("a rocket company")) as post:
        assert typer.label("Acme") == "other"
        assert typer.label("Acme") == "other"
    assert post.call_count == 2  # invalid answers are not cached


def test_gemini_failure(typer, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    with mock.patch.object(company_types.requests, "post", side_effect=company_types.requests.Timeout):
        assert typer.label("Acme") == "other"
    with sqlite3.connect(typer.db_path) as c:
        assert c.execute("SELECT COUNT(*) FROM company_types").fetchone()[0] == 0
