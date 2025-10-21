from __future__ import annotations

import logging
from typing import Optional

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


class ShopifyClient:
    """Minimal Shopify REST client for working with custom collections."""

    API_VERSION = "2024-01"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.shopify_store_domain or not settings.shopify_access_token:
            raise RuntimeError("Shopify credentials are missing.")
        self._store_domain = settings.shopify_store_domain.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Shopify-Access-Token": settings.shopify_access_token,
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"https://{self._store_domain}/admin/api/{self.API_VERSION}/{path}"

    def upsert_collection(self, title: str, html_body: str) -> Optional[int]:
        """Create or update a custom collection."""
        existing_id = self._find_collection_id(title)
        payload = {"custom_collection": {"title": title, "body_html": html_body}}

        if existing_id:
            url = self._url(f"custom_collections/{existing_id}.json")
            response = self._session.put(url, json=payload, timeout=30)
            logger.info("Updated Shopify collection %s (id=%s)", title, existing_id)
        else:
            url = self._url("custom_collections.json")
            response = self._session.post(url, json=payload, timeout=30)
            logger.info("Created Shopify collection %s", title)

        response.raise_for_status()
        data = response.json()
        return data.get("custom_collection", {}).get("id")

    def _find_collection_id(self, title: str) -> Optional[int]:
        url = self._url(f"custom_collections.json?title={requests.utils.quote(title)}")
        response = self._session.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()
        collections = data.get("custom_collections", [])
        return collections[0]["id"] if collections else None
