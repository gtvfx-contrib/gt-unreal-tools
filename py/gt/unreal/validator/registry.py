"""Rule registry: auto-discovery and decorator-based registration.

Provides a global registry that rules can register themselves with using the
``@registry.register`` decorator.  The registry supports auto-discovery of
rules from the rules subpackage.

Usage::

    from validator.registry import registry

    @registry.register(category="naming", severity=Severity.ERROR)
    class MyRule(AbstractRule):
        name = "my_rule"
        ...

"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Type, TYPE_CHECKING

if TYPE_CHECKING:
    from .rules.base import AbstractRule, Severity

logger = logging.getLogger(__name__)


class RuleRegistry:
    """Global registry of validation rules."""

    def __init__(self) -> None:
        self._rules: dict[str, Type] = {}
        self._discovered = False

    def register(self, category: str = "", severity=None):
        """Return a class decorator that registers the decorated rule class.

        Args:
            category: Optional category label assigned to the rule class.
            severity: Optional :class:`~validator.rules.base.Severity` value
                assigned to the rule class.

        Returns:
            A decorator that registers the class and returns it unchanged.

        Example::

            @registry.register(category="naming", severity=Severity.ERROR)
            class NamingConventionRule(AbstractRule):
                name = "naming_convention"
        
        """
        def decorator(cls: Type) -> Type:
            if category:
                cls.category = category
            if severity is not None:
                cls.severity = severity
            name = getattr(cls, "name", None) or cls.__name__
            if name in self._rules:
                logger.warning(
                    "[Registry] Rule '%s' already registered — overwriting with %s.",
                    name, cls.__name__,
                )
            self._rules[name] = cls
            logger.debug("[Registry] Registered rule '%s' (%s).", name, cls.__name__)
            return cls
        return decorator

    def discover(self) -> None:
        """Auto-discover and import all rule modules in the rules subpackage.

        Triggers module-level ``@registry.register`` decorators, populating
        the registry without requiring explicit imports.  Subsequent calls are
        no-ops (discovery runs at most once per process).
        
        """
        if self._discovered:
            return
        self._discovered = True

        from . import rules as rules_pkg
        for _finder, module_name, _is_pkg in pkgutil.iter_modules(rules_pkg.__path__):
            if module_name == "base":
                continue
            full_name = f"{rules_pkg.__name__}.{module_name}"
            try:
                importlib.import_module(full_name)
                logger.debug("[Registry] Discovered module: %s", full_name)
            except ImportError as exc:
                logger.warning(
                    "[Registry] Could not import '%s': %s", full_name, exc
                )

    def getRules(
        self,
        category: str | None = None,
        severity=None,
    ) -> list[Type]:
        """Return registered rule classes, optionally filtered.

        Args:
            category: If provided, only rules with this category are returned.
            severity: If provided, only rules with this severity are returned.

        Returns:
            A list of rule classes matching the given filters.
        
        """
        rules = list(self._rules.values())
        if category:
            rules = [r for r in rules if r.category == category]
        if severity is not None:
            rules = [r for r in rules if r.severity == severity]
        return rules

    def listRules(self) -> dict[str, Type]:
        """Return a copy of the rules dict {name: class}."""
        return dict(self._rules)

    def clear(self) -> None:
        """Clear all registered rules (useful in tests)."""
        self._rules.clear()
        self._discovered = False

    def __len__(self) -> int:
        return len(self._rules)

    def __repr__(self) -> str:
        return f"RuleRegistry(rules={list(self._rules.keys())})"


registry = RuleRegistry()