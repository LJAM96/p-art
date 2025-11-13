"""
Example custom artwork provider plugin for P-Art.

This template shows how to create your own artwork provider.
Copy this file, rename it, and implement the get_poster and get_background methods.
"""

from plugin_system import ProviderPlugin
from typing import Optional


class MyCustomProvider(ProviderPlugin):
    """
    Example custom provider - replace with your own implementation.

    Attributes:
        name: Unique identifier for this provider (lowercase, no spaces)
        display_name: Human-readable name shown in logs
    """

    name = "mycustom"
    display_name = "My Custom Provider"

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """
        Initialize your provider.

        Args:
            api_key: Optional API key if your provider requires authentication
            **kwargs: Additional configuration options from config
        """
        super().__init__(api_key, **kwargs)

        # Add any custom initialization here
        # Example: self.base_url = kwargs.get('base_url', 'https://api.example.com')

    def get_poster(self, item, min_width: int = 600) -> Optional[str]:
        """
        Get poster URL for a Plex item.

        Args:
            item: Plex library item (movie or show)
            min_width: Minimum width in pixels

        Returns:
            URL string if found, None otherwise

        Example implementation:
        """
        # Get item details
        title = getattr(item, 'title', '')
        year = getattr(item, 'year', None)
        media_type = getattr(item, 'type', 'movie')

        # Your custom logic here
        # Example: search your API, local storage, etc.
        # poster_url = self._search_my_api(title, year, media_type)

        # Return the poster URL or None
        return None

    def get_background(self, item, min_width: int = 1920) -> Optional[str]:
        """
        Get background/fanart URL for a Plex item.

        Args:
            item: Plex library item (movie or show)
            min_width: Minimum width in pixels

        Returns:
            URL string if found, None otherwise
        """
        # Similar implementation to get_poster
        # Your custom logic here

        return None

    def supports_media_type(self, media_type: str) -> bool:
        """
        Check if this provider supports the given media type.

        Args:
            media_type: One of "movie", "show", "season", "episode", "collection"

        Returns:
            True if supported, False otherwise
        """
        # Example: only support movies and shows
        return media_type in ["movie", "show"]


# Additional helper methods can be added as needed:
    def _search_my_api(self, title: str, year: Optional[int], media_type: str) -> Optional[str]:
        """
        Helper method example - search your custom API.

        This is just an example structure. Implement according to your needs.
        """
        # Your implementation here
        pass
