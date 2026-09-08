from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from price_monitor.db.alert_models import AlertDirection

AlertState = Literal["disabled", "waiting", "clear", "triggered"]


class AlertRuleCreate(BaseModel):
    product_id: UUID
    direction: AlertDirection
    threshold_percent: Decimal = Field(gt=0, le=10_000, max_digits=18, decimal_places=6)


class AlertRuleUpdate(BaseModel):
    direction: AlertDirection | None = None
    threshold_percent: Decimal | None = Field(
        default=None,
        gt=0,
        le=10_000,
        max_digits=18,
        decimal_places=6,
    )
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_a_change(self) -> AlertRuleUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one alert field must be supplied")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("alert fields cannot be null")
        return self


class AlertEvaluationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    state: AlertState
    last_checked_at: datetime | None
    last_triggered_at: datetime | None
    competitor_product_id: UUID | None
    price: Decimal | None
    previous_price: Decimal | None
    currency: str | None
    change_percent: Decimal | None


class AlertRuleRead(BaseModel):
    id: UUID
    customer_id: UUID
    product_id: UUID
    direction: AlertDirection
    threshold_percent: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime
    evaluation: AlertEvaluationRead
