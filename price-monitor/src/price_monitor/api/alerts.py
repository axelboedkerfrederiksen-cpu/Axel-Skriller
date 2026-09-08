from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from price_monitor.api.alert_schemas import (
    AlertEvaluationRead,
    AlertRuleCreate,
    AlertRuleRead,
    AlertRuleUpdate,
)
from price_monitor.api.dependencies import SessionDep
from price_monitor.db.alert_models import AlertRule
from price_monitor.services.alerts import AlertService
from price_monitor.services.errors import ConflictError

router = APIRouter(tags=["alerts"])


def _commit(session: Session) -> None:
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("alert conflicts with a concurrent operation") from exc


def _read(session: Session, rule: AlertRule) -> AlertRuleRead:
    return AlertRuleRead(
        id=rule.id,
        customer_id=rule.customer_id,
        product_id=rule.product_id,
        direction=rule.direction,
        threshold_percent=rule.threshold_percent,
        is_active=rule.is_active,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        evaluation=AlertEvaluationRead.model_validate(AlertService.evaluate(session, rule)),
    )


@router.post(
    "/customers/{customer_id}/alert-rules",
    response_model=AlertRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_alert_rule(
    customer_id: UUID,
    request: AlertRuleCreate,
    session: SessionDep,
) -> AlertRuleRead:
    rule = AlertService.create(session, customer_id, request)
    _commit(session)
    return _read(session, rule)


@router.get(
    "/customers/{customer_id}/alert-rules",
    response_model=list[AlertRuleRead],
)
def list_alert_rules(customer_id: UUID, session: SessionDep) -> list[AlertRuleRead]:
    return [_read(session, rule) for rule in AlertService.list(session, customer_id)]


@router.get("/alert-rules/{rule_id}", response_model=AlertRuleRead)
def get_alert_rule(rule_id: UUID, session: SessionDep) -> AlertRuleRead:
    return _read(session, AlertService.get(session, rule_id))


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(
    rule_id: UUID,
    request: AlertRuleUpdate,
    session: SessionDep,
) -> AlertRuleRead:
    rule = AlertService.update(session, rule_id, request)
    _commit(session)
    return _read(session, rule)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_alert_rule(rule_id: UUID, session: SessionDep) -> Response:
    AlertService.delete(session, rule_id)
    _commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
