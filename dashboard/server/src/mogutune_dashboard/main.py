# Copyright (c) 2026 Milkeyyy

"""MoguTune 管理ダッシュボードの FastAPI アプリケーション"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from mogutune_dashboard.access import AUTH_HEADER, AccessDeniedError, AccessUser, AccessVerifier, CurrentUser
from mogutune_dashboard.config import get_settings
from mogutune_dashboard.db import create_client
from mogutune_dashboard.routers import commands, errors, guilds, maintenance, quiz, status

if TYPE_CHECKING:
	from collections.abc import AsyncIterator

	from starlette.middleware.base import RequestResponseEndpoint
	from starlette.responses import Response

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEV_USER_EMAIL = "dev@localhost"
HEALTH_PATH = "/healthz"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
	"""MongoDB と Cloudflare Access 検証器を初期化する"""
	settings = get_settings()
	client = create_client(settings.db_uri)
	await client.admin.command("ping")
	app.state.db = client[settings.db_name]
	app.state.http = httpx.AsyncClient()
	app.state.verifier = AccessVerifier(settings, app.state.http)
	logger.info(
		"ダッシュボード起動: DB=%s / 認証=%s",
		settings.db_name,
		"無効 (開発モード)" if settings.auth_disabled else "Cloudflare Access",
	)
	try:
		yield
	finally:
		await app.state.http.aclose()
		await client.close()


app = FastAPI(title="MoguTune Dashboard", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def access_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
	"""Cloudflare Access の JWT を検証して未認証アクセスを拒否する"""
	if request.url.path == HEALTH_PATH:
		return await call_next(request)

	settings = get_settings()
	if settings.auth_disabled:
		request.state.user = AccessUser(email=DEV_USER_EMAIL, sub=None)
		return await call_next(request)

	token = request.headers.get(AUTH_HEADER)
	if not token:
		return JSONResponse(status_code=401, content={"detail": "Cloudflare Access のトークンがありません"})

	try:
		request.state.user = await request.app.state.verifier.verify(token)
	except AccessDeniedError as e:
		logger.warning("アクセスを拒否: %s", e)
		return JSONResponse(status_code=403, content={"detail": "アクセスが拒否されました"})

	return await call_next(request)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
	"""更新系リクエストの Origin を検証する (CSRF 対策)"""
	if request.method not in UNSAFE_METHODS:
		return await call_next(request)

	origin = request.headers.get("origin")
	if origin:
		settings = get_settings()
		# Cloudflare Tunnel 越しでは X-Forwarded-Proto が実際のスキームになる
		scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
		host = request.headers.get("host", "")
		allowed = settings.allowed_origins or {f"{scheme}://{host}"}
		if origin.rstrip("/") not in allowed:
			logger.warning("Origin を拒否: %s", origin)
			return JSONResponse(status_code=403, content={"detail": "Origin が許可されていません"})

	return await call_next(request)


@app.get(HEALTH_PATH, include_in_schema=False)
async def healthz() -> dict[str, str]:
	"""ヘルスチェック (認証不要)"""
	return {"status": "ok"}


@app.get("/api/me", include_in_schema=False)
async def me(user: CurrentUser) -> dict[str, str | None]:
	"""認証済みユーザーを返す"""
	return {"email": user.email, "sub": user.sub}


app.include_router(status.router)
app.include_router(guilds.router)
app.include_router(commands.router)
app.include_router(quiz.router)
app.include_router(errors.router)
app.include_router(maintenance.router)


def _static_dir() -> Path:
	"""静的ファイルのディレクトリを解決する"""
	path = Path(get_settings().static_dir)
	if not path.is_absolute():
		path = Path.cwd() / path
	return path


STATIC_DIR = _static_dir()

if (STATIC_DIR / "assets").is_dir():
	app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
async def spa(full_path: str) -> FileResponse:
	"""SPA の静的ファイルを配信する (存在しないパスは index.html へフォールバックする)"""
	if full_path.startswith("api/"):
		raise HTTPException(status_code=404, detail="Not Found")

	candidate = (STATIC_DIR / full_path).resolve()
	if full_path and candidate.is_file() and candidate.is_relative_to(STATIC_DIR.resolve()):
		return FileResponse(candidate)

	index = STATIC_DIR / "index.html"
	if not index.is_file():
		raise HTTPException(status_code=404, detail="フロントエンドがビルドされていません")
	return FileResponse(index)
