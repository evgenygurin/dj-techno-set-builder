"""PlatformRegistry — manages music platform adapter instances."""

from __future__ import annotations

from app.mcp.platforms.protocol import MusicPlatform, PlatformCapability


class PlatformRegistry:
    """Registry of connected music platform adapters.

    Provides lookup by platform name, capability checks,
    and lifecycle management (close_all).
    """

    def __init__(self) -> None:
        self._platforms: dict[str, MusicPlatform] = {}

    def register(self, adapter: MusicPlatform) -> None:
        """Register a platform adapter. Replaces existing if same name."""
        self._platforms[adapter.name] = adapter

    def get(self, name: str) -> MusicPlatform:
        """Get adapter by platform name. Raises KeyError if not found."""
        try:
            return self._platforms[name]
        except KeyError:
            msg = f"Platform '{name}' is not connected"
            raise KeyError(msg) from None

    def is_connected(self, name: str) -> bool:
        """Check if a platform adapter is registered."""
        return name in self._platforms

    def list_connected(self) -> list[str]:
        """Return sorted list of connected platform names."""
        return sorted(self._platforms.keys())

    def has_capability(self, name: str, capability: PlatformCapability) -> bool:
        """Check if a connected platform supports a capability."""
        if name not in self._platforms:
            return False
        return capability in self._platforms[name].capabilities

    async def close_all(self) -> None:
        """Close all registered adapters."""
        for adapter in self._platforms.values():
            await adapter.close()
