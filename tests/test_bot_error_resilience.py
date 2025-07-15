"""
Tests for bot error resilience and graceful degradation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from database.manager import DatabaseError


class TestBotErrorResilience:
    """Test bot's resilience to various error conditions."""
    
    @pytest.mark.asyncio
    async def test_bot_startup_with_database_error(self):
        """Test that bot can start even if database initialization fails."""
        with patch('database.manager.DatabaseManager.initialize_database') as mock_init:
            mock_init.side_effect = DatabaseError("Database initialization failed")
            
            # Bot should still be able to start (though with limited functionality)
            from main import Reacter
            bot = Reacter()
            
            # Verify bot was created successfully
            assert bot is not None
            assert hasattr(bot, 'db_manager')
            assert hasattr(bot, 'guild_config_manager')
            assert hasattr(bot, 'guild_blacklist_manager')
    
    @pytest.mark.asyncio
    async def test_guild_join_with_database_error(self):
        """Test that guild join events handle database errors gracefully."""
        from main import Reacter
        bot = Reacter()
        
        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.member_count = 100
        
        # Mock database error during config creation
        with patch.object(bot.guild_config_manager, 'create_default_config') as mock_create:
            mock_create.side_effect = DatabaseError("Database error")
            
            # Should not raise an exception
            await bot.on_guild_join(mock_guild)
    
    @pytest.mark.asyncio
    async def test_reaction_handling_with_multiple_errors(self):
        """Test reaction handling when multiple components fail."""
        from main import Reacter
        bot = Reacter()
        
        # Mock payload
        mock_payload = MagicMock()
        mock_payload.guild_id = 123
        mock_payload.user_id = 456
        mock_payload.emoji = "😀"
        
        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        bot.get_guild = MagicMock(return_value=mock_guild)
        
        # Mock both config and blacklist managers to fail
        with patch.object(bot.guild_config_manager, 'get_guild_config') as mock_config:
            with patch.object(bot.guild_blacklist_manager, 'is_blacklisted') as mock_blacklist:
                mock_config.side_effect = DatabaseError("Config error")
                mock_blacklist.side_effect = DatabaseError("Blacklist error")
                
                # Should not raise an exception
                await bot.on_raw_reaction_add(mock_payload)
    
    @pytest.mark.asyncio
    async def test_command_resilience_to_database_errors(self):
        """Test that commands remain functional despite database errors."""
        from main import blacklist_command, add_blacklist, remove_blacklist
        
        # Mock context
        mock_ctx = MagicMock()
        mock_ctx.guild.id = 123
        mock_ctx.guild.name = "Test Guild"
        mock_ctx.send = AsyncMock()
        
        # Mock bot with failing database operations
        with patch('main.bot') as mock_bot:
            mock_bot.guild_blacklist_manager.get_blacklist_display = AsyncMock(
                side_effect=DatabaseError("Database error")
            )
            mock_bot.guild_blacklist_manager.add_emoji = AsyncMock(
                side_effect=DatabaseError("Database error")
            )
            mock_bot.guild_blacklist_manager.remove_emoji = AsyncMock(
                side_effect=DatabaseError("Database error")
            )
            
            # All commands should handle errors gracefully
            await blacklist_command(mock_ctx)
            await add_blacklist(mock_ctx, "😀")
            await remove_blacklist(mock_ctx, "😀")
            
            # Verify error messages were sent
            assert mock_ctx.send.call_count >= 3
    
    @pytest.mark.asyncio
    async def test_logging_channel_error_recovery(self):
        """Test that logging errors don't affect bot functionality."""
        from main import log_guild_action
        from database.models import GuildConfig
        
        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 123
        mock_guild.name = "Test Guild"
        mock_guild.get_channel.return_value = None
        mock_guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Not found"))
        
        # Mock guild config with log channel
        guild_config = GuildConfig(guild_id=123, log_channel_id=456)
        
        # Mock bot's config manager
        with patch('main.bot') as mock_bot:
            mock_bot.guild_config_manager.update_guild_config = AsyncMock()
            
            # Should not raise an exception
            await log_guild_action(mock_guild, guild_config, "Test message")
            
            # Should attempt to clear invalid log channel
            mock_bot.guild_config_manager.update_guild_config.assert_called_once_with(
                123, log_channel_id=None
            )
    
    @pytest.mark.asyncio
    async def test_cache_consistency_during_errors(self):
        """Test that cache remains consistent during database errors."""
        from database.guild_config_manager import GuildConfigManager
        from database.manager import DatabaseManager
        
        # Create real managers
        db_manager = DatabaseManager(":memory:")
        config_manager = GuildConfigManager(db_manager)
        
        # Initialize database
        await db_manager.initialize_database()
        
        # Create initial config
        config = await config_manager.create_default_config(123)
        assert config.timeout_duration == 300
        
        # Mock database to fail on updates
        with patch.object(db_manager, 'execute_query') as mock_execute:
            mock_execute.side_effect = DatabaseError("Database error")
            
            # Update should fail but cache should be updated
            with pytest.raises(DatabaseError):
                await config_manager.update_guild_config(123, timeout_duration=600)
            
            # Cache should reflect the update
            cached_config = config_manager.get_cached_config(123)
            assert cached_config.timeout_duration == 600
            
            # Subsequent gets should use cache
            with patch.object(db_manager, 'fetch_one') as mock_fetch:
                mock_fetch.side_effect = DatabaseError("Database error")
                
                config = await config_manager.get_guild_config(123)
                assert config.timeout_duration == 600  # From cache


class TestErrorRecoveryScenarios:
    """Test specific error recovery scenarios."""
    
    @pytest.mark.asyncio
    async def test_partial_database_failure_recovery(self):
        """Test recovery when only some database operations fail."""
        from database.guild_blacklist_manager import GuildBlacklistManager
        from database.manager import DatabaseManager
        
        db_manager = DatabaseManager(":memory:")
        blacklist_manager = GuildBlacklistManager(db_manager)
        
        await db_manager.initialize_database()
        
        # Add some emojis successfully
        await blacklist_manager.add_emoji(123, "😀")
        await blacklist_manager.add_emoji(123, "😂")
        
        # Verify they were added
        result = await blacklist_manager.get_all_blacklisted(123)
        assert len(result) == 2
        
        # Now simulate database failure for new operations
        with patch.object(db_manager, 'execute_query') as mock_execute:
            mock_execute.side_effect = DatabaseError("Database error")
            
            # Adding new emoji should still work (cache-only)
            success = await blacklist_manager.add_emoji(123, "🎉")
            assert success is True
            
            # Cache should be updated
            assert "🎉" in blacklist_manager._cache[123]["unicode"]
        
        # When database recovers, we should still have the cached data
        with patch.object(db_manager, 'fetch_all') as mock_fetch:
            mock_fetch.side_effect = DatabaseError("Database error")
            
            # Should return cached data
            result = await blacklist_manager.get_all_blacklisted(123)
            assert len(result) == 3  # Original 2 + 1 cached
    
    @pytest.mark.asyncio
    async def test_graceful_degradation_with_no_cache(self):
        """Test graceful degradation when no cache is available."""
        from database.guild_config_manager import GuildConfigManager
        from database.manager import DatabaseManager
        
        db_manager = DatabaseManager(":memory:")
        config_manager = GuildConfigManager(db_manager)
        
        # Simulate complete database failure
        with patch.object(db_manager, 'fetch_one') as mock_fetch:
            mock_fetch.side_effect = DatabaseError("Database error")
            
            # Should return default config
            config = await config_manager.get_guild_config(123)
            assert config.guild_id == 123
            assert config.timeout_duration == 300  # Default
            assert config.log_channel_id is None
            
            # Should be cached for future use
            cached_config = config_manager.get_cached_config(123)
            assert cached_config is not None
            assert cached_config.timeout_duration == 300


if __name__ == "__main__":
    pytest.main([__file__])