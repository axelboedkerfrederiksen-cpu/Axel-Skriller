from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from price_monitor.api.alert_schemas import AlertRuleCreate, AlertRuleUpdate
from price_monitor.db.alert_models import AlertDirection, AlertRule
from price_monitor.db.models import CompetitorProduct, Customer, PriceHistory, Product
from price_monitor.domain.enums import ChangeKind
from price_monitor.services.errors import ConflictError, InvalidRequestError, NotFoundError

AlertEvaluationState = Literal["disabled", "waiting", "clear", "triggered"]


@dataclass(frozen=True, slots=True)
class AlertEvaluation:
    state: AlertEvaluationState
    last_checked_at: datetime | None = None
    last_triggered_at: datetime | None = None
    competitor_product_id: UUID | None = None
    price: Decimal | None = None
    previous_price: Decimal | None = None
    currency: str | None = None
    change_percent: Decimal | None = None


class AlertService:
    """Own alert mutations and derive rule state from accepted price history."""

    @staticmethod
    def create(
        session: Session,
        customer_id: UUID,
        request: AlertRuleCreate,
    ) -> AlertRule:
        AlertService._require_customer(session, customer_id)
        product = AlertService._require_product(session, request.product_id)
        if product.customer_id != customer_id:
            raise InvalidRequestError("product must belong to the selected customer")

        rule = AlertRule(
            customer_id=customer_id,
            product_id=product.id,
            direction=request.direction,
            threshold_percent=request.threshold_percent,
        )
        session.add(rule)
        AlertService._flush(session)
        return rule

    @staticmethod
    def list(session: Session, customer_id: UUID) -> list[AlertRule]:
        AlertService._require_customer(session, customer_id)
        return list(
            session.scalars(
                select(AlertRule)
                .where(AlertRule.customer_id == customer_id)
                .order_by(AlertRule.created_at.desc(), AlertRule.id)
            )
        )

    @staticmethod
    def get(session: Session, rule_id: UUID) -> AlertRule:
        rule = session.get(AlertRule, rule_id)
        if rule is None:
            raise NotFoundError(f"AlertRule {rule_id} was not found")
        return rule

    @staticmethod
    def update(
        session: Session,
        rule_id: UUID,
        request: AlertRuleUpdate,
    ) -> AlertRule:
        rule = AlertService.get(session, rule_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        AlertService._flush(session)
        return rule

    @staticmethod
    def delete(session: Session, rule_id: UUID) -> None:
        session.delete(AlertService.get(session, rule_id))
        AlertService._flush(session)

    @staticmethod
    def evaluate(session: Session, rule: AlertRule) -> AlertEvaluation:
        history_for_product = (
            select(PriceHistory)
            .join(
                CompetitorProduct,
                PriceHistory.competitor_product_id == CompetitorProduct.id,
            )
            .where(
                CompetitorProduct.product_id == rule.product_id,
                PriceHistory.observed_at >= rule.created_at,
            )
        )
        latest = session.scalar(
            history_for_product.order_by(
                PriceHistory.observed_at.desc(),
                PriceHistory.id.desc(),
            ).limit(1)
        )

        matching = session.scalar(
            history_for_product.where(
                AlertService._matching_change(rule.direction, rule.threshold_percent)
            )
            .order_by(PriceHistory.observed_at.desc(), PriceHistory.id.desc())
            .limit(1)
        )

        if not rule.is_active:
            state: AlertEvaluationState = "disabled"
        elif latest is None:
            state = "waiting"
        elif matching is None:
            state = "clear"
        else:
            state = "triggered"

        return AlertEvaluation(
            state=state,
            last_checked_at=latest.observed_at if latest else None,
            last_triggered_at=matching.observed_at if matching else None,
            competitor_product_id=matching.competitor_product_id if matching else None,
            price=matching.price if matching else None,
            previous_price=matching.previous_price if matching else None,
            currency=matching.currency if matching else None,
            change_percent=matching.change_percent if matching else None,
        )

    @staticmethod
    def _matching_change(
        direction: AlertDirection,
        threshold: Decimal,
    ) -> ColumnElement[bool]:
        if direction == "decrease":
            return (PriceHistory.change_kind == ChangeKind.DECREASE) & (
                PriceHistory.change_percent <= -threshold
            )
        if direction == "increase":
            return (PriceHistory.change_kind == ChangeKind.INCREASE) & (
                PriceHistory.change_percent >= threshold
            )
        return PriceHistory.change_kind.in_((ChangeKind.DECREASE, ChangeKind.INCREASE)) & (
            func.abs(PriceHistory.change_percent) >= threshold
        )

    @staticmethod
    def _require_customer(session: Session, customer_id: UUID) -> Customer:
        customer = session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(f"Customer {customer_id} was not found")
        return customer

    @staticmethod
    def _require_product(session: Session, product_id: UUID) -> Product:
        product = session.get(Product, product_id)
        if product is None:
            raise NotFoundError(f"Product {product_id} was not found")
        return product

    @staticmethod
    def _flush(session: Session) -> None:
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("alert conflicts with an existing record") from exc
