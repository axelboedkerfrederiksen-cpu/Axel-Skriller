from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from price_monitor.config import Settings
from price_monitor.db.session import SessionFactory, session_scope
from price_monitor.domain.enums import FailureKind, FetchMode, ResultStatus
from price_monitor.domain.types import FetchedPage, utc_now
from price_monitor.fetchers import (
    BrowserFetcher,
    FetchError,
    HttpFetcher,
    RobotsTxtPolicy,
    looks_like_anti_bot_interstitial,
)
from price_monitor.scrapers import ScraperExtractionError
from price_monitor.services.adapter_registry import AdapterRegistry
from price_monitor.services.artifacts import ArtifactReference, LocalArtifactStore
from price_monitor.services.errors import LeaseLostError
from price_monitor.services.queue import ClaimedScrape, ScrapeQueue
from price_monitor.services.results import ResultRecorder
from price_monitor.services.validation import ProductValidator

logger = logging.getLogger(__name__)


class ScrapeWorker:
    """Claims one durable job at a time and runs all network work outside DB transactions."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        settings: Settings,
        registry: AdapterRegistry,
        artifact_store: LocalArtifactStore | None = None,
        validator: ProductValidator | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings
        self.registry = registry
        self.artifacts = artifact_store or LocalArtifactStore(settings.artifact_root)
        self.validator = validator or ProductValidator()
        self.queue = ScrapeQueue(lease_seconds=settings.worker_lease_seconds)
        self.recorder = ResultRecorder(settings)
        self.robots = RobotsTxtPolicy(user_agent=settings.user_agent)
        self._http_fetchers: dict[tuple[float, int, int], HttpFetcher] = {}
        self._browser_fetchers: dict[tuple[float, int], BrowserFetcher] = {}

    async def process_one(self) -> bool:
        with session_scope(self.session_factory) as session:
            claimed = self.queue.claim_next(session)
        if claimed is None:
            return False
        try:
            await self._process_with_renewing_lease(claimed)
        except LeaseLostError as exc:
            # The unfinished result remains reclaimable. In particular, do not
            # finalize it with stale observations after another worker can own it.
            logger.warning("stopped scrape %s safely: %s", claimed.result_id, exc)
        return True

    async def aclose(self) -> None:
        for fetcher in self._http_fetchers.values():
            await fetcher.aclose()
        self._http_fetchers.clear()

    async def _process_with_renewing_lease(self, claimed: ClaimedScrape) -> None:
        """Run a scrape while renewing its lease and enforcing a local deadline."""

        loop = asyncio.get_running_loop()
        deadline = self._lease_watchdog_deadline(claimed.lease_expires_at)
        if deadline <= loop.time():
            raise LeaseLostError("scrape lease is too close to expiration to start safely")

        processing: asyncio.Task[None] | None = None
        heartbeat: asyncio.Task[None] | None = None
        try:
            async with asyncio.timeout_at(deadline) as lease_timeout:
                processing = asyncio.create_task(
                    self._process(claimed),
                    name=f"scrape-{claimed.result_id}",
                )
                heartbeat = asyncio.create_task(
                    self._lease_heartbeat(claimed, lease_timeout),
                    name=f"scrape-lease-{claimed.result_id}",
                )
                done, _ = await asyncio.wait(
                    (processing, heartbeat),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if processing in done:
                    await processing
                    return

                # A heartbeat only terminates when ownership can no longer be
                # guaranteed. Await it to preserve the specific failure reason.
                await heartbeat
                raise LeaseLostError("scrape lease heartbeat stopped unexpectedly")
        except TimeoutError as exc:
            raise LeaseLostError("scrape lease renewal deadline elapsed") from exc
        finally:
            pending = tuple(
                task for task in (processing, heartbeat) if task is not None and not task.done()
            )
            for task in pending:
                task.cancel()
            if pending:
                with suppress(asyncio.CancelledError):
                    await asyncio.gather(*pending, return_exceptions=True)

    async def _lease_heartbeat(
        self,
        claimed: ClaimedScrape,
        lease_timeout: asyncio.Timeout,
    ) -> None:
        """Renew in independent transactions and move the local watchdog forward."""

        while True:
            await asyncio.sleep(self._lease_renewal_interval_seconds())
            try:
                with session_scope(self.session_factory) as session:
                    lease_expires_at = self.queue.renew_lease(
                        session,
                        result_id=claimed.result_id,
                        lease_token=claimed.lease_token,
                    )
            except Exception as exc:
                # Conservatively stop network work while the old lease is still
                # valid instead of risking concurrent reclaim after a DB outage.
                raise LeaseLostError("could not renew scrape lease") from exc
            if lease_expires_at is None:
                raise LeaseLostError("scrape worker no longer owns a live lease")
            lease_timeout.reschedule(self._lease_watchdog_deadline(lease_expires_at))

    def _lease_renewal_interval_seconds(self) -> float:
        return max(1.0, min(30.0, self.settings.worker_lease_seconds / 3))

    def _lease_watchdog_deadline(self, lease_expires_at: datetime) -> float:
        remaining = (lease_expires_at - utc_now()).total_seconds()
        margin = max(1.0, min(5.0, self.settings.worker_lease_seconds / 6))
        return asyncio.get_running_loop().time() + max(0.0, remaining - margin)

    async def _process(self, claimed: ClaimedScrape) -> None:
        started = time.monotonic()
        page: FetchedPage | None = None
        artifact: ArtifactReference | None = None
        try:
            scraper = self.registry.scraper_at(
                claimed.target.adapter_key,
                claimed.target.adapter_revision,
            )
            self._verify_adapter_boundary(claimed, scraper.spec.allowed_hosts)
            page = await self._fetch(claimed)
            if looks_like_anti_bot_interstitial(page.html):
                raise FetchError(
                    "upstream returned an anti-bot or CAPTCHA challenge",
                    kind=FailureKind.ANTI_BOT,
                    url=str(page.final_url),
                    status_code=page.status_code,
                    retryable=False,
                )
            artifact = self.artifacts.store_html(
                site_key=claimed.target.adapter_key,
                artifact_id=str(claimed.result_id),
                html=page.html,
            )
            extracted = scraper.extract(page)
            validation = self.validator.validate(extracted, claimed.target)
            with session_scope(self.session_factory) as session:
                self._require_live_lease(session, claimed)
                if validation.accepted:
                    self.recorder.record_success(
                        session,
                        result_id=claimed.result_id,
                        lease_token=claimed.lease_token,
                        extracted=extracted,
                        validation=validation,
                        duration_ms=self._elapsed_ms(started),
                        http_status=page.status_code,
                        html_artifact_uri=artifact.relative_path,
                        html_sha256=artifact.content_sha256,
                    )
                else:
                    self.recorder.record_invalid(
                        session,
                        result_id=claimed.result_id,
                        lease_token=claimed.lease_token,
                        extracted=extracted,
                        validation=validation,
                        duration_ms=self._elapsed_ms(started),
                        http_status=page.status_code,
                        html_artifact_uri=artifact.relative_path,
                        html_sha256=artifact.content_sha256,
                    )
        except LeaseLostError:
            raise
        except ScraperExtractionError as exc:
            await self._record_failure(
                claimed,
                failure_kind=FailureKind.EXTRACTION,
                failure_code=f"EXTRACTION_{(exc.field or 'UNKNOWN').upper()}",
                message=str(exc),
                started=started,
                page=page,
                artifact=artifact,
            )
        except FetchError as exc:
            status = (
                ResultStatus.TIMED_OUT if "timeout" in str(exc).casefold() else ResultStatus.FAILED
            )
            await self._record_failure(
                claimed,
                failure_kind=exc.kind,
                failure_code=f"FETCH_{exc.kind.value.upper()}",
                message=str(exc),
                started=started,
                status=status,
                http_status=exc.status_code,
                page=page,
                artifact=artifact,
            )
        except Exception as exc:
            logger.exception("unexpected scrape worker failure for result %s", claimed.result_id)
            await self._record_failure(
                claimed,
                failure_kind=FailureKind.INTERNAL,
                failure_code="WORKER_INTERNAL_ERROR",
                message=f"{type(exc).__name__}: {exc}",
                started=started,
                page=page,
                artifact=artifact,
            )

    async def _fetch(self, claimed: ClaimedScrape) -> FetchedPage:
        http_fetcher = self._http_fetcher(claimed)
        url = str(claimed.target.url)
        if self.settings.respect_robots_txt:
            await self.robots.enforce(
                fetcher=http_fetcher,
                url=url,
                allowed_hosts=claimed.target.allowed_hosts,
            )

        if claimed.target.fetch_mode == FetchMode.HTTP:
            return await http_fetcher.fetch(url, allowed_hosts=claimed.target.allowed_hosts)
        if claimed.target.fetch_mode == FetchMode.BROWSER:
            host = urlsplit(url).hostname or ""
            await http_fetcher.wait_for_host(host)
            browser_fetcher = self._browser_fetcher(claimed)
            return await browser_fetcher.fetch(url, allowed_hosts=claimed.target.allowed_hosts)
        raise FetchError(
            "adapter requested an unsupported fetch mode",
            kind=FailureKind.INTERNAL,
            url=url,
        )

    def _http_fetcher(self, claimed: ClaimedScrape) -> HttpFetcher:
        key = (
            float(claimed.timeout_seconds),
            claimed.maximum_retries,
            claimed.minimum_request_interval_ms,
        )
        fetcher = self._http_fetchers.get(key)
        if fetcher is None:
            fetcher = HttpFetcher.from_settings(
                self.settings,
                timeout_seconds=claimed.timeout_seconds,
                maximum_retries=claimed.maximum_retries,
                minimum_request_interval_seconds=claimed.minimum_request_interval_ms / 1_000,
            )
            self._http_fetchers[key] = fetcher
        return fetcher

    def _browser_fetcher(self, claimed: ClaimedScrape) -> BrowserFetcher:
        key = (float(claimed.timeout_seconds), self.settings.maximum_response_bytes)
        fetcher = self._browser_fetchers.get(key)
        if fetcher is None:
            fetcher = BrowserFetcher(
                user_agent=self.settings.user_agent,
                timeout_seconds=claimed.timeout_seconds,
                maximum_response_bytes=self.settings.maximum_response_bytes,
            )
            self._browser_fetchers[key] = fetcher
        return fetcher

    async def _record_failure(
        self,
        claimed: ClaimedScrape,
        *,
        failure_kind: FailureKind,
        failure_code: str,
        message: str,
        started: float,
        status: ResultStatus = ResultStatus.FAILED,
        http_status: int | None = None,
        page: FetchedPage | None,
        artifact: ArtifactReference | None,
    ) -> None:
        if page is not None and artifact is None:
            try:
                artifact = self.artifacts.store_html(
                    site_key=claimed.target.adapter_key,
                    artifact_id=str(claimed.result_id),
                    html=page.html,
                )
            except Exception:
                logger.exception("failed to retain diagnostic HTML for %s", claimed.result_id)
        with session_scope(self.session_factory) as session:
            self._require_live_lease(session, claimed)
            self.recorder.record_failure(
                session,
                result_id=claimed.result_id,
                lease_token=claimed.lease_token,
                failure_kind=failure_kind,
                failure_code=failure_code,
                message=message,
                duration_ms=self._elapsed_ms(started),
                status=status,
                http_status=http_status or (page.status_code if page else None),
                html_artifact_uri=artifact.relative_path if artifact else None,
                html_sha256=artifact.content_sha256 if artifact else None,
            )

    def _require_live_lease(self, session: Session, claimed: ClaimedScrape) -> None:
        lease_expires_at = self.queue.renew_lease(
            session,
            result_id=claimed.result_id,
            lease_token=claimed.lease_token,
        )
        if lease_expires_at is None:
            raise LeaseLostError("scrape worker no longer owns a live lease")

    def _verify_adapter_boundary(
        self, claimed: ClaimedScrape, adapter_hosts: tuple[str, ...]
    ) -> None:
        if (
            claimed.target.fetch_mode
            != self.registry.spec_at(
                claimed.target.adapter_key, claimed.target.adapter_revision
            ).fetch_mode
        ):
            raise FetchError(
                "queued fetch mode differs from the versioned adapter",
                kind=FailureKind.INTERNAL,
                url=str(claimed.target.url),
            )
        if not set(claimed.target.allowed_hosts).issubset(adapter_hosts):
            raise FetchError(
                "target hostname is outside the versioned adapter allowlist",
                kind=FailureKind.ACCESS_DENIED,
                url=str(claimed.target.url),
            )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, round((time.monotonic() - started) * 1_000))


def default_worker(
    *,
    session_factory: SessionFactory,
    settings: Settings,
    adapter_runtime_root: Path | None = None,
) -> ScrapeWorker:
    registry = AdapterRegistry(adapter_runtime_root or settings.adapter_runtime_root)
    return ScrapeWorker(
        session_factory=session_factory,
        settings=settings,
        registry=registry,
    )
