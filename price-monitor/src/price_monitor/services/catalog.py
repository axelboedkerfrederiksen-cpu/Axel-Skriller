from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from price_monitor.api.schemas import (
    CompetitorCreate,
    CompetitorProductCreate,
    CompetitorProductUpdate,
    CompetitorUpdate,
    CustomerCreate,
    CustomerUpdate,
    ProductCreate,
    ProductUpdate,
)
from price_monitor.db.models import (
    Competitor,
    CompetitorProduct,
    Customer,
    Product,
    ScraperHealth,
)
from price_monitor.fetchers.policy import URLPolicyError, validate_url_syntax
from price_monitor.services.errors import ConflictError, InvalidRequestError, NotFoundError


def _url_string(value: Any) -> Any:
    return str(value) if hasattr(value, "scheme") and hasattr(value, "host") else value


def _payload(schema: BaseModel, *, exclude_unset: bool = False) -> dict[str, Any]:
    values = schema.model_dump(exclude_unset=exclude_unset)
    return {key: _url_string(value) for key, value in values.items()}


def _host(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise InvalidRequestError("URL must contain a hostname")
    return host.encode("idna").decode("ascii").lower().rstrip(".")


def _validate_product_url(product_url: str, competitor_url: str) -> None:
    expected_host = _host(competitor_url)
    try:
        product_parts, _, _ = validate_url_syntax(product_url, (expected_host,))
    except URLPolicyError as exc:
        raise InvalidRequestError(f"product URL is not permitted: {exc}") from exc
    competitor_parts = urlsplit(competitor_url)
    if competitor_parts.scheme.casefold() == "https" and product_parts.scheme.casefold() != "https":
        raise InvalidRequestError("product URL cannot downgrade the competitor's HTTPS scheme")


def _get_or_raise[ModelT](session: Session, model: type[ModelT], object_id: UUID) -> ModelT:
    instance = session.get(model, object_id)
    if instance is None:
        raise NotFoundError(f"{model.__name__} {object_id} was not found")
    return instance


class CatalogService:
    """Tenant-safe catalog mutations; transaction ownership stays with the caller."""

    @staticmethod
    def create_customer(session: Session, request: CustomerCreate) -> Customer:
        customer = Customer(**_payload(request))
        return CatalogService._add(session, customer)

    @staticmethod
    def update_customer(session: Session, customer_id: UUID, request: CustomerUpdate) -> Customer:
        return CatalogService._update(
            session, _get_or_raise(session, Customer, customer_id), request
        )

    @staticmethod
    def create_competitor(
        session: Session, customer_id: UUID, request: CompetitorCreate
    ) -> Competitor:
        _get_or_raise(session, Customer, customer_id)
        competitor = Competitor(customer_id=customer_id, **_payload(request))
        competitor = CatalogService._add(session, competitor)
        session.add(ScraperHealth(competitor_id=competitor.id))
        session.flush()
        return competitor

    @staticmethod
    def update_competitor(
        session: Session, competitor_id: UUID, request: CompetitorUpdate
    ) -> Competitor:
        return CatalogService._update(
            session, _get_or_raise(session, Competitor, competitor_id), request
        )

    @staticmethod
    def create_product(session: Session, customer_id: UUID, request: ProductCreate) -> Product:
        _get_or_raise(session, Customer, customer_id)
        product = Product(customer_id=customer_id, **_payload(request))
        return CatalogService._add(session, product)

    @staticmethod
    def update_product(session: Session, product_id: UUID, request: ProductUpdate) -> Product:
        product = _get_or_raise(session, Product, product_id)
        values = _payload(request, exclude_unset=True)
        resulting_price = values.get("current_own_price", product.current_own_price)
        resulting_currency = values.get("currency", product.currency)
        if (resulting_price is None) != (resulting_currency is None):
            raise InvalidRequestError("current_own_price and currency must both be set or cleared")
        return CatalogService._apply_update(session, product, values)

    @staticmethod
    def create_competitor_product(
        session: Session,
        product_id: UUID,
        request: CompetitorProductCreate,
    ) -> CompetitorProduct:
        product = _get_or_raise(session, Product, product_id)
        competitor = _get_or_raise(session, Competitor, request.competitor_id)
        if product.customer_id != competitor.customer_id:
            raise InvalidRequestError("product and competitor must belong to the same customer")
        product_url = str(request.product_url)
        _validate_product_url(product_url, competitor.base_url)
        values = _payload(request)
        values.pop("competitor_id")
        target = CompetitorProduct(
            product_id=product_id,
            competitor_id=competitor.id,
            **values,
        )
        return CatalogService._add(session, target)

    @staticmethod
    def update_competitor_product(
        session: Session,
        target_id: UUID,
        request: CompetitorProductUpdate,
    ) -> CompetitorProduct:
        target = _get_or_raise(session, CompetitorProduct, target_id)
        values = _payload(request, exclude_unset=True)
        if "product_url" in values:
            _validate_product_url(values["product_url"], target.competitor.base_url)
        minimum = values.get("minimum_valid_price", target.minimum_valid_price)
        maximum = values.get("maximum_valid_price", target.maximum_valid_price)
        if minimum is not None and maximum is not None and minimum > maximum:
            raise InvalidRequestError("minimum_valid_price cannot exceed maximum_valid_price")
        return CatalogService._apply_update(session, target, values)

    @staticmethod
    def _add[ModelT](session: Session, instance: ModelT) -> ModelT:
        session.add(instance)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("resource conflicts with an existing record") from exc
        return instance

    @staticmethod
    def _update[ModelT](session: Session, instance: ModelT, request: BaseModel) -> ModelT:
        return CatalogService._apply_update(
            session,
            instance,
            _payload(request, exclude_unset=True),
        )

    @staticmethod
    def _apply_update[ModelT](session: Session, instance: ModelT, values: dict[str, Any]) -> ModelT:
        for field, value in values.items():
            setattr(instance, field, value)
        try:
            session.flush()
        except IntegrityError as exc:
            raise ConflictError("resource conflicts with an existing record") from exc
        return instance

    @staticmethod
    def list_customers(session: Session) -> list[Customer]:
        return list(session.scalars(select(Customer).order_by(Customer.name)))

    @staticmethod
    def list_competitors(session: Session, customer_id: UUID) -> list[Competitor]:
        _get_or_raise(session, Customer, customer_id)
        return list(
            session.scalars(
                select(Competitor)
                .where(Competitor.customer_id == customer_id)
                .order_by(Competitor.name)
            )
        )

    @staticmethod
    def list_products(session: Session, customer_id: UUID) -> list[Product]:
        _get_or_raise(session, Customer, customer_id)
        return list(
            session.scalars(
                select(Product).where(Product.customer_id == customer_id).order_by(Product.name)
            )
        )

    @staticmethod
    def list_competitor_products(session: Session, product_id: UUID) -> list[CompetitorProduct]:
        _get_or_raise(session, Product, product_id)
        return list(
            session.scalars(
                select(CompetitorProduct)
                .where(CompetitorProduct.product_id == product_id)
                .order_by(CompetitorProduct.created_at)
            )
        )

    @staticmethod
    def get_customer(session: Session, object_id: UUID) -> Customer:
        return _get_or_raise(session, Customer, object_id)

    @staticmethod
    def get_competitor(session: Session, object_id: UUID) -> Competitor:
        return _get_or_raise(session, Competitor, object_id)

    @staticmethod
    def get_product(session: Session, object_id: UUID) -> Product:
        return _get_or_raise(session, Product, object_id)

    @staticmethod
    def get_competitor_product(session: Session, object_id: UUID) -> CompetitorProduct:
        return _get_or_raise(session, CompetitorProduct, object_id)
