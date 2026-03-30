from __future__ import annotations

import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.portal_seller_open_api.services.normalization import (
    clean_text,
    generate_uppercase_uuid,
)
from shared_domain.models.infound import SellerTkRpaScriptLogs, SellerTkRpaScripts


class SellerRpaScriptService:
    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session

    async def upsert_script_snapshot(
        self,
        *,
        actor_id: str,
        code: str,
        name: str,
        script: dict | list | str | None,
        version_hint: str | None = None,
    ) -> tuple[str | None, str | None]:
        normalized_code = clean_text(code)
        normalized_name = clean_text(name)
        if not normalized_code or not normalized_name or script in (None, "", [], {}):
            return None, None

        serialized_script = self._serialize_script(script)
        if not serialized_script:
            return None, None

        current_version = clean_text(version_hint) or self._build_version(serialized_script)
        existing = await self._find_script_by_code(normalized_code)

        if existing is None:
            script_row = SellerTkRpaScripts(
                id=generate_uppercase_uuid(),
                code=normalized_code,
                name=normalized_name,
                pro_script=serialized_script,
                current_version=current_version,
                creator_id=actor_id,
                creation_time=self._utc_now(),
                last_modifier_id=actor_id,
                last_modification_time=self._utc_now(),
            )
            self.db_session.add(script_row)
            self.db_session.add(
                SellerTkRpaScriptLogs(
                    id=generate_uppercase_uuid(),
                    code=normalized_code,
                    name=normalized_name,
                    pro_script=serialized_script,
                    current_version=current_version,
                    creator_id=actor_id,
                    creation_time=self._utc_now(),
                    last_modifier_id=actor_id,
                    last_modification_time=self._utc_now(),
                )
            )
            return normalized_code, current_version

        if (
            existing.pro_script != serialized_script
            or clean_text(existing.current_version) != current_version
            or clean_text(existing.name) != normalized_name
        ):
            existing.name = normalized_name
            existing.pro_script = serialized_script
            existing.current_version = current_version
            existing.last_modifier_id = actor_id
            existing.last_modification_time = self._utc_now()
            self.db_session.add(
                SellerTkRpaScriptLogs(
                    id=generate_uppercase_uuid(),
                    code=normalized_code,
                    name=normalized_name,
                    pro_script=serialized_script,
                    current_version=current_version,
                    creator_id=actor_id,
                    creation_time=self._utc_now(),
                    last_modifier_id=actor_id,
                    last_modification_time=self._utc_now(),
                )
            )

        return normalized_code, current_version

    async def _find_script_by_code(self, code: str) -> SellerTkRpaScripts | None:
        stmt = select(SellerTkRpaScripts).where(SellerTkRpaScripts.code == code).limit(1)
        result = await self.db_session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _serialize_script(script: dict | list | str) -> str | None:
        if isinstance(script, (dict, list)):
            return json.dumps(script, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        text = clean_text(script)
        return text or None

    @staticmethod
    def _build_version(serialized_script: str) -> str:
        return uuid5(NAMESPACE_URL, serialized_script).hex[:16].upper()

    @staticmethod
    def _utc_now():
        from datetime import datetime

        return datetime.utcnow()
