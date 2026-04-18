import importlib
import pkgutil
from typing import Dict
from pipeline import domains
from pipeline.domains.base import DomainPlugin


class DomainNotFoundError(Exception):
    pass


class _DomainRegistry:
    """Registry for domain plugins."""

    def __init__(self) -> None:
        self._plugins: Dict[str, DomainPlugin] = {}

    def register(self, plugin: DomainPlugin) -> None:
        """Register a new domain plugin."""
        self._plugins[plugin.domain_id] = plugin

    def get(self, domain_id: str) -> DomainPlugin:
        """Get a registered domain plugin by ID."""
        if domain_id not in self._plugins:
            raise DomainNotFoundError(f"Domain plugin not found for '{domain_id}'")
        return self._plugins[domain_id]

    def auto_discover(self) -> None:
        """Scans domains/ subdirectories for plugin.py files and imports them."""
        for finder, name, ispkg in pkgutil.iter_modules(
            domains.__path__, domains.__name__ + "."
        ):
            if ispkg:
                plugin_module_name = f"{name}.plugin"
                try:
                    importlib.import_module(plugin_module_name)
                except ImportError:
                    # Depending on strictness, we might log it
                    # Skip if no plugin.py exists
                    pass


registry = _DomainRegistry()
