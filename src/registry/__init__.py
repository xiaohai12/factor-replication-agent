"""Plugin Registry - Store and retrieve validated signal plugins."""

from __future__ import annotations

import hashlib
from typing import Optional

from src.models.plugin import PluginRecord


class PluginRegistry:
    """Persistent registry of validated signal plugins.

    Provides traceability from experiment results back to specific
    plugin code and MethodSpec versions.
    """

    def __init__(self):
        self._plugins: dict[str, PluginRecord] = {}

    def register(self, plugin: PluginRecord) -> str:
        """Register a validated plugin. Returns plugin_id."""
        plugin.code_hash = hashlib.sha256(plugin.code.encode()).hexdigest()[:16]
        self._plugins[plugin.plugin_id] = plugin
        return plugin.plugin_id

    def get(self, plugin_id: str) -> Optional[PluginRecord]:
        """Retrieve a plugin by ID."""
        return self._plugins.get(plugin_id)

    def list_by_factor(self, factor_id: str) -> list[PluginRecord]:
        """List all plugins for a given factor."""
        return [p for p in self._plugins.values() if p.factor_id == factor_id]

    def get_latest(self, factor_id: str) -> Optional[PluginRecord]:
        """Get the latest validated plugin for a factor."""
        plugins = [
            p for p in self.list_by_factor(factor_id)
            if p.validation_status == "passed"
        ]
        return plugins[-1] if plugins else None
