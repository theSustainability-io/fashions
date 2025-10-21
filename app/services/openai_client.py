from __future__ import annotations

from openai import OpenAI

from app.config import get_settings


class OpenAIContentGenerator:
    """Wrapper around the OpenAI client using the provided marketing prompts."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing. Set it before generating content.")
        self._client = OpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model

    def _complete(self, prompt: str) -> str:
        response = self._client.responses.create(
            model=self._model,
            input=prompt,
        )
        return response.output_text.strip()

    def generate_h2_heading(self, keyword: str) -> str:
        prompt = (
            "Given the main collection keyword: {keyword}. Suggest one complementary, "
            "semantically relevant H2 subtopic that helps shoppers discover related items.\n"
            "- Keep it 2-5 words.\n"
            "- Avoid repeating the main keyword verbatim.\n"
            "- Be specific, non-brand, and non-location.\n"
            "Return just the phrase."
        ).format(keyword=keyword)
        return self._complete(prompt)

    def generate_paragraph(self, keyword: str, subtopic: str, target_words: str) -> str:
        prompt = (
            "Write an informative, customer-friendly paragraph (~{target_words} words) expanding "
            "on the subtopic: {subtopic} in the context of {keyword}.\n"
            "- Tone: helpful, concise, non-fluffy.\n"
            "- Include practical shopping guidance (fit, fabrics, occasions, styling).\n"
            "- No brand claims, no pricing.\n"
            "- Avoid keyword stuffing.\n"
            "- Return plain HTML <p> only (no inline styles)."
        ).format(target_words=target_words, subtopic=subtopic, keyword=keyword)
        return self._complete(prompt)

    def generate_h3_heading(self, keyword: str, h2_keyword: str) -> str:
        prompt = (
            "For the main keyword {keyword}, suggest another complementary subtopic for an H3 heading "
            "that differs from {h2_keyword}.\n"
            "- 2-5 words, concise, non-brand.\n"
            "Return just the phrase."
        ).format(keyword=keyword, h2_keyword=h2_keyword)
        return self._complete(prompt)
