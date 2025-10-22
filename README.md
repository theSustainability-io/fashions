# Keyword to Shopify Collection Automation

FastAPI microservice that ingests Excel keyword lists, generates SEO-friendly collection content with OpenAI, and optionally syncs the results to Shopify collections. Designed for deployment on Render.com.

## Project Layout

```
app/
  main.py                # FastAPI app and HTTP routes
  config.py              # Environment-driven settings
  services/
    excel_processor.py   # Spreadsheet orchestration and HTML assembly
    openai_client.py     # Wrapper around OpenAI Responses API
    shopify_client.py    # Minimal Shopify custom collection client
requirements.txt         # Python dependencies
```

## Prerequisites

- Python 3.10+
- OpenAI API key with access to the Responses API (`OPENAI_API_KEY`)
- Optional: Shopify custom collection access token
- Excel input files saved as `.xlsx`

## Configuration

Set environment variables (Render dashboard or local `.env` file):

| Variable | Description | Required |
| --- | --- | --- |
| `OPENAI_API_KEY` | OpenAI secret key. | Yes (unless you only test skipping generations) |
| `OPENAI_MODEL` | Responses model name. Default `gpt-4.1-mini`. | No |
| `SHOPIFY_STORE_DOMAIN` | Shopify store domain, e.g. `example.myshopify.com`. | Only for Shopify sync |
| `SHOPIFY_ACCESS_TOKEN` | Admin API access token. | Only for Shopify sync |
| `INPUT_DIR` | Directory to watch for Excel uploads. Default `./input`. | No |
| `OUTPUT_DIR` | Directory where processed workbooks are stored. Default `./output`. | No |
| `POLL_INTERVAL_MINUTES` | Interval for the optional background watcher. Default `1440`. | No |
| `ENABLE_BACKGROUND_RUNNER` | Set to `true` to enable periodic polling. | No |

Both input and output folders are created automatically on startup.

## Running Locally

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Export your secrets (or place them in a `.env` file).
4. Start the API server:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

## API Usage

- `GET /` or `GET /upload` - simple HTML form for manual testing.
- `GET /health` - quick health probe.
- `POST /process/latest?push_to_shopify=false` - process the most recent Excel file within `INPUT_DIR`.
- `POST /process/upload` - multipart form upload with fields:
  - `file`: the Excel workbook (`.xlsx`).
  - `push_to_shopify` (optional): `true/false` toggle.

Sample `curl` request:
```bash
curl -X POST \
  -F "file=@sample.xlsx" \
  -F "push_to_shopify=true" \
  http://localhost:8000/process/upload
```

Responses follow this schema:
```json
{
  "input_file": "input/1712091550000_sample.xlsx",
  "output_file": "output/sample__20240326_140501.xlsx",
  "processed_rows": 12,
  "skipped_rows": 3,
  "shopify_updates": 12,
  "errors": [
    {"index": 4, "keyword": "blue prom dresses", "message": "Unable to produce valid H2 heading"}
  ]
}
```

Errors are collected per-row so one failure never halts the full batch.

## Content Generation Rules

- H2 and H3 headings stay under 60 characters and avoid repeating the main keyword verbatim.
- Paragraph lengths aim for ~200 words (H2) and 120-180 words (H3), retrying up to three times if needed.
- Paragraphs are returned as sanitized `<p>` blocks, and final HTML is stored in the `collection_html` column alongside `_processed_at` and `_row_hash` tracking fields.

## Excel Expectations

The processor normalizes against the following headers:

| Column | Purpose |
| --- | --- |
| `keywords` | Primary collection keyword. |
| `<h2> headline` | Generated or override heading for the H2 section. |
| `relevant text 2` | Paragraph for the H2 section. |
| `<h3> headline` | Generated or override heading for the H3 section. |
| `relevant text 3` | Paragraph for the H3 section. |
| `h2_overrides`, `h3_overrides` | Optional manual headings to bypass generation. |
| `collection_html`, `_processed_at`, `_row_hash` | Automation metadata. |

Any legacy column named `relevant text 1` is automatically renamed to `relevant text 2` during processing.

## Shopify Sync

When `push_to_shopify=true` **and** valid credentials are configured, each processed keyword is upserted as a custom collection: existing collections (matching by title) are updated, otherwise new ones are created.

## Deployment Notes (Render)

1. Create a new Web Service on Render pointing to your GitHub repo.
2. Either import the provided `render.yaml` (Render → New → Blueprint) or set the options manually:
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - (Optional) Attach a persistent disk and point `INPUT_DIR` / `OUTPUT_DIR` to the mount path so uploads survive restarts.
3. Configure environment variables (OpenAI, Shopify, etc.) in Render's dashboard.
4. (Optional) Enable autoscaling or cron jobs if you prefer scheduled runs instead of the background watcher.

## Next Steps

- Add unit tests around the Excel processing rules.
- Layer in authentication (API key or Basic Auth) if the service will be public.
- Extend Shopify sync to support Smart Collections or metafields if needed.
