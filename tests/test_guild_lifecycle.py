"""
Tests for guild lifecycle management functionality.
Tests automatic guild initialization and cleanup when bot joins/leaves guilds.
"""

import pytest
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Import the bot and managers
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.guild_config_manager import GuildConfigManager
from database.models import GuildConfig


class TestGuildLifecycle:
    """Test suite for guild lifecycle management."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.guild_config_manager = AsyncMock(spec=GuildConfigManager)
        bot.guild_config_manager._config_cache = {}
        return bot
    
    @pytest.fixture
    def mock_guild(self):
        """Create a mock guild."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 12345
        guild.name = "Test Guild"
        guild.member_count = 100
        return guild
    
    @pytest.fixture
    def mock_guild_config(self):
        """Create a mock guild configuration."""
        return GuildConfig(
            guild_id=12345,
            log_channel_id=None,
            timeout_duration=300,
            dm_on_timeout=False,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    @pytest.mark.asyncio
    async def test_on_guild_join_creates_default_config(self, mock_bot, mock_guild, mock_guild_config):
        """Test that joining a guild creates default configuration."""
        # Setup mock
        mock_bot.guild_config_manager.create_default_config.return_value = mock_guild_config
        
        # Import and test the event handler
        from main import on_guild_join
        
        # Mock the bot instance in the event handler
        with patch('main.bot', mock_bot):
            await on_guild_join(mock_guild)
        
        # Verify default config was created
        mock_bot.guild_config_manager.create_default_config.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_on_guild_join_logs_guild_info(self, mock_bot, mock_guild, mock_guild_config):
        """Test that guild join event logs appropriate information."""
        # Setup mock
        mock_bot.guild_config_manager.create_default_config.return_value = mock_guild_config
        
        from main import on_guild_join
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            await on_guild_join(mock_guild)
        
        # Verify logging calls
        mock_logger.info.assert_any_call(
            "Bot joined guild 'Test Guild' (ID: 12345). Created default configuration."
        )
        mock_logger.info.assert_any_call(
            "Guild 'Test Guild' has 100 members"
        )

    @pytest.mark.asyncio
    async def test_on_guild_join_handles_config_creation_failure(self, mock_bot, mock_guild):
        """Test that guild join handles configuration creation failures gracefully."""
        # Setup mock to raise exception
        mock_bot.guild_config_manager.create_default_config.side_effect = Exception("Database error")
        
        from main import on_guild_join
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            # Should not raise exception
            await on_guild_join(mock_guild)
        
        # Verify error was logged
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Failed to initialize configuration" in error_call
        assert "Test Guild" in error_call

    @pytest.mark.asyncio
    async def test_on_guild_remove_clears_cache(self, mock_bot, mock_guild):
        """Test that leaving a guild clears cached configuration."""
        # Setup cache with guild data
        mock_bot.guild_config_manager._config_cache = {12345: MagicMock()}
        
        from main import on_guild_remove
        
        with patch('main.bot', mock_bot):
            await on_guild_remove(mock_guild)
        
        # Verify cache was cleared
        assert 12345 not in mock_bot.guild_config_manager._config_cache

    @pytest.mark.asyncio
    async def test_on_guild_remove_logs_guild_info(self, mock_bot, mock_guild):
        """Test that guild remove event logs appropriate information."""
        from main import on_guild_remove
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            await on_guild_remove(mock_guild)
        
        # Verify logging calls
        mock_logger.info.assert_any_call(
            "Bot left guild 'Test Guild' (ID: 12345)"
        )
        mock_logger.info.assert_any_call(
            "Cleaned up cached data for guild 'Test Guild' (ID: 12345)"
        )

    @pytest.mark.asyncio
    async def test_on_guild_remove_handles_cleanup_failure(self, mock_bot, mock_guild):
        """Test that guild remove handles cleanup failures gracefully."""
        # Setup mock to raise exception when accessing cache
        mock_bot.guild_config_manager._config_cache = MagicMock()
        mock_bot.guild_config_manager._config_cache.pop.side_effect = Exception("Cache error")
        
        from main import on_guild_remove
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            # Should not raise exception
            await on_guild_remove(mock_guild)
        
        # Verify error was logged
        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Error during guild cleanup" in error_call
        assert "Test Guild" in error_call

    @pytest.mark.asyncio
    async def test_on_guild_remove_handles_missing_cache_attribute(self, mock_bot, mock_guild):
        """Test guild remove when bot doesn't have cache attribute."""
        # Remove cache attribute
        if hasattr(mock_bot.guild_config_manager, '_config_cache'):
            delattr(mock_bot.guild_config_manager, '_config_cache')
        
        from main import on_guild_remove
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            # Should not raise exception
            await on_guild_remove(mock_guild)
        
        # Should still log basic info
        mock_logger.info.assert_any_call(
            "Bot left guild 'Test Guild' (ID: 12345)"
        )

    @pytest.mark.asyncio
    async def test_reaction_handler_creates_config_automatically(self, mock_bot, mock_guild):
        """Test that reaction handler creates guild config automatically when needed."""
        # Setup mock payload
        payload = MagicMock()
        payload.user_id = 67890
        payload.guild_id = 12345
        payload.channel_id = 54321
        payload.message_id = 98765
        payload.emoji = "😀"
        
        # Setup mock guild and member
        mock_member = MagicMock(spec=discord.Member)
        mock_member.bot = False
        mock_member.guild_permissions.manage_messages = False
        mock_guild.get_member.return_value = mock_member
        mock_guild.me.guild_permissions.moderate_members = True
        
        # Setup mock channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.permissions_for.return_value.manage_messages = True
        mock_guild.get_channel.return_value = mock_channel
        
        # Setup mock message
        mock_message = AsyncMock()
        mock_channel.fetch_message.return_value = mock_message
        
        # Setup mock config manager to return config (simulating auto-creation)
        mock_config = GuildConfig(guild_id=12345, timeout_duration=300)
        mock_bot.guild_config_manager.get_guild_config.return_value = mock_config
        
        # Setup blacklist manager
        mock_bot.guild_blacklist_manager.is_blacklisted.return_value = True
        
        # Mock bot methods
        mock_bot.get_guild.return_value = mock_guild
        mock_bot.check_timeout_cooldown.return_value = True
        
        from main import on_raw_reaction_add
        
        with patch('main.bot', mock_bot), \
             patch('main.log_guild_action') as mock_log:
            await on_raw_reaction_add(payload)
        
        # Verify guild config was requested (which triggers auto-creation)
        mock_bot.guild_config_manager.get_guild_config.assert_called_once_with(12345)

    @pytest.mark.asyncio
    async def test_multiple_guild_join_events(self, mock_bot):
        """Test handling multiple guild join events."""
        # Create multiple mock guilds
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 11111
        guild1.name = "Guild 1"
        guild1.member_count = 50
        
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 22222
        guild2.name = "Guild 2"
        guild2.member_count = 150
        
        guild3 = MagicMock(spec=discord.Guild)
        guild3.id = 33333
        guild3.name = "Guild 3"
        guild3.member_count = 75
        
        # Setup mock configs
        config1 = GuildConfig(guild_id=11111)
        config2 = GuildConfig(guild_id=22222)
        config3 = GuildConfig(guild_id=33333)
        
        mock_bot.guild_config_manager.create_default_config.side_effect = [config1, config2, config3]
        
        from main import on_guild_join
        
        with patch('main.bot', mock_bot):
            # Process multiple guild joins
            await on_guild_join(guild1)
            await on_guild_join(guild2)
            await on_guild_join(guild3)
        
        # Verify all guilds had configs created
        expected_calls = [
            ((11111,),),
            ((22222,),),
            ((33333,),)
        ]
        actual_calls = mock_bot.guild_config_manager.create_default_config.call_args_list
        assert len(actual_calls) == 3
        for expected, actual in zip(expected_calls, actual_calls):
            assert actual[0] == expected[0]

    @pytest.mark.asyncio
    async def test_multiple_guild_remove_events(self, mock_bot):
        """Test handling multiple guild remove events."""
        # Setup cache with multiple guilds
        mock_bot.guild_config_manager._config_cache = {
            11111: MagicMock(),
            22222: MagicMock(),
            33333: MagicMock()
        }
        
        # Create multiple mock guilds
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 11111
        guild1.name = "Guild 1"
        
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 22222
        guild2.name = "Guild 2"
        
        guild3 = MagicMock(spec=discord.Guild)
        guild3.id = 33333
        guild3.name = "Guild 3"
        
        from main import on_guild_remove
        
        with patch('main.bot', mock_bot):
            # Process multiple guild removals
            await on_guild_remove(guild1)
            await on_guild_remove(guild2)
            await on_guild_remove(guild3)
        
        # Verify all guilds were removed from cache
        assert 11111 not in mock_bot.guild_config_manager._config_cache
        assert 22222 not in mock_bot.guild_config_manager._config_cache
        assert 33333 not in mock_bot.guild_config_manager._config_cache

    @pytest.mark.asyncio
    async def test_guild_join_with_partial_failure(self, mock_bot):
        """Test guild join when some operations succeed and others fail."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 12345
        guild.name = "Test Guild"
        guild.member_count = 100
        
        # Setup mock to succeed on config creation but fail on something else
        mock_config = GuildConfig(guild_id=12345)
        mock_bot.guild_config_manager.create_default_config.return_value = mock_config
        
        from main import on_guild_join
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            await on_guild_join(guild)
        
        # Verify config creation succeeded
        mock_bot.guild_config_manager.create_default_config.assert_called_once_with(12345)
        
        # Verify success logging
        mock_logger.info.assert_any_call(
            "Bot joined guild 'Test Guild' (ID: 12345). Created default configuration."
        )

    @pytest.mark.asyncio
    async def test_guild_events_with_unicode_guild_names(self, mock_bot):
        """Test guild events with Unicode characters in guild names."""
        # Create guild with Unicode name
        guild = MagicMock(spec=discord.Guild)
        guild.id = 12345
        guild.name = "Test Guild 🎮🎯"
        guild.member_count = 100
        
        mock_config = GuildConfig(guild_id=12345)
        mock_bot.guild_config_manager.create_default_config.return_value = mock_config
        mock_bot.guild_config_manager._config_cache = {12345: mock_config}
        
        from main import on_guild_join, on_guild_remove
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            # Test join
            await on_guild_join(guild)
            
            # Test remove
            await on_guild_remove(guild)
        
        # Verify operations completed without issues
        mock_bot.guild_config_manager.create_default_config.assert_called_once_with(12345)
        assert 12345 not in mock_bot.guild_config_manager._config_cache

    @pytest.mark.asyncio
    async def test_guild_config_auto_creation_in_get_guild_config(self, mock_bot):
        """Test that get_guild_config automatically creates config for new guilds."""
        # This tests the requirement that bot works immediately in new guilds
        guild_id = 12345
        
        # Setup mock to simulate config not existing, then being created
        mock_config = GuildConfig(guild_id=guild_id)
        
        # Create a real GuildConfigManager instance for this test
        from database.guild_config_manager import GuildConfigManager
        from database.manager import DatabaseManager
        
        db_manager = AsyncMock(spec=DatabaseManager)
        config_manager = GuildConfigManager(db_manager)
        
        # Mock database responses
        db_manager.fetch_one.return_value = None  # No existing config
        db_manager.execute_query.return_value = None  # Successful insert
        
        # Test get_guild_config
        result = await config_manager.get_guild_config(guild_id)
        
        # Verify config was created with defaults
        assert result.guild_id == guild_id
        assert result.timeout_duration == 300
        assert result.dm_on_timeout == False
        assert result.log_channel_id is None
        
        # Verify database operations
        db_manager.fetch_one.assert_called_once()
        db_manager.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_bot_resilience_to_guild_event_failures(self, mock_bot):
        """Test that bot continues operating even if guild events fail."""
        guild = MagicMock(spec=discord.Guild)
        guild.id = 12345
        guild.name = "Test Guild"
        guild.member_count = 100
        
        # Setup mock to raise various exceptions
        mock_bot.guild_config_manager.create_default_config.side_effect = [
            Exception("Database connection failed"),
            ConnectionError("Network error"),
            RuntimeError("Unexpected error")
        ]
        
        from main import on_guild_join
        
        with patch('main.bot', mock_bot), \
             patch('main.logger') as mock_logger:
            # All of these should complete without raising exceptions
            await on_guild_join(guild)
            await on_guild_join(guild)
            await on_guild_join(guild)
        
        # Verify all attempts were made
        assert mock_bot.guild_config_manager.create_default_config.call_count == 3
        
        # Verify errors were logged but didn't crash
        assert mock_logger.error.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__])