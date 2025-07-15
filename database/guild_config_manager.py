"""
Guild configuration management system.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from database.manager import DatabaseManager
from database.models import GuildConfig

logger = logging.getLogger(__name__)


class GuildConfigManager:
    """Manages guild-specific configuration settings with CRUD operations."""
    
    def __init__(self, db_manager: DatabaseManager):
        """Initialize with database manager instance."""
        self.db_manager = db_manager
        self._config_cache: Dict[int, GuildConfig] = {}
    
    async def get_guild_config(self, guild_id: int) -> GuildConfig:
        """
        Get guild configuration, creating default if it doesn't exist.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            GuildConfig object with current or default settings
        """
        # Check cache first
        if guild_id in self._config_cache:
            return self._config_cache[guild_id]
        
        try:
            # Try to fetch from database
            query = """
                SELECT guild_id, log_channel_id, timeout_duration, dm_on_timeout, 
                       created_at, updated_at
                FROM guild_configs 
                WHERE guild_id = ?
            """
            row = await self.db_manager.fetch_one(query, (guild_id,))
            
            if row:
                config = GuildConfig(
                    guild_id=row['guild_id'],
                    log_channel_id=row['log_channel_id'],
                    timeout_duration=row['timeout_duration'],
                    dm_on_timeout=bool(row['dm_on_timeout']),
                    created_at=datetime.fromisoformat(row['created_at']) if row['created_at'] else None,
                    updated_at=datetime.fromisoformat(row['updated_at']) if row['updated_at'] else None
                )
                # Cache the config
                self._config_cache[guild_id] = config
                return config
            else:
                # Create default configuration if none exists
                return await self.create_default_config(guild_id)
                
        except Exception as e:
            logger.error(f"Failed to get guild config for {guild_id}: {e}")
            # Return default config as fallback
            return GuildConfig(guild_id=guild_id)
    
    async def create_default_config(self, guild_id: int) -> GuildConfig:
        """
        Create default configuration for a new guild.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            GuildConfig object with default settings
        """
        try:
            now = datetime.now()
            query = """
                INSERT INTO guild_configs (guild_id, log_channel_id, timeout_duration, 
                                         dm_on_timeout, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            await self.db_manager.execute_query(
                query, 
                (guild_id, None, 300, False, now.isoformat(), now.isoformat())
            )
            
            config = GuildConfig(
                guild_id=guild_id,
                log_channel_id=None,
                timeout_duration=300,
                dm_on_timeout=False,
                created_at=now,
                updated_at=now
            )
            
            # Cache the new config
            self._config_cache[guild_id] = config
            logger.info(f"Created default configuration for guild {guild_id}")
            return config
            
        except Exception as e:
            logger.error(f"Failed to create default config for guild {guild_id}: {e}")
            # Return in-memory default as fallback
            return GuildConfig(guild_id=guild_id)
    
    async def update_guild_config(self, guild_id: int, **kwargs) -> None:
        """
        Update guild configuration with provided settings.
        
        Args:
            guild_id: Discord guild ID
            **kwargs: Configuration fields to update (log_channel_id, timeout_duration, dm_on_timeout)
            
        Raises:
            ValueError: If invalid configuration values are provided
        """
        # Validate input parameters
        self._validate_config_update(kwargs)
        
        try:
            # Get current config to ensure it exists
            current_config = await self.get_guild_config(guild_id)
            
            # Build update query dynamically based on provided kwargs
            update_fields = []
            params = []
            
            for field, value in kwargs.items():
                if field in ['log_channel_id', 'timeout_duration', 'dm_on_timeout']:
                    update_fields.append(f"{field} = ?")
                    params.append(value)
            
            if not update_fields:
                logger.warning(f"No valid fields to update for guild {guild_id}")
                return
            
            # Always update the updated_at timestamp
            update_fields.append("updated_at = ?")
            params.append(datetime.now().isoformat())
            params.append(guild_id)
            
            query = f"""
                UPDATE guild_configs 
                SET {', '.join(update_fields)}
                WHERE guild_id = ?
            """
            
            await self.db_manager.execute_query(query, tuple(params))
            
            # Update cache
            if guild_id in self._config_cache:
                config = self._config_cache[guild_id]
                for field, value in kwargs.items():
                    if hasattr(config, field):
                        setattr(config, field, value)
                config.updated_at = datetime.now()
            
            logger.info(f"Updated configuration for guild {guild_id}: {kwargs}")
            
        except Exception as e:
            logger.error(f"Failed to update guild config for {guild_id}: {e}")
            raise
    
    async def delete_guild_config(self, guild_id: int) -> None:
        """
        Delete guild configuration and associated data.
        
        Args:
            guild_id: Discord guild ID
        """
        try:
            # Delete guild configuration
            query = "DELETE FROM guild_configs WHERE guild_id = ?"
            await self.db_manager.execute_query(query, (guild_id,))
            
            # Remove from cache
            if guild_id in self._config_cache:
                del self._config_cache[guild_id]
            
            logger.info(f"Deleted configuration for guild {guild_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete guild config for {guild_id}: {e}")
            raise
    
    def _validate_config_update(self, kwargs: Dict[str, Any]) -> None:
        """
        Validate configuration update parameters.
        
        Args:
            kwargs: Configuration fields to validate
            
        Raises:
            ValueError: If invalid configuration values are provided
        """
        if 'timeout_duration' in kwargs:
            timeout = kwargs['timeout_duration']
            if not isinstance(timeout, int) or timeout < 0 or timeout > 2419200:  # Max 28 days
                raise ValueError("timeout_duration must be an integer between 0 and 2419200 seconds")
        
        if 'log_channel_id' in kwargs:
            channel_id = kwargs['log_channel_id']
            if channel_id is not None and (not isinstance(channel_id, int) or channel_id <= 0):
                raise ValueError("log_channel_id must be a positive integer or None")
        
        if 'dm_on_timeout' in kwargs:
            dm_setting = kwargs['dm_on_timeout']
            if not isinstance(dm_setting, bool):
                raise ValueError("dm_on_timeout must be a boolean value")
    
    def clear_cache(self) -> None:
        """Clear the configuration cache."""
        self._config_cache.clear()
        logger.info("Configuration cache cleared")
    
    def get_cached_config(self, guild_id: int) -> Optional[GuildConfig]:
        """
        Get cached configuration without database access.
        
        Args:
            guild_id: Discord guild ID
            
        Returns:
            Cached GuildConfig or None if not cached
        """
        return self._config_cache.get(guild_id)