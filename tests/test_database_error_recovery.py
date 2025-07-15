"""
Simple tests for database error recovery mechanisms.
"""

import pytest
import sqlite3
from unittest.mock import AsyncMock, patch, MagicMock
from database.manager import DatabaseManager, DatabaseError
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.models import GuildConfig


class TestDatabaseErrorRecovery:
    """Test database error recovery with simple mocking."""
    
    @pytest.mark.asyncio
    async def test_database_manager_retry_on_locked_database(self):
        """Test that DatabaseManager retries on locked database errors."""
        db_manager = DatabaseManager(":memory:")
        
        with patch('aiosqlite.connect') as mock_connect:
            # Mock connection that raises locked error first, then succeeds
            mock_db = AsyncMock()
            mock_cursor = AsyncMock()
            mock_cursor.lastrowid = 123
            
            # First call raises locked error, second succeeds
            mock_db.execute.side_effect = [
                sqlite3.OperationalError("database is locked"),
                mock_cursor
            ]
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            # Should succeed after retry
            result = await db_manager.execute_query("INSERT INTO test VALUES (?)", ("value",))
            assert result == 123
            assert mock_db.execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_guild_config_manager_fallback_to_default(self):
        """Test that GuildConfigManager falls back to default config on database errors."""
        mock_db_manager = AsyncMock()
        mock_db_manager.fetch_one.side_effect = DatabaseError("Connection failed")
        
        config_manager = GuildConfigManager(mock_db_manager)
        
        # Should return default config when database fails
        config = await config_manager.get_guild_config(123)
        assert config.guild_id == 123
        assert config.timeout_duration == 300  # Default value
        assert config.log_channel_id is None
    
    @pytest.mark.asyncio
    async def test_guild_config_manager_uses_cache_on_error(self):
        """Test that GuildConfigManager uses cache when database fails."""
        mock_db_manager = AsyncMock()
        config_manager = GuildConfigManager(mock_db_manager)
        
        # First, populate cache with successful call
        mock_db_manager.fetch_one.return_value = {
            "guild_id": 123,
            "log_channel_id": 456,
            "timeout_duration": 600,
            "dm_on_timeout": True,
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }
        
        config = await config_manager.get_guild_config(123)
        assert config.timeout_duration == 600
        
        # Now simulate database error - should use cached config
        mock_db_manager.fetch_one.side_effect = DatabaseError("Connection failed")
        
        config = await config_manager.get_guild_config(123)
        assert config.timeout_duration == 600  # From cache
        assert config.log_channel_id == 456
    
    @pytest.mark.asyncio
    async def test_guild_blacklist_manager_cache_fallback(self):
        """Test that GuildBlacklistManager falls back to cache on database errors."""
        mock_db_manager = AsyncMock()
        blacklist_manager = GuildBlacklistManager(mock_db_manager)
        
        # Populate cache manually
        blacklist_manager._cache[123] = {
            "unicode": {"😀", "😂"},
            "custom": {"123456"}
        }
        
        # Simulate database error
        mock_db_manager.fetch_all.side_effect = DatabaseError("Connection failed")
        
        # Should return cached data
        result = await blacklist_manager.get_all_blacklisted(123)
        assert len(result) == 3  # 2 unicode + 1 custom
        
        unicode_emojis = [r for r in result if r['emoji_type'] == 'unicode']
        custom_emojis = [r for r in result if r['emoji_type'] == 'custom']
        assert len(unicode_emojis) == 2
        assert len(custom_emojis) == 1
    
    @pytest.mark.asyncio
    async def test_guild_blacklist_manager_add_emoji_updates_cache_on_db_error(self):
        """Test that adding emoji updates cache even when database fails."""
        mock_db_manager = AsyncMock()
        mock_db_manager.execute_query.side_effect = DatabaseError("Connection failed")
        
        blacklist_manager = GuildBlacklistManager(mock_db_manager)
        
        # Mock is_blacklisted to return False (not already blacklisted)
        with patch.object(blacklist_manager, 'is_blacklisted', return_value=False):
            # Should still return True and update cache
            result = await blacklist_manager.add_emoji(123, "😀")
            assert result is True
            
            # Verify cache was updated
            assert 123 in blacklist_manager._cache
            assert "😀" in blacklist_manager._cache[123]["unicode"]
    
    @pytest.mark.asyncio
    async def test_config_update_maintains_cache_consistency_on_db_error(self):
        """Test that config updates maintain cache consistency even when database fails."""
        mock_db_manager = AsyncMock()
        config_manager = GuildConfigManager(mock_db_manager)
        
        # First, get a config to populate cache
        mock_db_manager.fetch_one.return_value = {
            "guild_id": 123,
            "log_channel_id": None,
            "timeout_duration": 300,
            "dm_on_timeout": False,
            "created_at": "2023-01-01T00:00:00",
            "updated_at": "2023-01-01T00:00:00"
        }
        
        config = await config_manager.get_guild_config(123)
        assert config.timeout_duration == 300
        
        # Now simulate database error during update
        mock_db_manager.execute_query.side_effect = DatabaseError("Connection failed")
        
        # Should raise error but still update cache
        with pytest.raises(DatabaseError):
            await config_manager.update_guild_config(123, timeout_duration=600)
        
        # Verify cache was updated despite database error
        cached_config = config_manager.get_cached_config(123)
        assert cached_config.timeout_duration == 600


class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""
    
    @pytest.mark.asyncio
    async def test_database_error_propagation(self):
        """Test that database errors are properly wrapped and propagated."""
        db_manager = DatabaseManager(":memory:")
        
        with patch('aiosqlite.connect') as mock_connect:
            # Simulate a persistent database error
            mock_connect.side_effect = sqlite3.Error("Disk I/O error")
            
            # Should raise DatabaseError, not sqlite3.Error
            with pytest.raises(DatabaseError) as exc_info:
                await db_manager.execute_query("SELECT 1")
            
            assert "Database error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_integrity_error_handling(self):
        """Test that integrity errors are properly handled."""
        db_manager = DatabaseManager(":memory:")
        
        with patch('aiosqlite.connect') as mock_connect:
            mock_db = AsyncMock()
            mock_db.execute.side_effect = sqlite3.IntegrityError("UNIQUE constraint failed")
            mock_connect.return_value.__aenter__.return_value = mock_db
            
            # Should raise DatabaseError with integrity violation message
            with pytest.raises(DatabaseError) as exc_info:
                await db_manager.execute_query("INSERT INTO test VALUES (?)", ("duplicate",))
            
            assert "Data integrity violation" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])