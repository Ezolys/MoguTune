# Copyright (c) 2026 Milkeyyy

"""ダッシュボードの環境変数設定"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

DEFAULT_PORT = 8787
DEFAULT_TIMEZONE = "Asia/Tokyo"
DEFAULT_STATIC_DIR = "client/dist"


class ConfigError(RuntimeError):
	"""設定不備を表す例外"""


@dataclass(frozen=True)
class Settings:
	"""環境変数から読み込んだ設定"""

	db_uri: str
	db_name: str
	cf_access_team_domain: str
	cf_access_aud: str
	allowed_emails: frozenset[str]
	auth_disabled: bool
	timezone: str
	static_dir: str
	allowed_origins: frozenset[str]

	@classmethod
	def from_env(cls) -> Settings:
		"""環境変数から設定を読み込む (必須項目が無い場合は ConfigError)"""
		db_uri = os.getenv("DB_URI", "")
		if not db_uri:
			message = "DB_URI が設定されていません"
			raise ConfigError(message)

		auth_disabled = _env_bool("DASHBOARD_AUTH_DISABLED", default=False)
		team_domain = _normalize_team_domain(os.getenv("CF_ACCESS_TEAM_DOMAIN", ""))
		aud = os.getenv("CF_ACCESS_AUD", "")
		if not auth_disabled and (not team_domain or not aud):
			message = "CF_ACCESS_TEAM_DOMAIN と CF_ACCESS_AUD が設定されていません (開発時は DASHBOARD_AUTH_DISABLED=true)"
			raise ConfigError(message)

		return cls(
			db_uri=db_uri,
			db_name=os.getenv("DB_NAME", "mogutune"),
			cf_access_team_domain=team_domain,
			cf_access_aud=aud,
			allowed_emails=_env_set("DASHBOARD_ALLOWED_EMAILS"),
			auth_disabled=auth_disabled,
			timezone=os.getenv("DASHBOARD_TIMEZONE", DEFAULT_TIMEZONE),
			static_dir=os.getenv("DASHBOARD_STATIC_DIR", DEFAULT_STATIC_DIR),
			allowed_origins=_env_set("DASHBOARD_ALLOWED_ORIGINS"),
		)


def _env_bool(name: str, *, default: bool) -> bool:
	"""環境変数を真偽値として読み込む"""
	value = os.getenv(name)
	if value is None:
		return default
	return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_set(name: str) -> frozenset[str]:
	"""カンマ区切りの環境変数を集合として読み込む"""
	value = os.getenv(name, "")
	return frozenset(part.strip() for part in value.split(",") if part.strip())


def _normalize_team_domain(value: str) -> str:
	"""Cloudflare Access のチームドメインを URL 形式へ正規化する"""
	value = value.strip().rstrip("/")
	if not value:
		return ""
	if not value.startswith(("http://", "https://")):
		return f"https://{value}"
	return value


@lru_cache
def get_settings() -> Settings:
	"""設定を取得する (プロセス内でキャッシュする)"""
	return Settings.from_env()
