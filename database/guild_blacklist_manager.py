"""
Guild-specific blacklist management system.
"""

import logging
from typing import Union, List, Dict, Optional
import discord
from .manager import DatabaseManager, DatabaseError
from .models import BlacklistedEmoji
from .logging_manager import monitoring_manager
from datetime import datetime

logger = logging.getLogger(__name__)


class GuildBlacklistManager:
    """Manages guild-specific emoji blacklists."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize with database manager."""
        self.db_manager = db_manager
        self._cache: Dict[int, Dict[str, set]] = {}  # guild_id -> {unicode: set, custom: set}
    
    async def add_emoji(self, guild_id: int, emoji: Union[str, discord.Emoji, discord.PartialEmoji], 
                       user_id: Optional[int] = None, command_name: Optional[str] = None) -> bool:
        """
        Add an emoji to the guild's blacklist.
        
        Args:
            guild_id: Discord guild ID
            emoji: Emoji to add (Unicode string or Discord emoji object)
            user_id: ID of user making the change (for audit logging)
            command_name: Name of command that triggered the change (for audit logging)
            
        Returns:
            True if emoji was added, False if already exists
        """
        try:
            emoji_type, emoji_value, emoji_name = self._parse_emoji(emoji)
            
            # Check if already exists
            if await self.is_blacklisted(guild_id, emoji):
                return False
            
            # Insert into database
            query = """
                INSERT INTO guild_blacklists (guild_id, emoji_type, emoji_value, emoji_name)
                VALUES (?, ?, ?, ?)
            """
            await self.db_manager.execute_query(query, (guild_id, emoji_type, emoji_value, emoji_name))
            
            # Update cache
            self._update_cache_add(guild_id, emoji_type, emoji_value)
            
            # Log blacklist change for audit trail
            emoji_info = {
                'emoji_type': emoji_type,
                'emoji_value': emoji_value,
                'emoji_name': emoji_name,
                'display': self._get_emoji_display_string(emoji_type, emoji_value, emoji_name)
            }
            monitoring_manager.audit_logger.log_blacklist_change(
                guild_id=guild_id,
                action='ADD',
                emoji_info=emoji_info,
                user_id=user_id,
                command_name=command_name
            )
            
            logger.info(f"Added {emoji_type} emoji {emoji_value} to blacklist for guild {guild_id}")
            return True
            
        except DatabaseError as e:
            logger.error(f"Database error adding emoji to blacklist for guild {guild_id}: {e}")
            # Update cache even if database fails to maintain consistency for current session
            try:
                emoji_type, emoji_value, emoji_name = self._parse_emoji(emoji)
                self._update_cache_add(guild_id, emoji_type, emoji_value)
                logger.warning(f"Added emoji to cache only for guild {guild_id} due to database error")
                return True
            except Exception as parse_error:
                logger.error(f"Failed to parse emoji during fallback: {parse_error}")
                raise DatabaseError(f"Failed to add emoji to blacklist: {e}")
        except Exception as e:
            logger.error(f"Unexpected error adding emoji to blacklist for guild {guild_id}: {e}")
            raise
    
    async def remove_emoji(self, guild_id: int, emoji: Union[str, discord.Emoji, discord.PartialEmoji, int], 
                          user_id: Optional[int] = None, command_name: Optional[str] = None) -> bool:
        """
        Remove an emoji from the guild's blacklist.
        
        Args:
            guild_id: Discord guild ID
            emoji: Emoji to remove (Unicode string, Discord emoji object, or custom emoji ID)
            user_id: ID of user making the change (for audit logging)
            command_name: Name of command that triggered the change (for audit logging)
            
        Returns:
            True if emoji was removed, False if not found
        """
        try:
            # Handle direct emoji ID input
            if isinstance(emoji, int):
                emoji_type = "custom"
                emoji_value = str(emoji)
                emoji_name = "unknown"
                
                # Get emoji name from database for audit logging
                query = """
                    SELECT emoji_name FROM guild_blacklists 
                    WHERE guild_id = ? AND emoji_type = ? AND emoji_value = ?
                """
                result = await self.db_manager.fetch_one(query, (guild_id, emoji_type, emoji_value))
                if not result:
                    return False
                emoji_name = result.get('emoji_name', 'unknown')
            else:
                emoji_type, emoji_value, emoji_name = self._parse_emoji(emoji)
                
                # Check if exists
                if not await self.is_blacklisted(guild_id, emoji):
                    return False
            
            # Remove from database
            query = """
                DELETE FROM guild_blacklists 
                WHERE guild_id = ? AND emoji_type = ? AND emoji_value = ?
            """
            await self.db_manager.execute_query(query, (guild_id, emoji_type, emoji_value))
            
            # Update cache
            self._update_cache_remove(guild_id, emoji_type, emoji_value)
            
            # Log blacklist change for audit trail
            emoji_info = {
                'emoji_type': emoji_type,
                'emoji_value': emoji_value,
                'emoji_name': emoji_name,
                'display': self._get_emoji_display_string(emoji_type, emoji_value, emoji_name)
            }
            monitoring_manager.audit_logger.log_blacklist_change(
                guild_id=guild_id,
                action='REMOVE',
                emoji_info=emoji_info,
                user_id=user_id,
                command_name=command_name
            )
            
            logger.info(f"Removed {emoji_type} emoji {emoji_value} from blacklist for guild {guild_id}")
            return True
            
        except DatabaseError as e:
            logger.error(f"Database error removing emoji from blacklist for guild {guild_id}: {e}")
            # Update cache even if database fails to maintain consistency for current session
            try:
                if isinstance(emoji, int):
                    emoji_type = "custom"
                    emoji_value = str(emoji)
                else:
                    emoji_type, emoji_value, _ = self._parse_emoji(emoji)
                self._update_cache_remove(guild_id, emoji_type, emoji_value)
                logger.warning(f"Removed emoji from cache only for guild {guild_id} due to database error")
                return True
            except Exception as parse_error:
                logger.error(f"Failed to parse emoji during fallback: {parse_error}")
                raise DatabaseError(f"Failed to remove emoji from blacklist: {e}")
        except Exception as e:
            logger.error(f"Unexpected error removing emoji from blacklist for guild {guild_id}: {e}")
            raise
    
    async def is_blacklisted(self, guild_id: int, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> bool:
        """
        Check if an emoji is blacklisted for a guild.
        
        Args:
            guild_id: Discord guild ID
            emoji: Emoji to check
            
        Returns:
            True if emoji is blacklisted, False otherwise
        """
        try:
            # Load cache if not present
            if guild_id not in self._cache:
                await self._load_guild_cache(guild_id)
            
            emoji_type, emoji_value, _ = self._parse_emoji(emoji)
            
            # Check cache
            guild_cache = self._cache.get(guild_id, {})
            if emoji_type == "unicode":
                return emoji_value in guild_cache.get("unicode", set())
            else:
                return emoji_value in guild_cache.get("custom", set())
                
        except Exception as e:
            logger.error(f"Failed to check if emoji is blacklisted for guild {guild_id}: {e}")
            return False
    
    async def get_all_blacklisted(self, guild_id: int) -> List[Dict[str, str]]:
        """
        Get all blacklisted emojis for a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            List of dictionaries containing emoji information
        """
        try:
            query = """
                SELECT emoji_type, emoji_value, emoji_name, created_at
                FROM guild_blacklists
                WHERE guild_id = ?
                ORDER BY created_at DESC
            """
            rows = await self.db_manager.fetch_all(query, (guild_id,))
            return rows
            
        except DatabaseError as e:
            logger.error(f"Database error getting blacklisted emojis for guild {guild_id}: {e}")
            # Fallback to cache if available
            if guild_id in self._cache:
                logger.warning(f"Using cached data for guild {guild_id} blacklist due to database error")
                cache_data = []
                guild_cache = self._cache[guild_id]
                
                # Convert cache to list format
                for emoji_value in guild_cache.get("unicode", set()):
                    cache_data.append({
                        'emoji_type': 'unicode',
                        'emoji_value': emoji_value,
                        'emoji_name': None,
                        'created_at': None
                    })
                
                for emoji_value in guild_cache.get("custom", set()):
                    cache_data.append({
                        'emoji_type': 'custom',
                        'emoji_value': emoji_value,
                        'emoji_name': 'unknown',
                        'created_at': None
                    })
                
                return cache_data
            else:
                logger.warning(f"No cached data available for guild {guild_id}")
                return []
        except Exception as e:
            logger.error(f"Unexpected error getting blacklisted emojis for guild {guild_id}: {e}")
            return []
    
    async def clear_blacklist(self, guild_id: int) -> None:
        """
        Clear all blacklisted emojis for a guild.
        
        Args:
            guild_id: Discord guild ID
        """
        try:
            query = "DELETE FROM guild_blacklists WHERE guild_id = ?"
            await self.db_manager.execute_query(query, (guild_id,))
            
            # Clear cache
            if guild_id in self._cache:
                del self._cache[guild_id]
            
            logger.info(f"Cleared all blacklisted emojis for guild {guild_id}")
            
        except DatabaseError as e:
            logger.error(f"Database error clearing blacklist for guild {guild_id}: {e}")
            # Clear cache even if database fails to maintain consistency for current session
            if guild_id in self._cache:
                del self._cache[guild_id]
                logger.warning(f"Cleared cache only for guild {guild_id} due to database error")
            raise DatabaseError(f"Failed to clear blacklist for guild {guild_id}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error clearing blacklist for guild {guild_id}: {e}")
            raise
    
    async def get_blacklist_display(self, guild_id: int) -> List[str]:
        """
        Get display strings for all blacklisted emojis in a guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            List of emoji display strings
        """
        try:
            blacklisted = await self.get_all_blacklisted(guild_id)
            displays = []
            
            for emoji_data in blacklisted:
                if emoji_data['emoji_type'] == 'unicode':
                    displays.append(emoji_data['emoji_value'])
                else:
                    # Custom emoji
                    emoji_name = emoji_data['emoji_name'] or 'unknown'
                    emoji_id = emoji_data['emoji_value']
                    displays.append(f"<:{emoji_name}:{emoji_id}>")
            
            return displays
            
        except Exception as e:
            logger.error(f"Failed to get blacklist display for guild {guild_id}: {e}")
            return []
    
    def _parse_emoji(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> tuple[str, str, Optional[str]]:
        """
        Parse emoji into type, value, and name.
        
        Returns:
            Tuple of (emoji_type, emoji_value, emoji_name)
        """
        if isinstance(emoji, str):
            # Unicode emoji
            return ("unicode", emoji, None)
        elif hasattr(emoji, 'id') and emoji.id is not None:
            # Custom emoji with ID
            return ("custom", str(emoji.id), emoji.name)
        elif hasattr(emoji, 'name'):
            # Unicode emoji as PartialEmoji (id is None)
            return ("unicode", emoji.name, None)
        else:
            raise ValueError(f"Unable to parse emoji: {emoji}")
    
    async def _load_guild_cache(self, guild_id: int) -> None:
        """Load guild blacklist into cache."""
        try:
            blacklisted = await self.get_all_blacklisted(guild_id)
            
            unicode_emojis = set()
            custom_emojis = set()
            
            for emoji_data in blacklisted:
                if emoji_data['emoji_type'] == 'unicode':
                    unicode_emojis.add(emoji_data['emoji_value'])
                else:
                    custom_emojis.add(emoji_data['emoji_value'])
            
            self._cache[guild_id] = {
                "unicode": unicode_emojis,
                "custom": custom_emojis
            }
            
        except Exception as e:
            logger.error(f"Failed to load cache for guild {guild_id}: {e}")
            self._cache[guild_id] = {"unicode": set(), "custom": set()}
    
    def _update_cache_add(self, guild_id: int, emoji_type: str, emoji_value: str) -> None:
        """Update cache when adding emoji."""
        if guild_id not in self._cache:
            self._cache[guild_id] = {"unicode": set(), "custom": set()}
        
        if emoji_type == "unicode":
            self._cache[guild_id]["unicode"].add(emoji_value)
        else:
            self._cache[guild_id]["custom"].add(emoji_value)
    
    def _update_cache_remove(self, guild_id: int, emoji_type: str, emoji_value: str) -> None:
        """Update cache when removing emoji."""
        if guild_id in self._cache:
            if emoji_type == "unicode":
                self._cache[guild_id]["unicode"].discard(emoji_value)
            else:
                self._cache[guild_id]["custom"].discard(emoji_value)
    
    def _get_emoji_display_string(self, emoji_type: str, emoji_value: str, emoji_name: Optional[str]) -> str:
        """Get display string for an emoji based on its type and values."""
        if emoji_type == "unicode":
            return emoji_value
        else:
            # Custom emoji
            name = emoji_name or 'unknown'
            return f"<:{name}:{emoji_value}>"
    
    async def migrate_from_global_blacklist(self, guild_id: int, unicode_emojis: set, custom_emoji_ids: set, custom_emoji_names: dict) -> None:
        """
        Migrate global blacklist data to guild-specific format.
        
        Args:
            guild_id: Discord guild ID to migrate data for
            unicode_emojis: Set of Unicode emoji strings
            custom_emoji_ids: Set of custom emoji IDs
            custom_emoji_names: Dict mapping custom emoji IDs to names
        """
        try:
            # Clear existing data for this guild
            await self.clear_blacklist(guild_id)
            
            # Add Unicode emojis
            for emoji in unicode_emojis:
                await self.add_emoji(guild_id, emoji)
            
            # Add custom emojis
            for emoji_id in custom_emoji_ids:
                emoji_name = custom_emoji_names.get(emoji_id, 'unknown')
                # Create a PartialEmoji to add
                partial_emoji = discord.PartialEmoji(name=emoji_name, id=emoji_id)
                await self.add_emoji(guild_id, partial_emoji)
            
            logger.info(f"Migrated {len(unicode_emojis)} Unicode and {len(custom_emoji_ids)} custom emojis for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Failed to migrate blacklist for guild {guild_id}: {e}")
            raise