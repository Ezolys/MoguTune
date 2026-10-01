# Copyright (c) 2026 Milkeyyy

"""Cloudflare Access JWT 検証のテスト"""

from __future__ import annotations

import datetime
import json
from typing import Any

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from mogutune_dashboard.access import AccessDeniedError, AccessVerifier
from mogutune_dashboard.config import Settings

TEAM_DOMAIN = "https://team.cloudflareaccess.com"
AUDIENCE = "aud-tag"
KID = "test-kid"


def _settings(**overrides: Any) -> Settings:  # noqa: ANN401
	defaults: dict[str, Any] = {
		"db_uri": "mongodb://localhost:27017",
		"db_name": "mogutune",
		"cf_access_team_domain": TEAM_DOMAIN,
		"cf_access_aud": AUDIENCE,
		"allowed_emails": frozenset(),
		"auth_disabled": False,
		"timezone": "UTC",
		"static_dir": ".",
		"allowed_origins": frozenset(),
	}
	defaults.update(overrides)
	return Settings(**defaults)


@pytest.fixture
def rsa_key() -> Any:  # noqa: ANN401
	return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwk(rsa_key: Any) -> dict:  # noqa: ANN401
	data = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(rsa_key.public_key()))
	data["kid"] = KID
	return data


def _token(private_key: Any, **claims: Any) -> str:  # noqa: ANN401
	now = datetime.datetime.now(tz=datetime.UTC)
	payload: dict[str, Any] = {
		"aud": AUDIENCE,
		"iss": TEAM_DOMAIN,
		"iat": now,
		"exp": now + datetime.timedelta(minutes=5),
		"email": "user@example.com",
		"sub": "user-1",
	}
	payload.update(claims)
	return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": KID})


def _verifier(settings: Settings, jwk: dict) -> AccessVerifier:
	verifier = AccessVerifier(settings, httpx.AsyncClient())
	verifier._keys = {KID: jwk}
	verifier._fetched_at = datetime.datetime.now(tz=datetime.UTC)
	return verifier


async def test_verify_success(rsa_key: Any, jwk: dict) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(), jwk)
	user = await verifier.verify(_token(rsa_key))
	assert user.email == "user@example.com"
	assert user.display_name == "user@example.com"


async def test_verify_allowed_emails(rsa_key: Any, jwk: dict) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(allowed_emails=frozenset({"USER@example.com"})), jwk)
	user = await verifier.verify(_token(rsa_key))
	assert user.email == "user@example.com"


async def test_verify_denied_email(rsa_key: Any, jwk: dict) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(allowed_emails=frozenset({"other@example.com"})), jwk)
	with pytest.raises(AccessDeniedError, match="許可されていない"):
		await verifier.verify(_token(rsa_key))


async def test_verify_expired(rsa_key: Any, jwk: dict) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(), jwk)
	expired = datetime.datetime.now(tz=datetime.UTC) - datetime.timedelta(minutes=5)
	with pytest.raises(AccessDeniedError, match="検証に失敗"):
		await verifier.verify(_token(rsa_key, exp=expired))


async def test_verify_wrong_audience(rsa_key: Any, jwk: dict) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(), jwk)
	with pytest.raises(AccessDeniedError, match="検証に失敗"):
		await verifier.verify(_token(rsa_key, aud="other-aud"))


async def test_verify_unknown_kid(rsa_key: Any) -> None:  # noqa: ANN401
	verifier = _verifier(_settings(), {})
	verifier._keys = {}

	async def fail_fetch() -> None:
		message = "no jwks"
		raise ValueError(message)

	verifier._fetch_keys = fail_fetch  # type: ignore[method-assign]
	with pytest.raises(AccessDeniedError, match="JWKS"):
		await verifier.verify(_token(rsa_key))


async def test_verify_invalid_token(jwk: dict) -> None:
	verifier = _verifier(_settings(), jwk)
	with pytest.raises(AccessDeniedError, match="ヘッダ"):
		await verifier.verify("not-a-jwt")
