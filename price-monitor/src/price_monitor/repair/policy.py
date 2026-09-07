from __future__ import annotations

import re
from dataclasses import dataclass

from price_monitor.scrapers.spec import SelectorRule, SiteSpec

SELECTOR_FIELDS = frozenset({"name", "price", "currency", "availability", "external_product_id"})
_SAFE_NEW_ATTRIBUTES = frozenset(
    {"content", "href", "value", "aria-label", "data-price", "data-currency", "data-sku"}
)
_NESTED_QUANTIFIER = re.compile(r"\([^)]*[+*][^)]*\)[+*{]")
_BACKREFERENCE_OR_LOOKAROUND = re.compile(r"\\[1-9]|\(\?[=!<P]")


@dataclass(frozen=True, slots=True)
class PolicyViolation:
    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class RepairPolicyReport:
    accepted: bool
    changed_fields: tuple[str, ...]
    violations: tuple[PolicyViolation, ...]


@dataclass(frozen=True, slots=True)
class DeclarativeRepairPolicy:
    """Allowlist policy for automatically promotable declarative repairs."""

    maximum_added_rules: int = 8
    preserve_existing_rules: bool = True

    def validate(
        self,
        baseline: SiteSpec,
        candidate: SiteSpec,
        *,
        permitted_selector_fields: frozenset[str] | None = None,
    ) -> RepairPolicyReport:
        permitted = permitted_selector_fields or SELECTOR_FIELDS
        unknown_permitted = permitted - SELECTOR_FIELDS
        if unknown_permitted:
            raise ValueError(
                f"unsupported permitted selector fields: {sorted(unknown_permitted)!r}"
            )

        violations: list[PolicyViolation] = []
        changed = tuple(
            field_name
            for field_name in SiteSpec.model_fields
            if getattr(baseline, field_name) != getattr(candidate, field_name)
        )

        if candidate.key != baseline.key:
            violations.append(
                PolicyViolation("key_changed", "candidate cannot change its site key", "key")
            )
        if candidate.revision == baseline.revision:
            violations.append(
                PolicyViolation(
                    "revision_unchanged", "candidate must use a new revision", "revision"
                )
            )

        mutable = permitted | {"revision"}
        for field_name in changed:
            if field_name not in mutable:
                violations.append(
                    PolicyViolation(
                        "field_out_of_scope",
                        f"automatic repair cannot modify {field_name}",
                        field_name,
                    )
                )

        changed_selectors = set(changed) & SELECTOR_FIELDS
        if not changed_selectors:
            violations.append(
                PolicyViolation(
                    "no_selector_change",
                    "candidate must change at least one selector field",
                )
            )

        added_rule_count = 0
        for field_name in SELECTOR_FIELDS:
            old_rules = tuple(getattr(baseline, field_name))
            new_rules = tuple(getattr(candidate, field_name))
            if len(set(new_rules)) != len(new_rules):
                violations.append(
                    PolicyViolation(
                        "duplicate_rule",
                        f"candidate contains duplicate {field_name} rules",
                        field_name,
                    )
                )
            if self.preserve_existing_rules:
                removed = tuple(rule for rule in old_rules if rule not in new_rules)
                if removed:
                    violations.append(
                        PolicyViolation(
                            "rule_removed",
                            f"automatic repair cannot remove existing {field_name} rules",
                            field_name,
                        )
                    )
            additions = tuple(rule for rule in new_rules if rule not in old_rules)
            added_rule_count += len(additions)
            for rule in additions:
                violations.extend(self._validate_new_rule(field_name, rule))

        if added_rule_count > self.maximum_added_rules:
            violations.append(
                PolicyViolation(
                    "too_many_rules",
                    f"candidate adds {added_rule_count} rules; limit is {self.maximum_added_rules}",
                )
            )

        return RepairPolicyReport(
            accepted=not violations,
            changed_fields=changed,
            violations=tuple(violations),
        )

    @staticmethod
    def _validate_new_rule(field_name: str, rule: SelectorRule) -> list[PolicyViolation]:
        violations: list[PolicyViolation] = []
        normalized_selector = rule.selector.casefold().replace(" ", "")
        if normalized_selector == "*" or ":has(" in normalized_selector:
            violations.append(
                PolicyViolation(
                    "expensive_selector",
                    "new selector is too broad or computationally risky",
                    field_name,
                )
            )
        if rule.attribute is not None and rule.attribute.casefold() not in _SAFE_NEW_ATTRIBUTES:
            violations.append(
                PolicyViolation(
                    "attribute_not_allowed",
                    f"attribute {rule.attribute!r} is not allowed for automatic repair",
                    field_name,
                )
            )
        if rule.pattern is not None and (
            _NESTED_QUANTIFIER.search(rule.pattern)
            or _BACKREFERENCE_OR_LOOKAROUND.search(rule.pattern)
        ):
            violations.append(
                PolicyViolation(
                    "unsafe_pattern",
                    "new regular expression uses a disallowed expensive construct",
                    field_name,
                )
            )
        return violations


def validate_repair_scope(
    baseline: SiteSpec,
    candidate: SiteSpec,
    *,
    permitted_selector_fields: frozenset[str] | None = None,
) -> RepairPolicyReport:
    return DeclarativeRepairPolicy().validate(
        baseline,
        candidate,
        permitted_selector_fields=permitted_selector_fields,
    )
