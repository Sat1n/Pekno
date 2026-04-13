from typing import List

from hub.core import model_settings


class LLMService:
    async def generate_summary(self, text: str, length: str = "short", preferred_locale: str | None = None) -> str:
        summary, _ = await model_settings.generate_summary(text, length=length, preferred_locale=preferred_locale)
        return summary

    async def extract_tags(self, text: str, preferred_locale: str | None = None) -> List[str]:
        tags, _ = await model_settings.extract_tags(text, preferred_locale=preferred_locale)
        return tags

    async def current_model_name(self, purpose: str = "short_summary") -> str:
        assignments = await model_settings.get_model_assignments()
        match = next((item for item in assignments if item["key"] == purpose), None)
        return match["model"] if match else ""

    async def understand_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        ocr_text: str = "",
        preferred_locale: str | None = None,
    ) -> tuple[dict, str, str]:
        return await model_settings.understand_image(
            image_bytes,
            mime_type,
            ocr_text=ocr_text,
            preferred_locale=preferred_locale,
        )


class EmbeddingService:
    async def get_vector(self, text: str) -> List[float]:
        vector, _ = await model_settings.embed_text(text)
        return vector

    async def current_model_name(self) -> str:
        assignments = await model_settings.get_model_assignments()
        match = next((item for item in assignments if item["key"] == "embedding"), None)
        return match["model"] if match else ""


class LLMManager:
    def __init__(self):
        self.llm = LLMService()
        self.embed = EmbeddingService()

    async def generate_summary(self, text: str, length: str = "short", preferred_locale: str | None = None) -> str:
        return await self.llm.generate_summary(text, length=length, preferred_locale=preferred_locale)

    async def extract_tags(self, text: str, preferred_locale: str | None = None) -> List[str]:
        return await self.llm.extract_tags(text, preferred_locale=preferred_locale)

    async def get_vector(self, text: str) -> List[float]:
        return await self.embed.get_vector(text)

    async def get_summary_model_name(self, length: str = "short") -> str:
        return await self.llm.current_model_name("short_summary" if length == "short" else "long_summary")

    async def get_tagging_model_name(self) -> str:
        return await self.llm.current_model_name("tagging")

    async def get_embedding_model_name(self) -> str:
        return await self.embed.current_model_name()

    async def understand_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        ocr_text: str = "",
        preferred_locale: str | None = None,
    ) -> tuple[dict, str, str]:
        return await self.llm.understand_image(
            image_bytes,
            mime_type,
            ocr_text=ocr_text,
            preferred_locale=preferred_locale,
        )
