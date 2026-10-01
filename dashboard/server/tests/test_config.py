# Copyright (c) 2026 Milkeyyy

"""設定読み込みのテスト"""

from __future__ import annotations

import pytest

from mogutune_dashboard.config import ConfigError, Settings, _env_set, _normalize_team_domain


def test_normalize_team_domain() -> None:
	assert _normalize_team_domain("team") == "https://team"
	assert _normalize_team_domain("https://team.cloudflareaccess.com/") == "https://team.cloudflareaccess.com"
	assert _normalize_team_domain("") == ""


def test_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("TEST_SET", "a, b ,,c")
	assert _env_set("TEST_SET") == frozenset({"a", "b", "c"})
	monkeypatch.delenv("TEST_SET")
	assert _env_set("TEST_SET") == frozenset()


def test_from_env_requires_db_uri(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.delenv("DB_URI", raising=False)
	monkeypatch.setenv("DASHBOARD_AUTH_DISABLED", "true")
	with pytest.raises(ConfigError):
		Settings.from_env()


def test_from_env_requires_access_settings(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DB_URI", "mongodb://localhost:27017")
	monkeypatch.delenv("DASHBOARD_AUTH_DISABLED", raising=False)
	monkeypatch.delenv("CF_ACCESS_TEAM_DOMAIN", raising=False)
	monkeypatch.delenv("CF_ACCESS_AUD", raising=False)
	with pytest.raises(ConfigError):
		Settings.from_env()


def test_from_env_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DB_URI", "mongodb://localhost:27017")
	monkeypatch.setenv("DASHBOARD_AUTH_DISABLED", "true")
	monkeypatch.setenv("DB_NAME", "testdb")
	monkeypatch.setenv("DASHBOARD_ALLOWED_EMAILS", "a@example.com,b@example.com")
	settings = Settings.from_env()
	assert settings.auth_disabled is True
	assert settings.db_name == "testdb"
	assert settings.allowed_emails == frozenset({"a@example.com", "b@example.com"})
	assert settings.cf_access_team_domain == ""


def test_from_env_access_settings(monkeypatch: pytest.MonkeyPatch) -> None:
	monkeypatch.setenv("DB_URI", "mongodb://localhost:27017")
	monkeypatch.setenv("DASHBOARD_AUTH_DISABLED", "false")
	monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "team.cloudflareaccess.com")
	monkeypatch.setenv("CF_ACCESS_AUD", "aud")
	settings = Settings.from_env()
	assert settings.cf_access_team_domain == "https://team.cloudflareaccess.com"
	assert settings.cf_access_aud == "aud"
