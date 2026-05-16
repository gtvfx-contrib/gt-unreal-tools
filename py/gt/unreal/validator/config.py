"""Layered configuration for the Asset Validation Framework.

Merges settings from built-in defaults, an optional JSON config file, and
environment variable overrides.  Later layers win over earlier ones.

Layering order (highest priority first):

1. Environment variables (``VALIDATOR_<KEY>`` in upper-case)
2. JSON config file (``--config`` flag or ``VALIDATOR_CONFIG_PATH``)
3. Hard-coded ``DEFAULTS``

Example::

    config = Config("my_config.json")
    max_mb = config.get("max_file_size_mb")   # 50 (default)
    config["naming_pattern"]                  # raises KeyError if missing
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


DEFAULTS: dict[str, Any] = {
    "max_file_size_mb":             50,
    "max_filename_length":          64,
    "naming_pattern":               r"^[A-Z][a-zA-Z0-9_]+$",
    "required_prefixes": {
        "SM_": [".fbx", ".uasset"],
        "T_":  [".png", ".tga", ".exr"],
        "M_":  [".uasset"],
    },
    "valid_extensions":             [".uasset", ".fbx", ".png", ".tga", ".exr"],
    "log_level":                    "WARNING",
    "min_lod_count":                1,
    "max_lod_count":                8,
    "max_material_slots":           4,
    "max_bounds_extent_uu":         500.0,
    "max_pivot_offset_uu":          10.0,
    "max_texture_dimension":        4096,
    "max_texture_samples":          16,
    "min_lod_screen_size_ratio":    0.5,
    "max_niagara_emitters":         8,
    "max_niagara_spawn_rate":       10000,
    "allow_gpu_simulation":         True,
    "require_niagara_fixed_bounds": True,
    "max_translucent_materials":    2,
    "allowlist":                    [],
    "report_format":                "console",
    "filter_severity":              None,
    "filter_category":              None,
    "show_passing":                 False,
}


CONFIG_SCHEMA: dict[str, type | tuple] = {
    "max_file_size_mb":             int,
    "max_filename_length":          int,
    "naming_pattern":               str,
    "required_prefixes":            dict,
    "valid_extensions":             list,
    "log_level":                    str,
    "min_lod_count":                int,
    "max_lod_count":                int,
    "max_material_slots":           int,
    "max_bounds_extent_uu":         (int, float),
    "max_pivot_offset_uu":          (int, float),
    "max_texture_dimension":        int,
    "max_texture_samples":          int,
    "min_lod_screen_size_ratio":    (int, float),
    "max_niagara_emitters":         int,
    "max_niagara_spawn_rate":       int,
    "allow_gpu_simulation":         bool,
    "require_niagara_fixed_bounds": bool,
    "max_translucent_materials":    int,
    "allowlist":                    list,
    "report_format":                str,
    "filter_severity":              (str, type(None)),
    "filter_category":              (str, type(None)),
    "show_passing":                 bool,
}


class Config:
    """Layered configuration container.

    Merges built-in defaults, an optional JSON file, and environment variable
    overrides into a single dict-like object.
    """

    def __init__(self, config_path: str | None = None, validate: bool = True) -> None:
        """Initialise the configuration.

        Args:
            config_path: Path to a JSON config file.  When ``None``, only
                defaults and environment variable overrides are applied.
            validate: When ``True`` (default), eagerly validates value types
                against :data:`CONFIG_SCHEMA` after loading.

        Raises:
            ValueError: If ``config_path`` is given but the file does not
                exist, the JSON is malformed, or (with ``validate=True``) any
                config value has the wrong type.
        """
        self._data: dict[str, Any] = dict(DEFAULTS)

        if config_path:
            json_data = self._load_json(config_path)
            self._data.update(json_data)

        env_data = self._load_env()
        self._data.update(env_data)

        if validate:
            self._validate_schema()

        logger.debug("[Config] Initialized with %d keys.", len(self._data))

    def _load_json(self, path: str) -> dict[str, Any]:
        """Load and return config values from a JSON file.

        Args:
            path: Filesystem path to the JSON config file.

        Returns:
            A dict of config key/value pairs parsed from the file.

        Raises:
            ValueError: If the file does not exist, is not a JSON object, or
                contains malformed JSON.
        """
        if not os.path.isfile(path):
            raise ValueError(f"Config file not found: '{path}'")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                raise ValueError(f"Config file must be a JSON object: '{path}'")
            logger.debug("[Config] Loaded JSON config from '%s'.", path)
            return data
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON in config '{path}': {exc}") from exc

    def _load_env(self) -> dict[str, Any]:
        """Read ``VALIDATOR_<KEY>`` environment variables and coerce types.

        Returns:
            A dict of config key/value pairs sourced from the environment.
            Only keys that appear in :data:`DEFAULTS` are included.

        Example:
            ``VALIDATOR_MAX_FILE_SIZE_MB=100`` sets ``max_file_size_mb=100``
            (coerced to ``int``).
        """
        result: dict[str, Any] = {}
        prefix = "VALIDATOR_"
        for env_key, raw_value in os.environ.items():
            if not env_key.startswith(prefix):
                continue
            config_key = env_key[len(prefix):].lower()
            if config_key in DEFAULTS:
                coerced = self._coerce(config_key, raw_value)
                if coerced is not None:
                    result[config_key] = coerced
        return result

    def _coerce(self, key: str, raw: str) -> Any:
        """Coerce a raw environment variable string to the correct type.

        Args:
            key: Config key used to look up the expected type from
                :data:`DEFAULTS`.
            raw: Raw string value from the environment variable.

        Returns:
            The coerced value, or the original string if coercion fails.
        """
        default = DEFAULTS.get(key)
        if default is None:
            return raw
        try:
            if isinstance(default, bool):
                return raw.lower() in ("1", "true", "yes")
            if isinstance(default, int):
                return int(raw)
            if isinstance(default, float):
                return float(raw)
            if isinstance(default, (list, dict)):
                return json.loads(raw)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning(
                "[Config] Could not coerce env var '%s'=%r: %s", key, raw, exc
            )
        return raw

    def _validate_schema(self) -> None:
        """Eagerly fail with a clear error if config values have wrong types."""
        errors = []
        for key, expected_type in CONFIG_SCHEMA.items():
            if key not in self._data:
                continue
            value = self._data[key]
            if not isinstance(value, expected_type):
                errors.append(
                    f"  '{key}': expected {expected_type}, "
                    f"got {type(value).__name__} = {value!r}"
                )
        if errors:
            raise ValueError(
                "Config validation failed — fix these issues before running:\n"
                + "\n".join(errors)
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Return the config value for key, or default if not found.

        Args:
            key: Config key to look up.
            default: Value returned when *key* is absent.

        Returns:
            The stored value for *key*, or *default*.
        """
        return self._data.get(key, default)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Config(keys={list(self._data.keys())})"