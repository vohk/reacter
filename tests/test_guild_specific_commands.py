"""
Tests for guild-specific command functionality.
Ensures commands only affect the current guild's settings.
"""

import pytest
import discord
from discord.ext import commands
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
from datetime import datetime

# Import the bot and managers
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.guild_blacklist_manager import GuildBlacklistManager
from database.guild_config_manager import GuildConfigManager
from database.models import GuildConfig, BlacklistedEmoji


class TestGuildSpecificCommands:
    """Test suite for guild-specific command functionality."""
    
    @pytest.fixture
    def mock_bot(self):
        """Create a mock bot instance."""
        bot = MagicMock()
        bot.guild_blacklist_manager = AsyncMock(spec=GuildBlacklistManager)
        bot.guild_config_manager = AsyncMock(spec=GuildConfigManager)
        return bot
    
    @pytest.fixture
    def mock_ctx(self):
        """Create a mock command context."""
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock(spec=discord.Guild)
        ctx.guild.id = 12345
        ctx.guild.name = "Test Guild"
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.name = "TestUser"
        ctx.send = AsyncMock()
        return ctx
    
    @pytest.fixture
    def mock_guild_config(self):
        """Create a mock guild configuration."""
        return GuildConfig(
            guild_id=12345,
            log_channel_id=67890,
            timeout_duration=300,
            dm_on_timeout=False,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )

    @pytest.mark.asyncio
    async def test_blacklist_command_guild_specific(self, mock_bot, mock_ctx):
        """Test that blacklist command shows only current guild's emojis."""
        # Setup mock data
        mock_bot.guild_blacklist_manager.get_blacklist_display.return_value = ["😀", "<:test:123>"]
        
        # Import and test the command function
        from main import blacklist_command
        
        # Mock the bot instance in the command
        with patch('main.bot', mock_bot):
            await blacklist_command(mock_ctx)
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.get_blacklist_display.assert_called_once_with(12345)
        
        # Verify response includes guild name
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        # Check if it's called with embed or string
        if call_args[1] and 'embed' in call_args[1]:
            embed = call_args[1]['embed']
            assert "Test Guild" in embed.title
        elif call_args[0]:
            # Called with positional argument (embed)
            embed = call_args[0][0]
            assert "Test Guild" in embed.title

    @pytest.mark.asyncio
    async def test_blacklist_command_empty_guild(self, mock_bot, mock_ctx):
        """Test blacklist command with no emojis in guild."""
        # Setup empty blacklist
        mock_bot.guild_blacklist_manager.get_blacklist_display.return_value = []
        
        from main import blacklist_command
        
        with patch('main.bot', mock_bot):
            await blacklist_command(mock_ctx)
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.get_blacklist_display.assert_called_once_with(12345)
        
        # Verify appropriate message for empty blacklist
        mock_ctx.send.assert_called_once_with("No emojis are currently blacklisted in this server.")

    @pytest.mark.asyncio
    async def test_add_blacklist_guild_specific(self, mock_bot, mock_ctx):
        """Test that add_blacklist only affects current guild."""
        # Setup mock
        mock_bot.guild_blacklist_manager.add_emoji.return_value = True
        
        from main import add_blacklist
        
        with patch('main.bot', mock_bot):
            await add_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.add_emoji.assert_called_once_with(12345, "😀")
        
        # Verify success message mentions server
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "this server's blacklist" in call_args

    @pytest.mark.asyncio
    async def test_add_blacklist_already_exists(self, mock_bot, mock_ctx):
        """Test add_blacklist when emoji already exists in guild."""
        # Setup mock to return False (already exists)
        mock_bot.guild_blacklist_manager.add_emoji.return_value = False
        
        from main import add_blacklist
        
        with patch('main.bot', mock_bot):
            await add_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.add_emoji.assert_called_once_with(12345, "😀")
        
        # Verify appropriate message
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "already blacklisted in this server" in call_args

    @pytest.mark.asyncio
    async def test_add_blacklist_custom_emoji(self, mock_bot, mock_ctx):
        """Test adding custom emoji to guild blacklist."""
        # Setup mock
        mock_bot.guild_blacklist_manager.add_emoji.return_value = True
        mock_bot.get_emoji.return_value = None  # Emoji not found in bot's cache
        
        from main import add_blacklist
        
        with patch('main.bot', mock_bot):
            await add_blacklist(mock_ctx, emoji_input="<:test:123456>")
        
        # Verify guild-specific call with PartialEmoji
        mock_bot.guild_blacklist_manager.add_emoji.assert_called_once()
        call_args = mock_bot.guild_blacklist_manager.add_emoji.call_args
        assert call_args[0][0] == 12345  # guild_id
        assert hasattr(call_args[0][1], 'id')  # PartialEmoji object
        assert call_args[0][1].id == 123456

    @pytest.mark.asyncio
    async def test_remove_blacklist_guild_specific(self, mock_bot, mock_ctx):
        """Test that remove_blacklist only affects current guild."""
        # Setup mock
        mock_bot.guild_blacklist_manager.remove_emoji.return_value = True
        
        from main import remove_blacklist
        
        with patch('main.bot', mock_bot):
            await remove_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.remove_emoji.assert_called_once_with(12345, "😀")
        
        # Verify success message mentions server
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "this server's blacklist" in call_args

    @pytest.mark.asyncio
    async def test_remove_blacklist_not_found(self, mock_bot, mock_ctx):
        """Test remove_blacklist when emoji not in guild blacklist."""
        # Setup mock to return False (not found)
        mock_bot.guild_blacklist_manager.remove_emoji.return_value = False
        
        from main import remove_blacklist
        
        with patch('main.bot', mock_bot):
            await remove_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.remove_emoji.assert_called_once_with(12345, "😀")
        
        # Verify appropriate message
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "not blacklisted in this server" in call_args

    @pytest.mark.asyncio
    async def test_remove_blacklist_custom_emoji(self, mock_bot, mock_ctx):
        """Test removing custom emoji from guild blacklist."""
        # Setup mock data
        mock_bot.guild_blacklist_manager.get_all_blacklisted.return_value = [
            {
                'emoji_type': 'custom',
                'emoji_value': '123456',
                'emoji_name': 'test_emoji',
                'created_at': datetime.now().isoformat()
            }
        ]
        mock_bot.guild_blacklist_manager.remove_emoji.return_value = True
        
        from main import remove_blacklist
        
        with patch('main.bot', mock_bot):
            await remove_blacklist(mock_ctx, emoji_input="123456")
        
        # Verify guild-specific calls
        mock_bot.guild_blacklist_manager.get_all_blacklisted.assert_called_once_with(12345)
        mock_bot.guild_blacklist_manager.remove_emoji.assert_called_once_with(12345, 123456)
        
        # Verify success message includes emoji name
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "test_emoji" in call_args

    @pytest.mark.asyncio
    async def test_clear_blacklist_guild_specific(self, mock_bot, mock_ctx):
        """Test that clear_blacklist only affects current guild."""
        # Setup mock for confirmation
        mock_bot.wait_for = AsyncMock()
        mock_bot.guild_blacklist_manager.clear_blacklist = AsyncMock()
        
        from main import clear_blacklist
        
        with patch('main.bot', mock_bot):
            await clear_blacklist(mock_ctx)
        
        # Verify guild-specific call
        mock_bot.guild_blacklist_manager.clear_blacklist.assert_called_once_with(12345)
        
        # Verify confirmation message mentions server
        mock_ctx.send.assert_called()
        first_call = mock_ctx.send.call_args_list[0][0][0]
        assert "this server" in first_call

    @pytest.mark.asyncio
    async def test_clear_blacklist_timeout(self, mock_bot, mock_ctx):
        """Test clear_blacklist timeout scenario."""
        # Setup mock to raise timeout
        mock_bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())
        
        from main import clear_blacklist
        
        with patch('main.bot', mock_bot):
            await clear_blacklist(mock_ctx)
        
        # Verify clear_blacklist was not called due to timeout
        mock_bot.guild_blacklist_manager.clear_blacklist.assert_not_called()
        
        # Verify timeout message
        mock_ctx.send.assert_called()
        last_call = mock_ctx.send.call_args_list[-1][0][0]
        assert "cancelled (timeout)" in last_call

    @pytest.mark.asyncio
    async def test_timeout_info_guild_specific(self, mock_bot, mock_ctx, mock_guild_config):
        """Test that timeout_info shows guild-specific configuration."""
        # Setup mock
        mock_bot.guild_config_manager.get_guild_config.return_value = mock_guild_config
        mock_bot.guild_blacklist_manager.get_all_blacklisted.return_value = [
            {'emoji_type': 'unicode', 'emoji_value': '😀'},
            {'emoji_type': 'custom', 'emoji_value': '123456'}
        ]
        
        # Mock guild channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.mention = "#test-log"
        mock_ctx.guild.get_channel.return_value = mock_channel
        
        from main import timeout_info
        
        with patch('main.bot', mock_bot):
            await timeout_info(mock_ctx)
        
        # Verify guild-specific calls
        mock_bot.guild_config_manager.get_guild_config.assert_called_once_with(12345)
        mock_bot.guild_blacklist_manager.get_all_blacklisted.assert_called_once_with(12345)
        
        # Verify response includes guild name
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        # Check if it's called with embed or string
        if call_args[1] and 'embed' in call_args[1]:
            embed = call_args[1]['embed']
            assert "Test Guild" in embed.title
        elif call_args[0]:
            # Called with positional argument (embed)
            embed = call_args[0][0]
            assert "Test Guild" in embed.title

    @pytest.mark.asyncio
    async def test_timeout_info_no_log_channel(self, mock_bot, mock_ctx, mock_guild_config):
        """Test timeout_info when no log channel is configured."""
        # Setup mock with no log channel
        mock_guild_config.log_channel_id = None
        mock_bot.guild_config_manager.get_guild_config.return_value = mock_guild_config
        mock_bot.guild_blacklist_manager.get_all_blacklisted.return_value = []
        
        from main import timeout_info
        
        with patch('main.bot', mock_bot):
            await timeout_info(mock_ctx)
        
        # Verify guild-specific call
        mock_bot.guild_config_manager.get_guild_config.assert_called_once_with(12345)
        
        # Verify response shows "Not set" for log channel
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        # Check if it's called with embed or string
        if call_args[1] and 'embed' in call_args[1]:
            embed = call_args[1]['embed']
            field_values = [field.value for field in embed.fields]
        elif call_args[0]:
            # Called with positional argument (embed)
            embed = call_args[0][0]
            field_values = [field.value for field in embed.fields]
        
        assert any("Not set" in value for value in field_values)

    @pytest.mark.asyncio
    async def test_commands_isolation_between_guilds(self, mock_bot):
        """Test that commands for different guilds don't interfere with each other."""
        # Create two different guild contexts
        ctx1 = MagicMock(spec=commands.Context)
        ctx1.guild = MagicMock(spec=discord.Guild)
        ctx1.guild.id = 11111
        ctx1.guild.name = "Guild 1"
        ctx1.send = AsyncMock()
        
        ctx2 = MagicMock(spec=commands.Context)
        ctx2.guild = MagicMock(spec=discord.Guild)
        ctx2.guild.id = 22222
        ctx2.guild.name = "Guild 2"
        ctx2.send = AsyncMock()
        
        # Setup different responses for each guild
        def mock_get_blacklist_display(guild_id):
            if guild_id == 11111:
                return ["😀", "😂"]
            elif guild_id == 22222:
                return ["🎉"]
            return []
        
        mock_bot.guild_blacklist_manager.get_blacklist_display.side_effect = mock_get_blacklist_display
        
        from main import blacklist_command
        
        with patch('main.bot', mock_bot):
            # Test both guilds
            await blacklist_command(ctx1)
            await blacklist_command(ctx2)
        
        # Verify each guild got its own data
        assert mock_bot.guild_blacklist_manager.get_blacklist_display.call_count == 2
        calls = mock_bot.guild_blacklist_manager.get_blacklist_display.call_args_list
        assert calls[0][0][0] == 11111  # First call with guild 1 ID
        assert calls[1][0][0] == 22222  # Second call with guild 2 ID
        
        # Verify both contexts received responses
        ctx1.send.assert_called_once()
        ctx2.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_in_commands(self, mock_bot, mock_ctx):
        """Test error handling in guild-specific commands."""
        # Setup mock to raise exception
        mock_bot.guild_blacklist_manager.get_blacklist_display.side_effect = Exception("Database error")
        
        from main import blacklist_command
        
        with patch('main.bot', mock_bot):
            await blacklist_command(mock_ctx)
        
        # Verify error message is sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "Failed to retrieve blacklist" in call_args

    @pytest.mark.asyncio
    async def test_add_blacklist_error_handling(self, mock_bot, mock_ctx):
        """Test error handling in add_blacklist command."""
        # Setup mock to raise exception
        mock_bot.guild_blacklist_manager.add_emoji.side_effect = Exception("Database error")
        
        from main import add_blacklist
        
        with patch('main.bot', mock_bot):
            await add_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify error message is sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "Failed to add emoji to blacklist" in call_args

    @pytest.mark.asyncio
    async def test_remove_blacklist_error_handling(self, mock_bot, mock_ctx):
        """Test error handling in remove_blacklist command."""
        # Setup mock to raise exception
        mock_bot.guild_blacklist_manager.remove_emoji.side_effect = Exception("Database error")
        
        from main import remove_blacklist
        
        with patch('main.bot', mock_bot):
            await remove_blacklist(mock_ctx, emoji_input="😀")
        
        # Verify error message is sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "Failed to remove emoji from blacklist" in call_args

    @pytest.mark.asyncio
    async def test_clear_blacklist_error_handling(self, mock_bot, mock_ctx):
        """Test error handling in clear_blacklist command."""
        # Setup mock for confirmation but error on clear
        mock_bot.wait_for = AsyncMock()
        mock_bot.guild_blacklist_manager.clear_blacklist.side_effect = Exception("Database error")
        
        from main import clear_blacklist
        
        with patch('main.bot', mock_bot):
            await clear_blacklist(mock_ctx)
        
        # Verify error message is sent
        mock_ctx.send.assert_called()
        last_call = mock_ctx.send.call_args_list[-1][0][0]
        assert "Failed to clear blacklist" in last_call

    @pytest.mark.asyncio
    async def test_timeout_info_error_handling(self, mock_bot, mock_ctx):
        """Test error handling in timeout_info command."""
        # Setup mock to raise exception
        mock_bot.guild_config_manager.get_guild_config.side_effect = Exception("Database error")
        
        from main import timeout_info
        
        with patch('main.bot', mock_bot):
            await timeout_info(mock_ctx)
        
        # Verify error message is sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args[0][0]
        assert "Failed to retrieve timeout configuration" in call_args


if __name__ == "__main__":
    pytest.main([__file__])