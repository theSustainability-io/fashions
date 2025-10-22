from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.config import get_settings
from app.services.excel_processor import ExcelProcessingResult, ExcelProcessor
from app.services.shopify_client import ShopifyClient

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Keyword To Shopify Collection Automation")
settings = get_settings()


class ErrorDetail(BaseModel):
    index: int
    keyword: str
    message: str


class ProcessResponse(BaseModel):
    input_file: str
    output_file: str
    processed_rows: int
    skipped_rows: int
    shopify_updates: int
    errors: list[ErrorDetail]


def _create_processor(push_to_shopify: bool) -> ExcelProcessor:
    shopify_factory: Optional[type[ShopifyClient]] = None
    if push_to_shopify:
        if not settings.shopify_store_domain or not settings.shopify_access_token:
            raise HTTPException(
                status_code=400,
                detail="Shopify credentials are missing. Provide SHOPIFY_STORE_DOMAIN and SHOPIFY_ACCESS_TOKEN.",
            )
        shopify_factory = ShopifyClient
    return ExcelProcessor(shopify_client_factory=shopify_factory)


def _convert_result(result: ExcelProcessingResult) -> ProcessResponse:
    return ProcessResponse(
        input_file=str(result.input_file),
        output_file=str(result.output_file),
        processed_rows=result.processed_rows,
        skipped_rows=result.skipped_rows,
        shopify_updates=result.shopify_updates,
        errors=[
            ErrorDetail(index=err.index, keyword=err.keyword, message=err.message)
            for err in result.errors
        ],
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


def _render_upload_page() -> str:
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <title>Keyword Collection Processor</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; line-height: 1.5; }
            form { max-width: 520px; padding: 24px; border: 1px solid #ccc; border-radius: 8px; }
            label { display: block; margin-bottom: 12px; }
            input[type="file"] { margin-top: 8px; }
            button { margin-top: 20px; padding: 10px 18px; }
            code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; display: inline-block; margin-top: 8px; }
        </style>
    </head>
    <body>
        <h1>Keyword Collection Processor</h1>
        <p>Upload an Excel workbook (.xlsx) to generate collection copy. The JSON response includes the saved files and any per-row errors.</p>

        <form action="/process/upload" method="post" enctype="multipart/form-data">
            <label>
                Excel file
                <input type="file" name="file" accept=".xlsx" required />
            </label>
            <label>
                <input type="checkbox" name="push_to_shopify" value="true" />
                Push updates to Shopify
            </label>
            <button type="submit">Process Workbook</button>
        </form>

        <section style="margin-top: 24px;">
            <h2>API Quick Test</h2>
            <p>You can also call the API directly with <code>POST /process/upload</code>. For example:</p>
            <code>curl -X POST -F "file=@sample.xlsx" -F "push_to_shopify=false" http://localhost:8001/process/upload</code>
            <p>Need the OpenAPI explorer? Visit <a href="/docs">/docs</a>.</p>
        </section>
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def homepage() -> str:
    return _render_upload_page()


@app.get("/upload", response_class=HTMLResponse)
async def upload_form() -> str:
    return _render_upload_page()


@app.post("/process/latest", response_model=ProcessResponse)
async def process_latest(push_to_shopify: bool = False) -> ProcessResponse:
    processor = _create_processor(push_to_shopify)
    result = processor.process_latest()
    if not result:
        raise HTTPException(status_code=404, detail="No Excel files found in the input directory.")
    return _convert_result(result)


@app.post("/process/upload", response_model=ProcessResponse)
async def process_upload(
    file: UploadFile = File(...),
    push_to_shopify: bool = Form(False),
) -> ProcessResponse:
    input_path = await _save_upload(file)
    processor = _create_processor(push_to_shopify)
    result = processor.process_file(input_path)
    return _convert_result(result)


async def _save_upload(file: UploadFile) -> Path:
    if not file.filename or not file.filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file.")
    timestamp = int(asyncio.get_event_loop().time() * 1000)
    destination = settings.input_dir / f"{timestamp}_{file.filename}"
    content = await file.read()
    destination.write_bytes(content)
    logger.info("Saved uploaded file to %s", destination)
    return destination


async def _background_runner() -> None:
    logger.info(
        "Background runner started. Checking every %s minutes.",
        settings.poll_interval_minutes,
    )
    while True:
        try:
            push_to_shopify = bool(settings.shopify_store_domain and settings.shopify_access_token)
            processor = _create_processor(push_to_shopify=push_to_shopify)
            result = processor.process_latest()
            if result:
                logger.info("Background run completed: %s", result)
        except HTTPException as http_exc:
            logger.warning("Background runner aborted: %s", http_exc.detail)
        except Exception:  # pylint: disable=broad-except
            logger.exception("Background runner encountered an error.")
        await asyncio.sleep(settings.poll_interval_minutes * 60)


@app.on_event("startup")
async def startup_event() -> None:
    if settings.enable_background_runner:
        asyncio.create_task(_background_runner())
