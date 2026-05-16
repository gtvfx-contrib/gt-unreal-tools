"""AllowlistManager: explicit per-asset rule exceptions with expiry.

The allowlist lets Technical Leads grant time-limited exceptions to specific
assets that would otherwise fail a validation rule. Each entry records the
reason, the author who approved it, and an optional expiry date.

Config key: ``allowlist`` (list of dicts in the JSON config).

JSON format::

    {
        "allowlist": [
            {
                "rule": "material_blend_mode",
                "asset": "/Game/Cinematics/Hero/M_HeroSkin",
                "reason": "Approved by TA lead for cinematic use",
                "author": "j.smith",
                "expires": "2026-12-31"
            }
        ]
    }
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

logger = logging.getLogger(__name__)


class AllowlistEntry:
    """One allowlist entry loaded from config.

    Attributes:
        rule: Name of the validation rule this exception applies to.
        asset: Content-browser or filesystem path of the exempted asset.
        reason: Human-readable justification for the exception.
        author: Username or identifier of the approver.
    """

    def __init__(self, rule: str, asset: str, reason: str = "",
                 author: str = "", expires: str | None = None) -> None:
        """Initialise an allowlist entry.

        Args:
            rule: Name of the validation rule this exception applies to.
            asset: Content-browser or filesystem path of the exempted asset.
            reason: Human-readable justification for the exception.
            author: Username or identifier of the approver.
            expires: Optional expiry date string in ``YYYY-MM-DD`` format.
                Entries past this date are treated as expired.
        """
        self.rule   = rule
        self.asset  = asset
        self.reason = reason
        self.author = author
        self._expires_str = expires
        self._expires: date | None = None
        if expires:
            try:
                self._expires = datetime.strptime(expires, "%Y-%m-%d").date()
            except ValueError:
                logger.warning(
                    "[Allowlist] Invalid expiry date '%s' for rule=%s asset=%s — ignoring.",
                    expires, rule, asset,
                )

    def is_expired(self) -> bool:
        """Return True if this entry has passed its expiry date."""
        if self._expires is None:
            return False
        return date.today() > self._expires

    def __repr__(self) -> str:
        return (
            f"AllowlistEntry(rule={self.rule!r}, asset={self.asset!r}, "
            f"expires={self._expires_str!r})"
        )


class AllowlistManager:
    """Manages a collection of allowlist entries loaded from :class:`Config`.

    Provides rule-plus-asset lookup so that rules can honour approved
    exceptions before raising failures.

    Example::

        from validator.allowlist import AllowlistManager

        manager = AllowlistManager(config)
        if manager.is_allowed("material_blend_mode", "/Game/M_HeroSkin"):
            return self._make_result(asset_path, passed=True, message="Allowlisted.")
    """

    def __init__(self, config: "Config") -> None:
        """Initialise the manager and load entries from config.

        Args:
            config: Loaded :class:`~validator.config.Config` instance.
                The ``allowlist`` key must contain a list of entry dicts.
        """
        raw_entries: list[dict] = config.get("allowlist", [])
        self._entries: list[AllowlistEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                logger.warning("[Allowlist] Skipping invalid entry (not a dict): %r", raw)
                continue
            entry = AllowlistEntry(
                rule    = raw.get("rule", ""),
                asset   = raw.get("asset", ""),
                reason  = raw.get("reason", ""),
                author  = raw.get("author", ""),
                expires = raw.get("expires"),
            )
            if entry.is_expired():
                logger.warning(
                    "[Allowlist] Expired entry skipped: rule=%s asset=%s expired=%s",
                    entry.rule, entry.asset, entry._expires_str,
                )
            else:
                self._entries.append(entry)

        logger.debug("[Allowlist] Loaded %d active entries.", len(self._entries))

    def is_allowed(self, rule_name: str, asset_path: str) -> bool:
        """Return ``True`` if the combination matches an active allowlist entry.

        Matching is exact on both rule name and asset path.

        Args:
            rule_name: Name of the validation rule.
            asset_path: Content-browser or filesystem path of the asset.

        Returns:
            ``True`` when an active (non-expired) entry matches, ``False``
            otherwise.
        """
        for entry in self._entries:
            if entry.rule == rule_name and entry.asset == asset_path:
                return True
        return False

    def get_entry(self, rule_name: str, asset_path: str) -> AllowlistEntry | None:
        """Return the matching :class:`AllowlistEntry`, or ``None``.

        Args:
            rule_name: Name of the validation rule.
            asset_path: Content-browser or filesystem path of the asset.

        Returns:
            The matching entry, or ``None`` if no active entry is found.
        """
        for entry in self._entries:
            if entry.rule == rule_name and entry.asset == asset_path:
                return entry
        return None

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"AllowlistManager(entries={len(self._entries)})"