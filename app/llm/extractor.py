import json

from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from app.config import Settings
from app.llm.prompts import SPREADSHEET_CONTEXT
from app.profiles.nsec import NSECProfile
from app.schemas.canonical_raw import RoutineCollectionExtraction, RoutineExtraction


class ExtractionError(ValueError):
    pass


class ModelServiceError(RuntimeError):
    pass


class RoutineExtractor:
    def __init__(self, settings: Settings, profile=None, model=None):
        self.profile = profile or NSECProfile()
        if model is not None:
            self.model = model
        elif settings.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic
            if not settings.anthropic_api_key or not settings.llm_model:
                raise ExtractionError("Set ANTHROPIC_API_KEY and LLM_MODEL in .env")
            self.model = ChatAnthropic(
                model=settings.llm_model, api_key=settings.anthropic_api_key,
                timeout=settings.llm_timeout_seconds, max_retries=0,
            )
        elif settings.llm_provider == "openai":
            if not settings.openai_api_key or not settings.llm_model:
                raise ExtractionError("Set OPENAI_API_KEY and LLM_MODEL in .env")
            self.model = ChatOpenAI(
                model=settings.llm_model, api_key=settings.openai_api_key,
                base_url=settings.llm_base_url, timeout=settings.llm_timeout_seconds,
                max_retries=0,
            )
        else:
            raise ExtractionError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    async def extract(self, image_urls: list[str], document_text: str | None = None) -> list[RoutineExtraction]:
        content = [{"type": "text", "text": self.profile.prompt}]
        if document_text is not None:
            content.append({"type": "text", "text": SPREADSHEET_CONTEXT + document_text})
        content.extend({"type": "image_url", "image_url": {"url": url}} for url in image_urls)
        try:
            response = await self.model.ainvoke([{"role": "user", "content": content}])
        except Exception as exc:
            raise ModelServiceError(f"Model request failed: {exc}") from exc
        body = response.content
        if isinstance(body, list):
            body = "".join(part.get("text", "") for part in body if isinstance(part, dict))
        if not isinstance(body, str):
            raise ExtractionError("Model returned non-text content")
        body = body.strip()
        if body.startswith("```json"):
            body = body[7:]
        if body.startswith("```"):
            body = body[3:]
        if body.endswith("```"):
            body = body[:-3]
        try:
            payload = json.loads(body.strip())
            collection = RoutineCollectionExtraction.model_validate(payload)
            return [self.profile.adapt(self.profile.raw_schema.model_validate(item.model_dump()))
                    for item in collection.routines]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ExtractionError("Model response must be JSON with a nonempty routines array") from exc
