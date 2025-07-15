"""
Compatibility layer for existing EmojiBlacklist functionality.
This provides the same interface as the original EmojiBlacklist but uses guild-specific data.
"""

import logging
from typing import Union, Set, Dict, List
import discord
from .guild_blacklist_manager import GuildBlacklistManager

logger = logging.getLogger(__name__)


class EmojiBlacklistCompat:
    """
    Compatibility wrapper for EmojiBlacklist that works with guild-specific data.
    Maintains the same interface as the original EmojiBlacklist class.
    """
    
    def __init__(self, guild_blacklist_manager: GuildBlacklistManager, guild_id: int):
        """
        Initialize with guild-specific blacklist manager.
        
        Args:
            guild_blacklist_manager: The guild blacklist manager instance
            guild_id: The Discord guild ID this instance manages
        """
        self.guild_blacklist_manager = guild_blacklist_manager
        self.guild_id = guild_id
        
        # Legacy properties for compatibility (will be populated on demand)
        self.unicode_emojis: Set[str] = set()
        self.custom_emoji_ids: Set[int] = set()
        self.custom_emoji_names: Dict[int, str] = {}
    
    async def add_emoji(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> bool:
        """Add an emoji to the blacklist. Returns True if added, False if already exists."""
        try:
            result = await self.guild_blacklist_manager.add_emoji(self.guild_id, emoji)
            if result:
                # Update legacy properties for compatibility
                await self._update_legacy_properties()
            return result
        except Exception as e:
            logger.error(f"Failed to add emoji to blacklist: {e}")
            return False
    
    async def remove_emoji(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji, int]) -> bool:
        """Remove an emoji from the blacklist. Returns True if removed, False if not found."""
        try:
            result = await self.guild_blacklist_manager.remove_emoji(self.guild_id, emoji)
            if result:
                # Update legacy properties for compatibility
                await self._update_legacy_properties()
            return result
        except Exception as e:
            logger.error(f"Failed to remove emoji from blacklist: {e}")
            return False
    
    async def is_blacklisted(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> bool:
        """Check if an emoji is blacklisted."""
        try:
            return await self.guild_blacklist_manager.is_blacklisted(self.guild_id, emoji)
        except Exception as e:
            logger.error(f"Failed to check if emoji is blacklisted: {e}")
            return False
    
    def get_emoji_display(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> str:
        """Get a display string for an emoji."""
        if isinstance(emoji, str):
            return emoji
        elif hasattr(emoji, 'id') and emoji.id:
            if hasattr(emoji, 'animated') and emoji.animated:
                return f"<a:{emoji.name}:{emoji.id}>"
            else:
                return f"<:{emoji.name}:{emoji.id}>"
        return str(emoji)
    
    async def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage (legacy compatibility)."""
        await self._update_legacy_properties()
        return {
            'unicode_emojis': list(self.unicode_emojis),
            'custom_emoji_ids': list(self.custom_emoji_ids),
            'custom_emoji_names': self.custom_emoji_names
        }
    
    async def from_dict(self, data: dict):
        """Load from dictionary (legacy compatibility)."""
        # Clear existing data
        await self.guild_blacklist_manager.clear_blacklist(self.guild_id)
        
        # Add Unicode emojis
        unicode_emojis = set(data.get('unicode_emojis', []))
        for emoji in unicode_emojis:
            await self.add_emoji(emoji)
        
        # Add custom emojis
        custom_emoji_ids = set(data.get('custom_emoji_ids', []))
        custom_emoji_names = data.get('custom_emoji_names', {})
        
        # Convert string keys to int for custom_emoji_names
        custom_emoji_names = {int(k): v for k, v in custom_emoji_names.items()}
        
        for emoji_id in custom_emoji_ids:
            emoji_name = custom_emoji_names.get(emoji_id, 'unknown')
            # Create a PartialEmoji to add
            partial_emoji = discord.PartialEmoji(name=emoji_name, id=emoji_id)
            await self.add_emoji(partial_emoji)
    
    async def get_all_display(self) -> List[str]:
        """Get display strings for all blacklisted emojis."""
        try:
            return await self.guild_blacklist_manager.get_blacklist_display(self.guild_id)
        except Exception as e:
            logger.error(f"Failed to get blacklist display: {e}")
            return []
    
    async def clear_all(self):
        """Clear all blacklisted emojis."""
        try:
            await self.guild_blacklist_manager.clear_blacklist(self.guild_id)
            # Update legacy properties
            await self._update_legacy_properties()
        except Exception as e:
            logger.error(f"Failed to clear blacklist: {e}")
    
    async def _update_legacy_properties(self):
        """Update legacy properties for backward compatibility."""
        try:
            blacklisted = await self.guild_blacklist_manager.get_all_blacklisted(self.guild_id)
            
            unicode_emojis = set()
            custom_emoji_ids = set()
            custom_emoji_names = {}
            
            for emoji_data in blacklisted:
                if emoji_data['emoji_type'] == 'unicode':
                    unicode_emojis.add(emoji_data['emoji_value'])
                else:
                    emoji_id = int(emoji_data['emoji_value'])
                    custom_emoji_ids.add(emoji_id)
                    if emoji_data['emoji_name']:
                        custom_emoji_names[emoji_id] = emoji_data['emoji_name']
            
            self.unicode_emojis = unicode_emojis
            self.custom_emoji_ids = custom_emoji_ids
            self.custom_emoji_names = custom_emoji_names
            
        except Exception as e:
            logger.error(f"Failed to update legacy properties: {e}")
            # Initialize with empty sets on error
            self.unicode_emojis = set()
            self.custom_emoji_ids = set()
            self.custom_emoji_names = {}


class GlobalEmojiBlacklistManager:
    """
    Manages emoji blacklists across multiple guilds.
    Provides a way to get guild-specific blacklist instances.
    """
    
    def __init__(self, guild_blacklist_manager: GuildBlacklistManager):
        """Initialize with guild blacklist manager."""
        self.guild_blacklist_manager = guild_blacklist_manager
        self._guild_instances: Dict[int, EmojiBlacklistCompat] = {}
    
    def get_guild_blacklist(self, guild_id: int) -> EmojiBlacklistCompat:
        """Get or create a guild-specific blacklist instance."""
        if guild_id not in self._guild_instances:
            self._guild_instances[guild_id] = EmojiBlacklistCompat(
                self.guild_blacklist_manager, guild_id
            )
        return self._guild_instances[guild_id]
    
    async def migrate_global_blacklist(self, guild_ids: List[int], global_data: dict):
        """
        Migrate global blacklist data to all specified guilds.
        
        Args:
            guild_ids: List of guild IDs to migrate data to
            global_data: Global blacklist data in the old format
        """
        unicode_emojis = set(global_data.get('unicode_emojis', []))
        custom_emoji_ids = set(global_data.get('custom_emoji_ids', []))
        custom_emoji_names = global_data.get('custom_emoji_names', {})
        
        # Convert string keys to int for custom_emoji_names
        custom_emoji_names = {int(k): v for k, v in custom_emoji_names.items()}
        
        for guild_id in guild_ids:
            try:
                await self.guild_blacklist_manager.migrate_from_global_blacklist(
                    guild_id, unicode_emojis, custom_emoji_ids, custom_emoji_names
                )
                logger.info(f"Migrated global blacklist to guild {guild_id}")
            except Exception as e:
                logger.error(f"Failed to migrate blacklist to guild {guild_id}: {e}")