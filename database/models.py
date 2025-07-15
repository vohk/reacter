"""
Data models for guild configurations and blacklisted emojis.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class GuildConfig:
    """Guild-specific configuration settings."""
    guild_id: int
    log_channel_id: Optional[int] = None
    timeout_duration: int = 300
    dm_on_timeout: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class BlacklistedEmoji:
    """Represents a blacklisted emoji for a specific guild."""
    guild_id: int
    emoji_type: str  # 'unicode' or 'custom'
    emoji_value: str  # Unicode emoji or custom emoji ID
    emoji_name: Optional[str] = None  # Display name for custom emojis
    created_at: Optional[datetime] = None