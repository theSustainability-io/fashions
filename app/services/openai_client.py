from __future__ import annotations

from openai import OpenAI

from app.config import get_settings
from app.utils.prompt_manager import get_prompt_manager


class OpenAIContentGenerator:
    """Wrapper around the OpenAI client using the provided marketing prompts."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Set it before generating content.")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        self._prompt_manager = get_prompt_manager()

    def _complete(self, prompt: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=prompt,
        )
        return response.output_text.strip()

    def generate_h2_heading(self, keyword: str) -> str:
        template = self._prompt_manager.get_prompt("h2_heading")
        prompt = template.format(keyword=keyword)
        return self._complete(prompt)

    def generate_paragraph(self, keyword: str, subtopic: str, target_words: str) -> str:
        template = self._prompt_manager.get_prompt("paragraph")
        prompt = template.format(target_words=target_words, subtopic=subtopic, keyword=keyword)
        return self._complete(prompt)

    def generate_h3_heading(self, keyword: str, h2_keyword: str) -> str:
        template = self._prompt_manager.get_prompt("h3_heading")
        prompt = template.format(keyword=keyword, h2_keyword=h2_keyword)
        return self._complete(prompt)
