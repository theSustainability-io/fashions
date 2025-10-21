from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from app.config import get_settings
from app.services.openai_client import OpenAIContentGenerator
from app.services.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)


@dataclass
class ExcelProcessingError:
    index: int
    keyword: str
    message: str


@dataclass
class ExcelProcessingResult:
    input_file: Path
    output_file: Path
    processed_rows: int
    skipped_rows: int
    errors: List[ExcelProcessingError]
    shopify_updates: int = 0


class ExcelProcessor:
    """Main orchestrator for reading Excel, generating content, and writing results."""

    REQUIRED_COLUMNS = {
        "keyword": "keywords",
        "h2_headline": "<h2> headline",
        "h3_headline": "<h3> headline",
        "h2_override": "h2_overrides",
        "h3_override": "h3_overrides",
        "collection_html": "collection_html",
        "processed_at": "_processed_at",
        "row_hash": "_row_hash",
    }

    H2_TEXT_COLUMN = "relevant text 2"
    H3_TEXT_COLUMN = "relevant text 3"

    def __init__(
        self,
        generator_factory: Callable[[], OpenAIContentGenerator] = OpenAIContentGenerator,
        shopify_client_factory: Optional[Callable[[], ShopifyClient]] = None,
    ) -> None:
        self.settings = get_settings()
        self._generator_factory = generator_factory
        self._generator: Optional[OpenAIContentGenerator] = None
        self._shopify_client_factory = shopify_client_factory
        self._shopify_client: Optional[ShopifyClient] = None

    def process_latest(self) -> Optional[ExcelProcessingResult]:
        input_path = self._find_latest_excel()
        if not input_path:
            logger.info("No Excel files found in %s", self.settings.input_dir)
            return None
        return self.process_file(input_path)

    def process_file(self, input_path: Path) -> ExcelProcessingResult:
        logger.info("Processing workbook %s", input_path)
        df = pd.read_excel(input_path)
        self._normalize_columns(df)

        processed = 0
        skipped = 0
        shopify_updates = 0
        errors: List[ExcelProcessingError] = []

        for idx, row in df.iterrows():
            keyword = str(row[self.REQUIRED_COLUMNS["keyword"]]).strip()
            if not keyword or keyword.lower() == "nan":
                skipped += 1
                continue

            target_hash = self._row_hash(row)
            existing_hash = str(row.get(self.REQUIRED_COLUMNS["row_hash"], "") or "")
            existing_html = str(row.get(self.REQUIRED_COLUMNS["collection_html"], "") or "")

            if existing_hash == target_hash and existing_html.strip():
                skipped += 1
                continue

            try:
                h2_heading = self._build_h2_heading(keyword, row)
                h2_paragraph = self._build_paragraph(
                    keyword=keyword,
                    subtopic=h2_heading,
                    target_words=200,
                )

                h3_heading = self._build_h3_heading(keyword, h2_heading, row)
                h3_paragraph = self._build_paragraph(
                    keyword=keyword,
                    subtopic=h3_heading,
                    target_words=150,
                )

                html = self._compose_html(h2_heading, h2_paragraph, h3_heading, h3_paragraph)

                df.at[idx, self.REQUIRED_COLUMNS["h2_headline"]] = h2_heading
                df.at[idx, self.H2_TEXT_COLUMN] = h2_paragraph
                df.at[idx, self.REQUIRED_COLUMNS["h3_headline"]] = h3_heading
                df.at[idx, self.H3_TEXT_COLUMN] = h3_paragraph
                df.at[idx, self.REQUIRED_COLUMNS["collection_html"]] = html
                df.at[idx, self.REQUIRED_COLUMNS["processed_at"]] = datetime.now(timezone.utc).isoformat()
                df.at[idx, self.REQUIRED_COLUMNS["row_hash"]] = target_hash

                if self._should_push_to_shopify():
                    self._ensure_shopify_client().upsert_collection(keyword, html)
                    shopify_updates += 1

                processed += 1
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to process row %s (%s)", idx, keyword)
                errors.append(ExcelProcessingError(index=idx, keyword=keyword, message=str(exc)))

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_path = self.settings.output_dir / f"{input_path.stem}__{timestamp}.xlsx"
        df.to_excel(output_path, index=False)
        logger.info(
            "Finished processing %s. processed=%s skipped=%s errors=%s shopify=%s -> %s",
            input_path.name,
            processed,
            skipped,
            len(errors),
            shopify_updates,
            output_path.name,
        )

        return ExcelProcessingResult(
            input_file=input_path,
            output_file=output_path,
            processed_rows=processed,
            skipped_rows=skipped,
            errors=errors,
            shopify_updates=shopify_updates,
        )

    def _build_h2_heading(self, keyword: str, row: pd.Series) -> str:
        override = str(row.get(self.REQUIRED_COLUMNS["h2_override"], "") or "").strip()
        if override:
            return self._validate_heading(override, keyword, forbidden={keyword.lower()})

        generator = self._ensure_generator()
        for attempt in range(3):
            heading = self._validate_heading(
                generator.generate_h2_heading(keyword),
                keyword,
                forbidden={keyword.lower()},
            )
            if heading:
                return heading
            logger.debug("Retrying H2 heading for %s (attempt %s)", keyword, attempt + 1)
        raise ValueError("Unable to produce valid H2 heading")

    def _build_h3_heading(self, keyword: str, h2_heading: str, row: pd.Series) -> str:
        override = str(row.get(self.REQUIRED_COLUMNS["h3_override"], "") or "").strip()
        forbidden = {keyword.lower(), h2_heading.lower()}
        if override:
            return self._validate_heading(override, keyword, forbidden=forbidden)

        generator = self._ensure_generator()
        for attempt in range(3):
            heading = generator.generate_h3_heading(keyword, h2_heading)
            heading = self._validate_heading(heading, keyword, forbidden=forbidden)
            if heading:
                return heading
            logger.debug("Retrying H3 heading for %s (attempt %s)", keyword, attempt + 1)
        raise ValueError("Unable to produce valid H3 heading")

    def _build_paragraph(self, keyword: str, subtopic: str, target_words: int) -> str:
        generator = self._ensure_generator()
        lower_bound = int(target_words * 0.75)
        upper_bound = int(target_words * 1.15)
        for attempt in range(3):
            paragraph = generator.generate_paragraph(keyword, subtopic, str(target_words))
            paragraph = self._normalize_paragraph(paragraph)
            word_count = len(self._strip_html(paragraph).split())
            if lower_bound <= word_count <= upper_bound:
                return paragraph
            logger.debug(
                "Paragraph for keyword=%s subtopic=%s had %s words (target=%s). Retrying...",
                keyword,
                subtopic,
                word_count,
                target_words,
            )
        return paragraph

    def _normalize_paragraph(self, paragraph: str) -> str:
        cleaned = paragraph.strip()
        if not cleaned.lower().startswith("<p"):
            cleaned = f"<p>{cleaned}</p>"
        return cleaned

    def _strip_html(self, html_fragment: str) -> str:
        # Quick stripping: removes tags by replacing with space.
        text = ""
        in_tag = False
        for char in html_fragment:
            if char == "<":
                in_tag = True
                text += " "
            elif char == ">":
                in_tag = False
            elif not in_tag:
                text += char
        return " ".join(text.split())

    def _validate_heading(self, heading: str, keyword: str, forbidden: set[str]) -> str:
        cleaned = heading.strip()
        if not cleaned:
            return ""
        if cleaned.lower() in forbidden:
            return ""
        if len(cleaned) > 60:
            cleaned = cleaned[:60].rstrip()
        return cleaned

    def _compose_html(self, h2: str, h2_p: str, h3: str, h3_p: str) -> str:
        return "\n".join(
            [
                f"<h2>{h2}</h2>",
                h2_p.strip(),
                f"<h3>{h3}</h3>",
                h3_p.strip(),
            ]
        )

    def _should_push_to_shopify(self) -> bool:
        return bool(self._shopify_client_factory)

    def _ensure_generator(self) -> OpenAIContentGenerator:
        if not self._generator:
            self._generator = self._generator_factory()
        return self._generator

    def _ensure_shopify_client(self) -> ShopifyClient:
        if not self._shopify_client:
            if not self._shopify_client_factory:
                raise RuntimeError("Shopify integration not configured")
            self._shopify_client = self._shopify_client_factory()
        return self._shopify_client

    def _normalize_columns(self, df: pd.DataFrame) -> None:
        # Align sample sheet with expected column names.
        if "relevant text 1" in df.columns and self.H2_TEXT_COLUMN not in df.columns:
            df.rename(columns={"relevant text 1": self.H2_TEXT_COLUMN}, inplace=True)

        for alias in self.REQUIRED_COLUMNS.values():
            if alias not in df.columns:
                df[alias] = ""

        if self.H2_TEXT_COLUMN not in df.columns:
            df[self.H2_TEXT_COLUMN] = ""
        if self.H3_TEXT_COLUMN not in df.columns:
            df[self.H3_TEXT_COLUMN] = ""

    def _row_hash(self, row: pd.Series) -> str:
        payload: Dict[str, str] = {
            "keyword": str(row.get(self.REQUIRED_COLUMNS["keyword"], "") or "").strip(),
            "h2_override": str(row.get(self.REQUIRED_COLUMNS["h2_override"], "") or "").strip(),
            "h3_override": str(row.get(self.REQUIRED_COLUMNS["h3_override"], "") or "").strip(),
        }
        serialized = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(serialized).hexdigest()

    def _find_latest_excel(self) -> Optional[Path]:
        excel_files = sorted(
            self.settings.input_dir.glob("*.xlsx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return excel_files[0] if excel_files else None
