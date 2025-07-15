"""
Unit tests for GuildConfigManager.
"""

import pytest
import asyncio
import tempfile
import os
from datetime import datetime
from unittest.mock import AsyncMock, patch
from database.manager import DatabaseManager
from database.guild_config_manager import GuildConfigManager
from database.models import GuildConfig


class TestGuildConfigManager:
    """Test cases for GuildConfigManager functionality."""
    
    @pytest.fixture
    def db_manager(self):
        """Create a temporary database manager for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name
        
        manager = DatabaseManager(db_path)
        
        # Initialize database synchronously for testing
        async def init_db():
            await manager.initialize_database()
        
        asyncio.run(init_db())
        
        yield manager
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.fixture
    def config_manager(self, db_manager):
        """Create GuildConfigManager instance for testing."""
        return GuildConfigManager(db_manager)
    
    @pytest.mark.asyncio
    async def test_create_default_config(self, config_manager):
        """Test creating default configuration for a new guild."""
        guild_id = 12345
        
        config = await config_manager.create_default_config(guild_id)
        
        assert config.guild_id == guild_id
        assert config.log_channel_id is None
        assert config.timeout_duration == 300
        assert config.dm_on_timeout is False
        assert config.created_at is not None
        assert config.updated_at is not None
        
        # Verify it's cached
        cached_config = config_manager.get_cached_config(guild_id)
        assert cached_config is not None
        assert cached_config.guild_id == guild_id
    
    @pytest.mark.asyncio
    async def test_get_guild_config_existing(self, config_manager):
        """Test getting existing guild configuration."""
        guild_id = 12345
        
        # Create default config first
        await config_manager.create_default_config(guild_id)
        
        # Get the config
        config = await config_manager.get_guild_config(guild_id)
        
        assert config.guild_id == guild_id
        assert config.timeout_duration == 300
    
    @pytest.mark.asyncio
    async def test_get_guild_config_nonexistent(self, config_manager):
        """Test getting configuration for non-existent guild creates default."""
        guild_id = 99999
        
        config = await config_manager.get_guild_config(guild_id)
        
        assert config.guild_id == guild_id
        assert config.timeout_duration == 300
        
        # Should be cached now
        cached_config = config_manager.get_cached_config(guild_id)
        assert cached_config is not None
    
    @pytest.mark.asyncio
    async def test_update_guild_config_valid(self, config_manager):
        """Test updating guild configuration with valid values."""
        guild_id = 12345
        
        # Create default config first
        await config_manager.create_default_config(guild_id)
        
        # Update configuration
        await config_manager.update_guild_config(
            guild_id,
            log_channel_id=67890,
            timeout_duration=600,
            dm_on_timeout=True
        )
        
        # Verify updates
        config = await config_manager.get_guild_config(guild_id)
        assert config.log_channel_id == 67890
        assert config.timeout_duration == 600
        assert config.dm_on_timeout is True
    
    @pytest.mark.asyncio
    async def test_update_guild_config_partial(self, config_manager):
        """Test partial update of guild configuration."""
        guild_id = 12345
        
        # Create default config first
        await config_manager.create_default_config(guild_id)
        
        # Update only timeout duration
        await config_manager.update_guild_config(guild_id, timeout_duration=900)
        
        # Verify only timeout was updated
        config = await config_manager.get_guild_config(guild_id)
        assert config.timeout_duration == 900
        assert config.log_channel_id is None  # Should remain unchanged
        assert config.dm_on_timeout is False  # Should remain unchanged
    
    @pytest.mark.asyncio
    async def test_update_guild_config_invalid_timeout(self, config_manager):
        """Test updating with invalid timeout duration raises ValueError."""
        guild_id = 12345
        
        await config_manager.create_default_config(guild_id)
        
        # Test negative timeout
        with pytest.raises(ValueError, match="timeout_duration must be an integer"):
            await config_manager.update_guild_config(guild_id, timeout_duration=-1)
        
        # Test timeout too large (more than 28 days)
        with pytest.raises(ValueError, match="timeout_duration must be an integer"):
            await config_manager.update_guild_config(guild_id, timeout_duration=2419201)
        
        # Test non-integer timeout
        with pytest.raises(ValueError, match="timeout_duration must be an integer"):
            await config_manager.update_guild_config(guild_id, timeout_duration="invalid")
    
    @pytest.mark.asyncio
    async def test_update_guild_config_invalid_channel_id(self, config_manager):
        """Test updating with invalid channel ID raises ValueError."""
        guild_id = 12345
        
        await config_manager.create_default_config(guild_id)
        
        # Test negative channel ID
        with pytest.raises(ValueError, match="log_channel_id must be a positive integer"):
            await config_manager.update_guild_config(guild_id, log_channel_id=-1)
        
        # Test zero channel ID
        with pytest.raises(ValueError, match="log_channel_id must be a positive integer"):
            await config_manager.update_guild_config(guild_id, log_channel_id=0)
        
        # Test string channel ID
        with pytest.raises(ValueError, match="log_channel_id must be a positive integer"):
            await config_manager.update_guild_config(guild_id, log_channel_id="invalid")
    
    @pytest.mark.asyncio
    async def test_update_guild_config_invalid_dm_setting(self, config_manager):
        """Test updating with invalid DM setting raises ValueError."""
        guild_id = 12345
        
        await config_manager.create_default_config(guild_id)
        
        # Test non-boolean DM setting
        with pytest.raises(ValueError, match="dm_on_timeout must be a boolean"):
            await config_manager.update_guild_config(guild_id, dm_on_timeout="yes")
        
        with pytest.raises(ValueError, match="dm_on_timeout must be a boolean"):
            await config_manager.update_guild_config(guild_id, dm_on_timeout=1)
    
    @pytest.mark.asyncio
    async def test_delete_guild_config(self, config_manager):
        """Test deleting guild configuration."""
        guild_id = 12345
        
        # Create config first
        await config_manager.create_default_config(guild_id)
        
        # Verify it exists
        config = await config_manager.get_guild_config(guild_id)
        assert config.guild_id == guild_id
        
        # Delete the config
        await config_manager.delete_guild_config(guild_id)
        
        # Verify it's removed from cache
        cached_config = config_manager.get_cached_config(guild_id)
        assert cached_config is None
        
        # Getting config again should create a new default
        new_config = await config_manager.get_guild_config(guild_id)
        assert new_config.guild_id == guild_id
    
    @pytest.mark.asyncio
    async def test_cache_functionality(self, config_manager):
        """Test configuration caching functionality."""
        guild_id = 12345
        
        # Initially no cache
        assert config_manager.get_cached_config(guild_id) is None
        
        # Create config (should be cached)
        await config_manager.create_default_config(guild_id)
        cached_config = config_manager.get_cached_config(guild_id)
        assert cached_config is not None
        assert cached_config.guild_id == guild_id
        
        # Clear cache
        config_manager.clear_cache()
        assert config_manager.get_cached_config(guild_id) is None
    
    @pytest.mark.asyncio
    async def test_database_error_handling(self, config_manager):
        """Test graceful handling of database errors."""
        guild_id = 12345
        
        # Mock database manager to raise exception
        with patch.object(config_manager.db_manager, 'fetch_one', side_effect=Exception("DB Error")):
            # Should return default config as fallback
            config = await config_manager.get_guild_config(guild_id)
            assert config.guild_id == guild_id
            assert config.timeout_duration == 300  # Default value
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_guild(self, config_manager):
        """Test updating configuration for non-existent guild creates it first."""
        guild_id = 99999
        
        # Update config for non-existent guild
        await config_manager.update_guild_config(guild_id, timeout_duration=450)
        
        # Should have created the guild and applied the update
        config = await config_manager.get_guild_config(guild_id)
        assert config.guild_id == guild_id
        assert config.timeout_duration == 450
    
    @pytest.mark.asyncio
    async def test_update_with_no_valid_fields(self, config_manager):
        """Test update with no valid fields logs warning but doesn't fail."""
        guild_id = 12345
        
        await config_manager.create_default_config(guild_id)
        
        # Update with invalid field name (should be ignored)
        await config_manager.update_guild_config(guild_id, invalid_field="value")
        
        # Config should remain unchanged
        config = await config_manager.get_guild_config(guild_id)
        assert config.timeout_duration == 300  # Default unchanged
    
    @pytest.mark.asyncio
    async def test_concurrent_access(self, config_manager):
        """Test concurrent access to guild configurations."""
        guild_id = 12345
        
        # Create multiple concurrent requests
        tasks = [
            config_manager.get_guild_config(guild_id),
            config_manager.get_guild_config(guild_id),
            config_manager.get_guild_config(guild_id)
        ]
        
        configs = await asyncio.gather(*tasks)
        
        # All should return the same guild_id
        for config in configs:
            assert config.guild_id == guild_id
            assert config.timeout_duration == 300