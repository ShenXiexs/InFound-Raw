from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.core.config import get_settings
from common.models.infound import Products


@dataclass(frozen=True)
class ChatbotMessage:
    type: str
    content: str


class ChatbotMessageBuilder:
    SCENARIO_SHIPPED = "shipped"
    SCENARIO_CONTENT_PENDING = "content_pending"
    SCENARIO_NO_CONTENT_POSTED = "no_content_posted"
    SCENARIO_MISSING_AD_CODE = "missing_ad_code"

    def __init__(self) -> None:
        settings = get_settings()
        self.link_template = str(
            getattr(
                settings,
                "CHATBOT_SAMPLE_LINK_TEMPLATE",
                "https://creator.infound.ai/samples/{sampleId}",
            )
            or "https://creator.infound.ai/samples/{sampleId}"
        )

    async def build_messages(
        self,
        *,
        session: AsyncSession,
        scenario: str,
        sample: Any,
        creator_whatsapp: Optional[str],
    ) -> List[dict]:
        normalized = str(scenario or "").strip().lower()
        if normalized == self.SCENARIO_SHIPPED:
            return await self._shipped(session, sample, creator_whatsapp)
        if normalized == self.SCENARIO_CONTENT_PENDING:
            return await self._content_pending(session, sample)
        if normalized == self.SCENARIO_NO_CONTENT_POSTED:
            return await self._no_content_posted(session, sample)
        if normalized == self.SCENARIO_MISSING_AD_CODE:
            return await self._missing_ad_code(session, sample)
        return []

    async def _product_block(self, session: AsyncSession, sample: Any) -> str:
        product_id = str(getattr(sample, "platform_product_id", "") or "").strip()
        product_name = ""
        if product_id:
            result = await session.execute(
                select(Products.product_name)
                .where(Products.platform_product_id == product_id)
                .limit(1)
            )
            product_name = str(result.scalars().first() or "").strip()
        parts: List[str] = []
        if product_name:
            parts.append(product_name)
        if product_id:
            parts.append(f"product ID: {product_id}")
        return "\n".join(parts) if parts else "product info unavailable"

    def _link(self, sample: Any) -> str:
        sample_id = str(getattr(sample, "id", "") or "").strip()
        if not sample_id:
            return ""
        return self.link_template.format(sampleId=sample_id.upper())

    async def _shipped(
        self,
        session: AsyncSession,
        sample: Any,
        creator_whatsapp: Optional[str],
    ) -> List[dict]:
        has_whatsapp = bool((creator_whatsapp or "").strip())
        block = await self._product_block(session, sample)
        if has_whatsapp:
            text = (
                "🥰 Me complace informarte que tus muestras ya han sido enviadas.\n\n"
                f"{block}"
            )
            return [{"type": "text", "content": text}]

        text = (
            "🥰 Me complace informarte que tus muestras ya han sido enviadas.\n\n"
            f"{block}\n\n"
            "Además, nos gustaría invitarte a unirte a nuestra comunidad de creadores, donde compartimos oportunidades de colaboración, briefings y tips para aumentar tus ventas.\n\n"
            "¿Me podrías compartir tu número de WhatsApp para agregarte?\n\n"
            "O, si prefieres, puedes agregarme directamente a WhatsApp y enviarme un mensaje, incluyendo tu Creator ID.\n\n"
            "Mi WhatsApp: +52 55 6091 7657."
        )
        return [{"type": "text", "content": text}]

    async def _content_pending(self, session: AsyncSession, sample: Any) -> List[dict]:
        block = await self._product_block(session, sample)
        first = (
            "Hola, ¿ya recibiste las muestras? 😊\n\n"
            f"{block}\n\n"
            "Aquí tienes la Guía para Creadores que hemos diseñado especialmente para ti. ¡Descubre el secreto para generar ventas explosivas!\n\n"
            "Copia el enlace y ábrelo en el navegador de tu móvil para ver los detalles.👇"
        )
        messages = [{"type": "text", "content": first}]
        link = self._link(sample)
        if link:
            messages.append({"type": "link", "content": link})
        return messages

    async def _no_content_posted(self, session: AsyncSession, sample: Any) -> List[dict]:
        block = await self._product_block(session, sample)
        first = (
            "Hola, ¿cómo estás? 😊\n\n"
            "Notamos que el contenido del producto aún no ha sido publicado y ya pasó la fecha acordada. ¿Podrías por favor confirmarme cuándo podrás subir el video?\n\n"
            f"{block}\n\n"
            "Tu publicación es muy importante para futuras colaboraciones y para poder seguir enviándote más productos. 🙏\n\n"
            "¡Gracias por tu apoyo!\n\n"
            "Copia el enlace y ábrelo en el navegador de tu móvil para ver los detalles.👇"
        )
        messages = [{"type": "text", "content": first}]
        link = self._link(sample)
        if link:
            messages.append({"type": "link", "content": link})
        return messages

    async def _missing_ad_code(self, session: AsyncSession, sample: Any) -> List[dict]:
        block = await self._product_block(session, sample)
        first = (
            "Hola, 😍 nos encantaría darle aún más visibilidad con una promoción en TikTok. ¿Podrías compartirnos tu código AD para que podamos lanzar la campaña? 🙏\n\n"
            f"{block}\n\n"
            "Copia el enlace y ábrelo en el navegador de tu móvil para ver los detalles.👇"
        )
        messages = [{"type": "text", "content": first}]
        link = self._link(sample)
        if link:
            messages.append({"type": "link", "content": link})
        return messages


chatbot_message_builder = ChatbotMessageBuilder()
