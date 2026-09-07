from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import cast
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from price_monitor.api.dashboard_schemas import (
    DashboardCompetitorOffer,
    DashboardCompetitorSummary,
    DashboardFreshness,
    DashboardHealth,
    DashboardOverview,
    DashboardPriceChangeEvent,
    DashboardPriceHistoryPoint,
    DashboardProduct,
    DashboardProductComparison,
    DashboardProductDetail,
    DashboardSiteMonitorStatus,
    MonitorStatus,
)
from price_monitor.db.models import (
    Competitor,
    CompetitorProduct,
    Customer,
    PriceHistory,
    Product,
    ScrapeResult,
)
from price_monitor.domain.enums import Availability, ChangeKind, ResultStatus
from price_monitor.domain.types import utc_now
from price_monitor.services.errors import NotFoundError

_TERMINAL_RESULTS = (
    ResultStatus.SUCCEEDED,
    ResultStatus.INVALID,
    ResultStatus.FAILED,
    ResultStatus.TIMED_OUT,
)


def _as_float(value: object | None) -> float | None:
    return None if value is None else float(cast(float, value))


def _availability(value: Availability | None) -> bool | None:
    if value == Availability.IN_STOCK:
        return True
    if value == Availability.OUT_OF_STOCK:
        return False
    return None


def _worst_status(statuses: list[MonitorStatus]) -> MonitorStatus:
    if "failed" in statuses:
        return "failed"
    if "stale" in statuses or not statuses:
        return "stale"
    return "healthy"


def _target_last_checked(target: CompetitorProduct) -> datetime:
    return target.last_attempt_at or target.current_observed_at or target.updated_at


def _target_last_success(target: CompetitorProduct) -> datetime | None:
    return target.last_success_at or target.current_observed_at


def _target_status(target: CompetitorProduct, now: datetime) -> MonitorStatus:
    if target.consecutive_failures > 0:
        return "failed"
    last_success = target.last_success_at or target.current_observed_at
    if last_success is None:
        return "stale"
    interval = target.schedule_interval_seconds or target.competitor.schedule_interval_seconds
    stale_after = timedelta(seconds=max(interval * 2, 3_600))
    return "stale" if now - last_success > stale_after else "healthy"


class DashboardService:
    """Build customer-scoped dashboard read models from accepted monitoring data."""

    @staticmethod
    def overview(
        session: Session,
        customer_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DashboardOverview:
        reference_time = now or utc_now()
        customer = DashboardService._customer(session, customer_id)
        products = DashboardService._products(session, customer_id)
        histories = DashboardService._histories(
            session,
            customer_id,
            since=reference_time - timedelta(hours=24),
        )
        events = DashboardService._events(histories)
        comparisons = DashboardService._comparisons(
            products,
            customer.default_currency,
            events,
            reference_time,
        )
        targets = DashboardService._targets(products)
        statuses = [_target_status(target, reference_time) for target in targets]
        healthy = statuses.count("healthy")
        successful_updates = [
            timestamp
            for target in targets
            if (timestamp := _target_last_success(target)) is not None
        ]
        price_events = [
            event for event in events if event.event_type in {"price_drop", "price_increase"}
        ]
        largest_gaps = sorted(
            (
                comparison
                for comparison in comparisons
                if comparison.difference_amount is not None and comparison.difference_amount > 0
            ),
            key=lambda comparison: comparison.difference_amount or 0,
            reverse=True,
        )[:5]
        return DashboardOverview(
            total_products=len(products),
            monitored_offers=len(targets),
            price_changes_24h=len(price_events),
            overpriced_products=sum(
                comparison.difference_amount is not None and comparison.difference_amount > 0
                for comparison in comparisons
            ),
            cheapest_products=sum(
                comparison.is_customer_cheapest is True for comparison in comparisons
            ),
            stale_or_failed=sum(status != "healthy" for status in statuses),
            recent_events=events[:6],
            largest_gaps=largest_gaps,
            freshness=DashboardFreshness(
                status=_worst_status(statuses),
                last_successful_update=max(successful_updates, default=None),
                healthy_percentage=round(healthy / len(statuses) * 100) if statuses else 0,
                checked_last_hour=sum(
                    target.last_attempt_at is not None
                    and target.last_attempt_at >= reference_time - timedelta(hours=1)
                    for target in targets
                ),
            ),
        )

    @staticmethod
    def products(
        session: Session,
        customer_id: UUID,
        *,
        now: datetime | None = None,
    ) -> list[DashboardProductComparison]:
        reference_time = now or utc_now()
        customer = DashboardService._customer(session, customer_id)
        products = DashboardService._products(session, customer_id)
        histories = DashboardService._histories(
            session,
            customer_id,
            since=reference_time - timedelta(hours=24),
        )
        return DashboardService._comparisons(
            products,
            customer.default_currency,
            DashboardService._events(histories),
            reference_time,
        )

    @staticmethod
    def product_detail(
        session: Session,
        customer_id: UUID,
        product_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DashboardProductDetail:
        reference_time = now or utc_now()
        customer = DashboardService._customer(session, customer_id)
        products = DashboardService._products(session, customer_id, product_id=product_id)
        if not products:
            raise NotFoundError(f"Product {product_id} was not found for customer {customer_id}")
        product = products[0]
        histories = DashboardService._histories(
            session,
            customer_id,
            product_id=product_id,
            since=reference_time - timedelta(days=21),
        )
        events = DashboardService._events(histories)
        comparison = DashboardService._comparison(
            product,
            customer.default_currency,
            events,
            reference_time,
        )
        history = DashboardService._history_points(product, histories)
        return DashboardProductDetail(comparison=comparison, history=history, events=events)

    @staticmethod
    def competitors(
        session: Session,
        customer_id: UUID,
        *,
        now: datetime | None = None,
    ) -> list[DashboardCompetitorSummary]:
        reference_time = now or utc_now()
        customer = DashboardService._customer(session, customer_id)
        products = DashboardService._products(session, customer_id)
        comparisons = DashboardService._comparisons(
            products,
            customer.default_currency,
            [],
            reference_time,
        )
        competitors = DashboardService._competitors(session, customer_id)
        targets = DashboardService._targets(products)
        targets_by_competitor: dict[UUID, list[CompetitorProduct]] = defaultdict(list)
        for target in targets:
            targets_by_competitor[target.competitor_id].append(target)
        result_stats = DashboardService._result_stats(session, customer_id)

        summaries: list[DashboardCompetitorSummary] = []
        for competitor in competitors:
            site_targets = targets_by_competitor[competitor.id]
            differences: list[float] = []
            for target in site_targets:
                own_price = target.product.current_own_price
                if target.current_price is None or own_price is None or own_price == 0:
                    continue
                differences.append(float((target.current_price - own_price) / own_price * 100))
            site_statuses = [_target_status(target, reference_time) for target in site_targets]
            last_successes = [
                timestamp
                for target in site_targets
                if (timestamp := _target_last_success(target)) is not None
            ]
            attempts, successes = result_stats.get(competitor.id, (0, 0))
            summaries.append(
                DashboardCompetitorSummary(
                    id=competitor.id,
                    name=competitor.name,
                    monitored_products=len(site_targets),
                    average_difference_percentage=(
                        sum(differences) / len(differences) if differences else None
                    ),
                    cheapest_products=sum(
                        comparison.cheapest_competitor is not None
                        and comparison.cheapest_competitor.competitor_id == competitor.id
                        for comparison in comparisons
                    ),
                    last_successful_scrape=max(last_successes, default=None),
                    status=_worst_status(site_statuses),
                    success_rate=round(successes / attempts * 100) if attempts else 0,
                )
            )
        return summaries

    @staticmethod
    def health(
        session: Session,
        customer_id: UUID,
        *,
        now: datetime | None = None,
    ) -> DashboardHealth:
        reference_time = now or utc_now()
        DashboardService._customer(session, customer_id)
        products = DashboardService._products(session, customer_id)
        competitors = DashboardService._competitors(session, customer_id)
        targets = DashboardService._targets(products)
        targets_by_competitor: dict[UUID, list[CompetitorProduct]] = defaultdict(list)
        for target in targets:
            targets_by_competitor[target.competitor_id].append(target)

        sites: list[DashboardSiteMonitorStatus] = []
        all_last_successes: list[datetime] = []
        all_statuses: list[MonitorStatus] = []
        for competitor in competitors:
            site_targets = targets_by_competitor[competitor.id]
            statuses = [_target_status(target, reference_time) for target in site_targets]
            all_statuses.extend(statuses)
            last_successes = [
                timestamp
                for target in site_targets
                if (timestamp := _target_last_success(target)) is not None
            ]
            all_last_successes.extend(last_successes)
            sites.append(
                DashboardSiteMonitorStatus(
                    id=competitor.id,
                    name=competitor.name,
                    healthy_monitors=statuses.count("healthy"),
                    stale_monitors=statuses.count("stale"),
                    failed_checks=statuses.count("failed"),
                    last_successful_update=max(last_successes, default=None),
                    status=_worst_status(statuses),
                )
            )
        return DashboardHealth(
            healthy_monitors=all_statuses.count("healthy"),
            stale_monitors=all_statuses.count("stale"),
            failed_checks=all_statuses.count("failed"),
            total_monitors=len(all_statuses),
            last_successful_update=max(all_last_successes, default=None),
            sites=sites,
        )

    @staticmethod
    def _customer(session: Session, customer_id: UUID) -> Customer:
        customer = session.get(Customer, customer_id)
        if customer is None or not customer.is_active:
            raise NotFoundError(f"Customer {customer_id} was not found")
        return customer

    @staticmethod
    def _products(
        session: Session,
        customer_id: UUID,
        *,
        product_id: UUID | None = None,
    ) -> list[Product]:
        statement = (
            select(Product)
            .options(
                selectinload(Product.competitor_products).joinedload(CompetitorProduct.competitor)
            )
            .where(Product.customer_id == customer_id, Product.is_active.is_(True))
            .order_by(Product.name)
        )
        if product_id is not None:
            statement = statement.where(Product.id == product_id)
        return list(session.scalars(statement).unique())

    @staticmethod
    def _competitors(session: Session, customer_id: UUID) -> list[Competitor]:
        return list(
            session.scalars(
                select(Competitor)
                .where(
                    Competitor.customer_id == customer_id,
                    Competitor.is_active.is_(True),
                )
                .order_by(Competitor.name)
            )
        )

    @staticmethod
    def _targets(products: list[Product]) -> list[CompetitorProduct]:
        return [
            target
            for product in products
            for target in product.competitor_products
            if target.is_active and target.competitor.is_active
        ]

    @staticmethod
    def _histories(
        session: Session,
        customer_id: UUID,
        *,
        since: datetime,
        product_id: UUID | None = None,
    ) -> list[PriceHistory]:
        statement = (
            select(PriceHistory)
            .join(CompetitorProduct, PriceHistory.competitor_product_id == CompetitorProduct.id)
            .join(Product, CompetitorProduct.product_id == Product.id)
            .join(Competitor, CompetitorProduct.competitor_id == Competitor.id)
            .options(
                joinedload(PriceHistory.competitor_product).joinedload(CompetitorProduct.product),
                joinedload(PriceHistory.competitor_product).joinedload(
                    CompetitorProduct.competitor
                ),
            )
            .where(
                Product.customer_id == customer_id,
                Product.is_active.is_(True),
                CompetitorProduct.is_active.is_(True),
                Competitor.is_active.is_(True),
                PriceHistory.observed_at >= since,
            )
            .order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc())
        )
        if product_id is not None:
            statement = statement.where(Product.id == product_id)
        return list(session.scalars(statement))

    @staticmethod
    def _events(histories: list[PriceHistory]) -> list[DashboardPriceChangeEvent]:
        events: list[DashboardPriceChangeEvent] = []
        previous_availability: dict[UUID, Availability] = {}
        for history in sorted(histories, key=lambda item: (item.observed_at, item.id)):
            target = history.competitor_product
            if history.change_kind in {ChangeKind.DECREASE, ChangeKind.INCREASE}:
                events.append(
                    DashboardPriceChangeEvent(
                        id=f"price-{history.id}",
                        product_id=target.product_id,
                        product_name=target.product.name,
                        competitor_id=target.competitor_id,
                        competitor_name=target.competitor.name,
                        currency=history.currency,
                        old_price=_as_float(history.previous_price),
                        new_price=float(history.price),
                        percentage_change=_as_float(history.change_percent),
                        timestamp=history.observed_at,
                        event_type=(
                            "price_drop"
                            if history.change_kind == ChangeKind.DECREASE
                            else "price_increase"
                        ),
                    )
                )
            prior = previous_availability.get(target.id)
            if prior != history.availability and prior is not None:
                if history.availability == Availability.OUT_OF_STOCK:
                    event_type = "out_of_stock"
                elif (
                    prior == Availability.OUT_OF_STOCK
                    and history.availability == Availability.IN_STOCK
                ):
                    event_type = "back_in_stock"
                else:
                    event_type = None
                if event_type is not None:
                    events.append(
                        DashboardPriceChangeEvent(
                            id=f"availability-{history.id}",
                            product_id=target.product_id,
                            product_name=target.product.name,
                            competitor_id=target.competitor_id,
                            competitor_name=target.competitor.name,
                            currency=history.currency,
                            timestamp=history.observed_at,
                            event_type=event_type,
                        )
                    )
            previous_availability[target.id] = history.availability
        return sorted(events, key=lambda event: event.timestamp, reverse=True)

    @staticmethod
    def _comparisons(
        products: list[Product],
        default_currency: str,
        events: list[DashboardPriceChangeEvent],
        now: datetime,
    ) -> list[DashboardProductComparison]:
        events_by_product: dict[UUID, list[DashboardPriceChangeEvent]] = defaultdict(list)
        for event in events:
            events_by_product[event.product_id].append(event)
        return [
            DashboardService._comparison(
                product,
                default_currency,
                events_by_product[product.id],
                now,
            )
            for product in products
        ]

    @staticmethod
    def _comparison(
        product: Product,
        default_currency: str,
        events: list[DashboardPriceChangeEvent],
        now: datetime,
    ) -> DashboardProductComparison:
        targets = [
            target
            for target in product.competitor_products
            if target.is_active and target.competitor.is_active
        ]
        offers = [
            DashboardService._offer(target, product, default_currency, now) for target in targets
        ]
        available_offers = [
            offer for offer in offers if offer.price is not None and offer.in_stock is True
        ]
        cheapest = min(
            available_offers,
            key=lambda offer: offer.price if offer.price is not None else float("inf"),
            default=None,
        )
        own_price = _as_float(product.current_own_price)
        cheapest_price = cheapest.price if cheapest is not None else None
        if own_price is None or cheapest_price is None:
            difference = None
            percentage = None
            rank = None
            is_cheapest = None
        else:
            difference = own_price - cheapest_price
            percentage = difference / cheapest_price * 100 if cheapest_price else None
            rank = 1 + sum(
                offer.price is not None and offer.price < own_price for offer in available_offers
            )
            is_cheapest = difference <= 0
        statuses = [offer.status for offer in offers]
        last_checked = max(
            (_target_last_checked(target) for target in targets),
            default=product.updated_at,
        )
        recent_cutoff = now - timedelta(hours=24)
        recent_events = [event for event in events if event.timestamp >= recent_cutoff]
        return DashboardProductComparison(
            product=DashboardProduct(
                id=product.id,
                name=product.name,
                sku=product.sku or "—",
                customer_price=own_price,
                currency=product.currency or default_currency,
                in_stock=None,
                last_checked=last_checked,
            ),
            competitor_offers=offers,
            cheapest_competitor=cheapest,
            cheapest_price=cheapest_price,
            customer_price=own_price,
            difference_amount=difference,
            difference_percentage=percentage,
            customer_rank=rank,
            is_customer_cheapest=is_cheapest,
            has_recent_competitor_drop=any(
                event.event_type == "price_drop" for event in recent_events
            ),
            has_recent_competitor_increase=any(
                event.event_type == "price_increase" for event in recent_events
            ),
            status=_worst_status(statuses),
        )

    @staticmethod
    def _offer(
        target: CompetitorProduct,
        product: Product,
        default_currency: str,
        now: datetime,
    ) -> DashboardCompetitorOffer:
        return DashboardCompetitorOffer(
            id=target.id,
            product_id=product.id,
            competitor_id=target.competitor_id,
            competitor_name=target.competitor.name,
            price=_as_float(target.current_price),
            currency=target.current_currency or product.currency or default_currency,
            in_stock=_availability(target.current_availability),
            product_url=target.product_url,
            last_checked=_target_last_checked(target),
            status=_target_status(target, now),
        )

    @staticmethod
    def _history_points(
        product: Product,
        histories: list[PriceHistory],
    ) -> list[DashboardPriceHistoryPoint]:
        ordered = sorted(histories, key=lambda history: (history.observed_at, history.id))
        points = [
            DashboardPriceHistoryPoint(
                timestamp=history.observed_at,
                price=float(history.price),
                source_type="competitor",
                competitor_id=history.competitor_product.competitor_id,
                competitor_name=history.competitor_product.competitor.name,
            )
            for history in ordered
        ]
        if product.current_own_price is not None:
            timestamps = sorted({history.observed_at for history in ordered}) or [
                product.updated_at
            ]
            points.extend(
                DashboardPriceHistoryPoint(
                    timestamp=timestamp,
                    price=float(product.current_own_price),
                    source_type="customer",
                )
                for timestamp in timestamps
            )
        return sorted(points, key=lambda point: point.timestamp)

    @staticmethod
    def _result_stats(session: Session, customer_id: UUID) -> dict[UUID, tuple[int, int]]:
        rows = session.execute(
            select(
                CompetitorProduct.competitor_id,
                func.count(ScrapeResult.id),
                func.sum(case((ScrapeResult.status == ResultStatus.SUCCEEDED, 1), else_=0)),
            )
            .join(
                ScrapeResult,
                ScrapeResult.competitor_product_id == CompetitorProduct.id,
            )
            .join(Product, CompetitorProduct.product_id == Product.id)
            .join(Competitor, CompetitorProduct.competitor_id == Competitor.id)
            .where(
                Product.customer_id == customer_id,
                Product.is_active.is_(True),
                CompetitorProduct.is_active.is_(True),
                Competitor.is_active.is_(True),
                ScrapeResult.status.in_(_TERMINAL_RESULTS),
            )
            .group_by(CompetitorProduct.competitor_id)
        )
        return {
            competitor_id: (int(attempts), int(successes or 0))
            for competitor_id, attempts, successes in rows
        }
