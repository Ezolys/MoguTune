# Copyright (c) 2026 Milkeyyy

"""Cloudflare Access の JWT 検証と認証依存関係"""

from __future__ import annotations

import asyncio
import datetime
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated

import httpx
import jwt
from fastapi import Depends, HTTPException, Request

if TYPE_CHECKING:
	from mogutune_dashboard.config import Settings

logger = logging.getLogger(__name__)

ALGORITHMS = ["RS256"]
JWKS_CACHE_SECONDS = 600.0
AUTH_HEADER = "Cf-Access-Jwt-Assertion"

_ERR_HEADER = "トークンのヘッダを解析できません"
_ERR_VERIFY = "トークンの検証に失敗しました"
_ERR_NOT_ALLOWED = "許可されていないユーザーです"
_ERR_NO_KID = "トークンに kid がありません"
_ERR_JWKS = "JWKS の取得に失敗しました"
_ERR_KEY_NOT_FOUND = "トークンの署名鍵が見つかりません"
_ERR_KEY_PARSE = "署名鍵の解析に失敗しました"


class AccessDeniedError(Exception):
	"""Cloudflare Access の検証に失敗したことを表す例外"""


@dataclass(frozen=True)
class AccessUser:
	"""Cloudflare Access で認証されたユーザー"""

	email: str | None
	sub: str | None

	@property
	def display_name(self) -> str:
		"""表示用のユーザー名を返す"""
		return self.email or self.sub or "unknown"


def get_current_user(request: Request) -> AccessUser:
	"""リクエストから認証済みユーザーを取得する (未認証は 401)"""
	user = getattr(request.state, "user", None)
	if not isinstance(user, AccessUser):
		raise HTTPException(status_code=401, detail="認証されていません")
	return user


CurrentUser = Annotated[AccessUser, Depends(get_current_user)]


class AccessVerifier:
	"""Cf-Access-Jwt-Assertion ヘッダの JWT を JWKS で検証する"""

	def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
		self._settings = settings
		self._client = client
		self._keys: dict[str, dict] = {}
		self._fetched_at: datetime.datetime | None = None
		self._lock = asyncio.Lock()
		self._allowed_emails = frozenset(email.lower() for email in settings.allowed_emails)

	async def verify(self, token: str) -> AccessUser:
		"""JWT を検証してユーザーを返す (失敗時は AccessDeniedError)"""
		try:
			header = jwt.get_unverified_header(token)
		except jwt.PyJWTError as e:
			raise AccessDeniedError(_ERR_HEADER) from e

		key = await self._get_key(header.get("kid"))
		try:
			claims = jwt.decode(
				token,
				key=key,
				algorithms=ALGORITHMS,
				audience=self._settings.cf_access_aud,
				issuer=self._settings.cf_access_team_domain,
				options={"require": ["exp", "iat"]},
			)
		except jwt.PyJWTError as e:
			raise AccessDeniedError(_ERR_VERIFY) from e

		email = claims.get("email")
		email = email if isinstance(email, str) else None
		if self._allowed_emails and (email is None or email.lower() not in self._allowed_emails):
			raise AccessDeniedError(_ERR_NOT_ALLOWED)

		sub = claims.get("sub")
		return AccessUser(email=email, sub=sub if isinstance(sub, str) else None)

	async def _get_key(self, kid: object) -> object:
		"""JWKS から kid に対応する公開鍵を取得する (キャッシュ切れ・未知の kid は再取得する)"""
		if not isinstance(kid, str):
			raise AccessDeniedError(_ERR_NO_KID)

		async with self._lock:
			expired = (
				self._fetched_at is None or (datetime.datetime.now(tz=datetime.UTC) - self._fetched_at).total_seconds() > JWKS_CACHE_SECONDS
			)
			if kid not in self._keys or expired:
				try:
					await self._fetch_keys()
				except (httpx.HTTPError, TypeError, ValueError) as e:
					raise AccessDeniedError(_ERR_JWKS) from e
			key_data = self._keys.get(kid)

		if key_data is None:
			raise AccessDeniedError(_ERR_KEY_NOT_FOUND)
		try:
			return jwt.PyJWK(key_data, algorithm="RS256").key
		except jwt.PyJWTError as e:
			raise AccessDeniedError(_ERR_KEY_PARSE) from e

	async def _fetch_keys(self) -> None:
		"""Cloudflare Access の JWKS を取得してキャッシュする"""
		url = f"{self._settings.cf_access_team_domain}/cdn-cgi/access/certs"
		response = await self._client.get(url, timeout=10.0)
		response.raise_for_status()
		payload = response.json()
		keys = payload.get("keys") if isinstance(payload, dict) else None
		if not isinstance(keys, list):
			message = "JWKS の形式が不正です"
			raise TypeError(message)
		self._keys = {key["kid"]: key for key in keys if isinstance(key, dict) and isinstance(key.get("kid"), str)}
		self._fetched_at = datetime.datetime.now(tz=datetime.UTC)
		logger.debug("Cloudflare Access の JWKS を更新: %d keys", len(self._keys))
