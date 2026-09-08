from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Numeric, String, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from price_monitor.db.base import Base
from price_monitor.db.types import UTCDateTime
from price_monitor.domain.types import utc_now

AlertDirection = Literal["decrease", "increase", "either"]


class AlertRule(Base):
    """A durable, product-scoped price-change rule.

    Alert delivery is deliberately out of scope for the first release. The rule's
    state is evaluated from accepted ``PriceHistory`` rows, so failed or rejected
    scraper observations never create an alert.
    """

    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint(
            "direction IN ('decrease', 'increase', 'either')",
            name="direction_valid",
        ),
        CheckConstraint(
            "threshold_percent > 0 AND threshold_percent <= 10000",
            name="threshold_percent_range",
        ),
        Index("ix_alert_rules_customer_active", "customer_id", "is_active"),
        Index("ix_alert_rules_product_id", "product_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    direction: Mapped[AlertDirection] = mapped_column(String(16), nullable=False)
    threshold_percent: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
