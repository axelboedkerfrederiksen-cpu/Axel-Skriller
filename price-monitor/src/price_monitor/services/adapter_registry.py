from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from price_monitor.fetchers.policy import URLPolicyError, validate_url_syntax
from price_monitor.repair.versions import SpecVersionStore, UnknownSpecError
from price_monitor.scrapers.selector import SelectorScraper
from price_monitor.scrapers.sites.books_to_scrape import BOOKS_TO_SCRAPE_V1
from price_monitor.scrapers.spec import SiteSpec
from price_monitor.services.errors import InvalidRequestError, NotFoundError

BUILTIN_SPECS = (BOOKS_TO_SCRAPE_V1,)


class AdapterRegistry:
    """Allowlisted adapter registry backed by immutable declarative versions."""

    def __init__(self, runtime_root: Path, baselines: Iterable[SiteSpec] = BUILTIN_SPECS) -> None:
        specs = tuple(baselines)
        self._store = SpecVersionStore(runtime_root, specs)
        self._baseline_keys = frozenset(spec.key for spec in specs)

    @property
    def version_store(self) -> SpecVersionStore:
        return self._store

    @property
    def keys(self) -> frozenset[str]:
        return self._baseline_keys

    def active_spec(self, key: str) -> SiteSpec:
        try:
            return self._store.get_active(key).spec
        except UnknownSpecError as exc:
            raise NotFoundError(f"unknown scraper adapter {key!r}") from exc

    def spec_at(self, key: str, revision: str) -> SiteSpec:
        try:
            return self._store.get_revision(key, revision).spec
        except UnknownSpecError as exc:
            raise NotFoundError(f"unknown scraper adapter {key!r}@{revision!r}") from exc

    def scraper_at(self, key: str, revision: str) -> SelectorScraper:
        return SelectorScraper(self.spec_at(key, revision))

    def validate_site_configuration(self, *, base_url: str, spec: SiteSpec) -> None:
        try:
            validate_url_syntax(base_url, spec.allowed_hosts)
        except URLPolicyError as exc:
            raise InvalidRequestError(
                f"competitor base URL is not allowed by the selected adapter: {exc}"
            ) from exc
