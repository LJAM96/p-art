"""Plugin system for custom artwork providers."""

import importlib
import logging
import sys
from pathlib import Path
from typing import Dict, List, Type, Optional
from abc import ABC, abstractmethod

log = logging.getLogger("p-art")


class ProviderPlugin(ABC):
    """Base class for provider plugins."""

    name: str = "custom"
    display_name: str = "Custom Provider"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        self.api_key = api_key
        self.config = kwargs

    @abstractmethod
    def get_poster(self, item, min_width: int = 600) -> Optional[str]:
        """Get poster URL for an item."""
        pass

    @abstractmethod
    def get_background(self, item, min_width: int = 1920) -> Optional[str]:
        """Get background URL for an item."""
        pass

    def supports_media_type(self, media_type: str) -> bool:
        """Check if this provider supports the given media type."""
        return True


class PluginManager:
    """Manages provider plugins."""

    def __init__(self, plugin_dir: Path = Path("plugins")):
        self.plugin_dir = plugin_dir
        self.plugins: Dict[str, Type[ProviderPlugin]] = {}
        self._instances: Dict[str, ProviderPlugin] = {}

    def discover_plugins(self):
        """Discover and load plugins from plugin directory."""
        if not self.plugin_dir.exists():
            self.plugin_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Created plugin directory: {self.plugin_dir}")
            return

        # Add plugin directory to Python path
        plugin_path_str = str(self.plugin_dir.absolute())
        if plugin_path_str not in sys.path:
            sys.path.insert(0, plugin_path_str)

        # Discover Python files in plugin directory
        for plugin_file in self.plugin_dir.glob("*.py"):
            if plugin_file.name.startswith("_"):
                continue

            try:
                module_name = plugin_file.stem
                module = importlib.import_module(module_name)

                # Find ProviderPlugin subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, ProviderPlugin) and
                        attr is not ProviderPlugin):

                        plugin_name = getattr(attr, 'name', module_name)
                        self.plugins[plugin_name] = attr
                        log.info(f"Loaded plugin: {plugin_name} ({attr.display_name})")

            except Exception as e:
                log.error(f"Failed to load plugin {plugin_file.name}: {e}")

    def get_plugin(self, name: str, api_key: Optional[str] = None, **config) -> Optional[ProviderPlugin]:
        """Get or create a plugin instance."""
        if name not in self.plugins:
            return None

        if name not in self._instances:
            try:
                plugin_class = self.plugins[name]
                self._instances[name] = plugin_class(api_key=api_key, **config)
            except Exception as e:
                log.error(f"Failed to instantiate plugin {name}: {e}")
                return None

        return self._instances[name]

    def list_plugins(self) -> List[str]:
        """List available plugin names."""
        return list(self.plugins.keys())

    def reload_plugins(self):
        """Reload all plugins."""
        self.plugins.clear()
        self._instances.clear()
        self.discover_plugins()


# Example plugin template
class ExampleProviderPlugin(ProviderPlugin):
    """Example custom provider plugin."""

    name = "example"
    display_name = "Example Provider"

    def get_poster(self, item, min_width: int = 600) -> Optional[str]:
        """Get poster URL for an item."""
        # Implement your custom logic here
        # Example: fetch from custom API, local storage, etc.
        return None

    def get_background(self, item, min_width: int = 1920) -> Optional[str]:
        """Get background URL for an item."""
        # Implement your custom logic here
        return None

    def supports_media_type(self, media_type: str) -> bool:
        """Check if this provider supports the given media type."""
        return media_type in ["movie", "show"]
