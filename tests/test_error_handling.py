"""
Tests for error handling and graceful degradation functionality.
"""

import pytest
import asyncio
import sqlite3
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from database.manager import DatabaseManager, DatabaseError
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.models import GuildConfig


class TestDatabaseErrorHandling:
    """Test database error handling and recovery mechanisms."""
    
    @pytest.fixture
    def db_manager(self):
        """Create a test database manager."""
        return DatabaseManager(":memory:")
    
    @pytest.fixture
    def guild_config_manager(self, db_manager):
        """Create a test guild config manager."""
        return GuildConfigManager(db_manager)
    
    @pytest.fixture
    def guild_blacklist_manager(self, db_manager):
        """Create a test guild blacklist manager."""
        return GuildBlacklistManager(db_manager)
    
    @pytest.mark.asyncio
    async def test_database_locked_retry_mechanism(self, db_manager):
        """Test that database locked errors trigger retry mechanism."""
        with patch.object(db_manager, 'fetch_one') as mock_fetch:
            # Simulate database locked error followed by success
            mock_fetch.side_effect = [
                sqlite3.OperationalError("database is locked"),
                {"guild_id": 123, "timeout_duration": 300}
            ]
            
            # This should succeed after retry
            result = await db_manager.fetch_one("SELECT * FROM guild_configs WHERE guild_id = ?", (123,))
            assert result is not None
            assert mock_fetch.call_count == 2
    
    @pytest.mark.asyncio
    async def test_database_error_fallback_to_default_config(self, guild_config_manager):
        """Test that database errors fall back to default configuration."""
        with patch.object(guild_config_manager.db_manager, 'fetch_one') as mock_fetch:
            # Simulate database error
            mock_fetch.side_effect = DatabaseError("Database connection failed")
            
            # Should return default config
            config = await guild_config_manager.get_guild_config(123)
            assert config.guild_id == 123
            assert config.timeout_duration == 300  # Default value
            assert config.log_channel_id is None
    
    @pytest.mark.asyncio
    async def test_database_error_uses_cached_config(self, guild_config_manager):
        """Test that database errors use cached configuration when available."""
        # First, populate cache with a successful call
        with patch.object(guild_config_manager.db_manager, 'fetch_one') as mock_fetch:
            mock_fetch.return_value = {
                "guild_id": 123,
                "log_channel_id": 456,
                "timeout_duration": 600,
                "dm_on_timeout": True,
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
            
            config = await guild_config_manager.get_guild_config(123)
            assert config.timeout_duration == 600
        
        # Now simulate database error - should use cached config
        with patch.object(guild_config_manager.db_manager, 'fetch_one') as mock_fetch:
            mock_fetch.side_effect = DatabaseError("Database connection failed")
            
            config = await guild_config_manager.get_guild_config(123)
            assert config.timeout_duration == 600  # From cache
            assert config.log_channel_id == 456
    
    @pytest.mark.asyncio
    async def test_blacklist_database_error_fallback_to_cache(self, guild_blacklist_manager):
        """Test that blacklist database errors fall back to cache."""
        # First, populate cache
        guild_blacklist_manager._cache[123] = {
            "unicode": {"😀", "😂"},
            "custom": {"123456", "789012"}
        }
        
        with patch.object(guild_blacklist_manager.db_manager, 'fetch_all') as mock_fetch:
            mock_fetch.side_effect = DatabaseError("Database connection failed")
            
            # Should return cached data
            result = await guild_blacklist_manager.get_all_blacklisted(123)
            assert len(result) == 4  # 2 unicode + 2 custom
            
            # Verify cache data is returned
            unicode_emojis = [r for r in result if r['emoji_type'] == 'unicode']
            custom_emojis = [r for r in result if r['emoji_type'] == 'custom']
            assert len(unicode_emojis) == 2
            assert len(custom_emojis) == 2
    
    @pytest.mark.asyncio
    async def test_blacklist_add_emoji_database_error_updates_cache(self, guild_blacklist_manager):
        """Test that adding emoji with database error still updates cache."""
        with patch.object(guild_blacklist_manager.db_manager, 'execute_query') as mock_execute:
            mock_execute.side_effect = DatabaseError("Database connection failed")
            
            # Should still return True and update cache
            result = await guild_blacklist_manager.add_emoji(123, "😀")
            assert result is True
            
            # Verify cache was updated
            assert 123 in guild_blacklist_manager._cache
            assert "😀" in guild_blacklist_manager._cache[123]["unicode"]
    
    @pytest.mark.asyncio
    async def test_config_update_database_error_updates_cache(self, guild_config_manager):
        """Test that config updates with database errors still update cache."""
        # First, get a config to populate cache
        with patch.object(guild_config_manager.db_manager, 'fetch_one') as mock_fetch:
            mock_fetch.return_value = {
                "guild_id": 123,
                "log_channel_id": None,
                "timeout_duration": 300,
                "dm_on_timeout": False,
                "created_at": "2023-01-01T00:00:00",
                "updated_at": "2023-01-01T00:00:00"
            }
            config = await guild_config_manager.get_guild_config(123)
        
        # Now simulate database error during update
        with patch.object(guild_config_manager.db_manager, 'execute_query') as mock_execute:
            mock_execute.side_effect = DatabaseError("Database connection failed")
            
            # Should raise error but still update cache
            with pytest.raises(DatabaseError):
                await guild_config_manager.update_guild_config(123, timeout_duration=600)
            
            # Verify cache was updated despite database error
            cached_config = guild_config_manager.get_cached_config(123)
            assert cached_config.timeout_duration == 600


class TestLoggingChannelErrorHandling:
    """Test error handling for logging channel issues."""
    
    @pytest.fixture
    def mock_guild(self):
        """Create a mock Discord guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.name = "Test Guild"
        guild.id = 123
        guild.me = MagicMock()
        return guild
    
    @pytest.fixture
    def mock_guild_config(self):
        """Create a mock guild configuration."""
        config = MagicMock()
        config.log_channel_id = 456
        return config
    
    @pytest.mark.asyncio
    async def test_log_channel_not_found_clears_config(self, mock_guild, mock_guild_config):
        """Test that non-existent log channels are cleared from config."""
        # Mock guild.get_channel to return None
        mock_guild.get_channel.return_value = None
        
        # Mock guild.fetch_channel to raise NotFound
        mock_guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Channel not found"))
        
        # Mock the bot's guild_config_manager
        with patch('main.bot') as mock_bot:
            mock_bot.guild_config_manager.update_guild_config = AsyncMock()
            
            # Import and call the function
            from main import log_guild_action
            await log_guild_action(mock_guild, mock_guild_config, "Test message")
            
            # Verify that the config was updated to clear the invalid channel
            mock_bot.guild_config_manager.update_guild_config.assert_called_once_with(
                123, log_channel_id=None
            )
    
    @pytest.mark.asyncio
    async def test_log_channel_forbidden_access_handled_gracefully(self, mock_guild, mock_guild_config):
        """Test that forbidden access to log channels is handled gracefully."""
        mock_guild.get_channel.return_value = None
        mock_guild.fetch_channel = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "No permission"))
        
        # Should not raise an exception
        from main import log_guild_action
        await log_guild_action(mock_guild, mock_guild_config, "Test message")
    
    @pytest.mark.asyncio
    async def test_log_channel_deleted_during_send_clears_config(self, mock_guild, mock_guild_config):
        """Test that channels deleted during send are cleared from config."""
        # Mock a valid text channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.permissions_for.return_value.send_messages = True
        mock_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "Not Found"))
        mock_channel.send.side_effect.status = 404
        
        mock_guild.get_channel.return_value = mock_channel
        
        with patch('main.bot') as mock_bot:
            mock_bot.guild_config_manager.update_guild_config = AsyncMock()
            
            from main import log_guild_action
            await log_guild_action(mock_guild, mock_guild_config, "Test message")
            
            # Verify that the config was updated to clear the deleted channel
            mock_bot.guild_config_manager.update_guild_config.assert_called_once_with(
                123, log_channel_id=None
            )
    
    @pytest.mark.asyncio
    async def test_log_channel_no_permissions_handled_gracefully(self, mock_guild, mock_guild_config):
        """Test that lack of permissions in log channel is handled gracefully."""
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.permissions_for.return_value.send_messages = False
        
        mock_guild.get_channel.return_value = mock_channel
        
        # Should not raise an exception
        from main import log_guild_action
        await log_guild_action(mock_guild, mock_guild_config, "Test message")


class TestReactionHandlingErrorRecovery:
    """Test error recovery in reaction handling."""
    
    @pytest.mark.asyncio
    async def test_guild_config_error_uses_default(self):
        """Test that guild config errors use default configuration."""
        with patch('main.bot') as mock_bot:
            # Simulate database error
            mock_bot.guild_config_manager.get_guild_config = AsyncMock(
                side_effect=Exception("Database error")
            )
            
            # Mock other required objects
            mock_guild = MagicMock()
            mock_guild.name = "Test Guild"
            mock_guild.id = 123
            
            mock_payload = MagicMock()
            mock_payload.guild_id = 123
            mock_payload.user_id = 456
            mock_payload.emoji = "😀"
            
            mock_bot.get_guild.return_value = mock_guild
            mock_bot.guild_blacklist_manager.is_blacklisted = AsyncMock(return_value=False)
            
            # Import and test the reaction handler
            from main import bot
            
            # This should not raise an exception and should use default config
            await bot.on_raw_reaction_add(mock_payload)
    
    @pytest.mark.asyncio
    async def test_blacklist_check_error_assumes_not_blacklisted(self):
        """Test that blacklist check errors assume emoji is not blacklisted."""
        with patch('main.bot') as mock_bot:
            # Mock successful config retrieval
            mock_config = MagicMock()
            mock_bot.guild_config_manager.get_guild_config = AsyncMock(return_value=mock_config)
            
            # Simulate blacklist check error
            mock_bot.guild_blacklist_manager.is_blacklisted = AsyncMock(
                side_effect=Exception("Database error")
            )
            
            mock_guild = MagicMock()
            mock_guild.name = "Test Guild"
            mock_guild.id = 123
            
            mock_payload = MagicMock()
            mock_payload.guild_id = 123
            mock_payload.user_id = 456
            mock_payload.emoji = "😀"
            
            mock_bot.get_guild.return_value = mock_guild
            
            from main import bot
            
            # This should not raise an exception and should return early
            await bot.on_raw_reaction_add(mock_payload)


class TestCommandErrorHandling:
    """Test error handling in bot commands."""
    
    @pytest.mark.asyncio
    async def test_blacklist_command_database_error_message(self):
        """Test that blacklist command shows appropriate error message for database errors."""
        with patch('main.bot') as mock_bot:
            mock_bot.guild_blacklist_manager.get_blacklist_display = AsyncMock(
                side_effect=Exception("Database connection failed")
            )
            
            mock_ctx = MagicMock()
            mock_ctx.guild.name = "Test Guild"
            mock_ctx.guild.id = 123
            mock_ctx.send = AsyncMock()
            
            from main import blacklist_command
            
            await blacklist_command(mock_ctx)
            
            # Should send database-specific error message
            mock_ctx.send.assert_called_once()
            call_args = mock_ctx.send.call_args[0][0]
            assert "Database error occurred" in call_args


if __name__ == "__main__":
    pytest.main([__file__])