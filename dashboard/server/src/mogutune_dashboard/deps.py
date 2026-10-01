# Copyright (c) 2026 Milkeyyy

"""FastAPI の共通依存関係"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from pymongo.asynchronous.database import AsyncDatabase

from mogutune_dashboard.db import get_db

DbDep = Annotated[AsyncDatabase, Depends(get_db)]
