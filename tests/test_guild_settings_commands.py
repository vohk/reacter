"""
Tests for guild settings management commands.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from discord.ext import commands
from datetime import datetime, timezone

# Import the bot and related components
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import Reacter, parse_duration
from database.models import GuildConfig


class TestGuildSettingsCommands:
    """Test guild settings management commands."""
    
    @pytest.fixture
    def mock_ctx(self):
        """Create a mock command context."""
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = 12345
        ctx.guild.name = "Test Guild"
        ctx.author = MagicMock()
        ctx.author.name = "TestUser"
        ctx.send = AsyncMock()
        return ctx
    
    @pytest.fixture
    def sample_guild_config(self):
        """Create a sample guild configuration."""
        return GuildConfig(
            guild_id=12345,
            log_channel_id=67890,
            timeout_duration=600,
            dm_on_timeout=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
    
    @pytest.mark.asyncio
    async def test_show_guild_settings_with_custom_values(self, mock_ctx, sample_guild_config):
        """Test showing guild settings with custom values."""
        # Mock the log channel
        mock_channel = MagicMock()
        mock_channel.mention = "#test-log"
        mock_ctx.guild.get_channel.return_value = mock_channel
        
        # Mock the bot's guild config manager
        with patch('main.bot') as mock_bot:
            mock_bot.guild_config_manager.get_guild_config.return_value = sample_guild_config
            
            # Get the command callback function directly
            from main import show_guild_settings
            await show_guild_settings.callback(mock_ctx)
            
            # Verify the guild config was fetched
            mock_bot.guild_config_manager.get_guild_config.assert_called_once_with(12345)
        
        # Verify a response was sent
        mock_ctx.send.assert_called_once()
        
        # Check that the embed contains expected information
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        
        assert "Guild Settings - Test Guild" in embed.title
        # Check that custom indicators are present
        embed_dict = embed.to_dict()
        fields_text = ' '.join([field['value'] for field in embed_dict['fields']])
        assert "*(custom)*" in fields_text
    
    @pytest.mark.asyncio
    async def test_show_guild_settings_with_default_values(self, mock_ctx):
        """Test showing guild settings with default values."""
        # Create a default config
        default_config = GuildConfig(
            guild_id=12345,
            log_channel_id=None,
            timeout_duration=300,
            dm_on_timeout=False
        )
        
        mock_ctx.bot.guild_config_manager.get_guild_config.return_value = default_config
        
        from main import show_guild_settings
        await show_guild_settings.callback(mock_ctx)
        
        # Verify response was sent
        mock_ctx.send.assert_called_once()
        
        # Check that default indicators are present
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        embed_dict = embed.to_dict()
        fields_text = ' '.join([field['value'] for field in embed_dict['fields']])
        assert "*(default)*" in fields_text
    
    @pytest.mark.asyncio
    async def test_show_guild_settings_error_handling(self, mock_ctx):
        """Test error handling in show guild settings."""
        # Make the guild config manager raise an exception
        mock_ctx.bot.guild_config_manager.get_guild_config.side_effect = Exception("Database error")
        
        from main import show_guild_settings
        await show_guild_settings.callback(mock_ctx)
        
        # Verify error message was sent
        mock_ctx.send.assert_called_once_with("❌ Failed to retrieve guild settings. Please try again.")
    
    @pytest.mark.asyncio
    async def test_set_timeout_duration_valid_input(self, mock_ctx):
        """Test setting timeout duration with valid input."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        from main import set_timeout_duration
        await set_timeout_duration.callback(mock_ctx, "5m")
        
        # Verify the config was updated with correct value (5 minutes = 300 seconds)
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            timeout_duration=300
        )
        
        # Verify success message was sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        assert "Timeout Duration Updated" in embed.title
    
    @pytest.mark.asyncio
    async def test_set_timeout_duration_invalid_input(self, mock_ctx):
        """Test setting timeout duration with invalid input."""
        from main import set_timeout_duration
        await set_timeout_duration.callback(mock_ctx, "invalid")
        
        # Verify error message was sent
        mock_ctx.send.assert_called_once()
        args = mock_ctx.send.call_args[0]
        assert "❌ Invalid duration format" in args[0]
    
    @pytest.mark.asyncio
    async def test_set_timeout_duration_negative_value(self, mock_ctx):
        """Test setting negative timeout duration."""
        from main import set_timeout_duration
        
        # Mock parse_duration to return negative value
        with patch('main.parse_duration', return_value=-300):
            await set_timeout_duration.callback(mock_ctx, "-5m")
        
        # Verify error message was sent
        mock_ctx.send.assert_called_once_with("❌ Timeout duration cannot be negative.")
    
    @pytest.mark.asyncio
    async def test_set_timeout_duration_too_large(self, mock_ctx):
        """Test setting timeout duration that exceeds maximum."""
        from main import set_timeout_duration
        
        # Mock parse_duration to return large value
        with patch('main.parse_duration', return_value=2592000):  # 30 days
            await set_timeout_duration.callback(mock_ctx, "30d")
        
        # Verify error message was sent
        mock_ctx.send.assert_called_once_with("❌ Timeout duration cannot exceed 28 days (2,419,200 seconds).")
    
    @pytest.mark.asyncio
    async def test_set_log_channel_valid_channel(self, mock_ctx):
        """Test setting log channel with valid channel."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        # Mock a text channel
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 98765
        mock_channel.mention = "#new-log"
        
        from main import set_log_channel
        await set_log_channel.callback(mock_ctx, mock_channel)
        
        # Verify the config was updated
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            log_channel_id=98765
        )
        
        # Verify success message was sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        assert "Log Channel Updated" in embed.title
    
    @pytest.mark.asyncio
    async def test_set_log_channel_disable_logging(self, mock_ctx):
        """Test disabling log channel."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        from main import set_log_channel
        await set_log_channel.callback(mock_ctx, None)
        
        # Verify the config was updated to disable logging
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            log_channel_id=None
        )
        
        # Verify success message was sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        assert "Log Channel Disabled" in embed.title
    
    @pytest.mark.asyncio
    async def test_set_dm_timeout_enable(self, mock_ctx):
        """Test enabling DM timeout notifications."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        from main import set_dm_timeout
        await set_dm_timeout.callback(mock_ctx, "true")
        
        # Verify the config was updated
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            dm_on_timeout=True
        )
        
        # Verify success message was sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        assert "DM Timeout Setting Updated" in embed.title
        assert "Enabled" in embed.description
    
    @pytest.mark.asyncio
    async def test_set_dm_timeout_disable(self, mock_ctx):
        """Test disabling DM timeout notifications."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        from main import set_dm_timeout
        await set_dm_timeout.callback(mock_ctx, "false")
        
        # Verify the config was updated
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            dm_on_timeout=False
        )
        
        # Verify success message was sent
        mock_ctx.send.assert_called_once()
        call_args = mock_ctx.send.call_args
        if call_args[1]:  # kwargs
            embed = call_args[1]['embed']
        else:  # args
            embed = call_args[0][0]
        assert "Disabled" in embed.description
    
    @pytest.mark.asyncio
    async def test_set_dm_timeout_invalid_value(self, mock_ctx):
        """Test setting DM timeout with invalid value."""
        from main import set_dm_timeout
        await set_dm_timeout.callback(mock_ctx, "maybe")
        
        # Verify error message was sent
        mock_ctx.send.assert_called_once_with("❌ Invalid value. Use: true/false, yes/no, on/off, or enable/disable")
    
    @pytest.mark.asyncio
    async def test_reset_guild_settings_confirmed(self, mock_ctx):
        """Test resetting guild settings with confirmation."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        # Mock the wait_for to return a confirmation message
        mock_response = MagicMock()
        mock_response.content = "yes"
        mock_ctx.bot.wait_for = AsyncMock(return_value=mock_response)
        
        from main import reset_guild_settings
        await reset_guild_settings.callback(mock_ctx)
        
        # Verify the config was reset to defaults
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_called_once_with(
            12345,
            log_channel_id=None,
            timeout_duration=300,
            dm_on_timeout=False
        )
        
        # Verify confirmation and success messages were sent
        assert mock_ctx.send.call_count == 2  # Initial prompt + success message
    
    @pytest.mark.asyncio
    async def test_reset_guild_settings_cancelled(self, mock_ctx):
        """Test resetting guild settings when cancelled."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        # Mock the wait_for to return a cancellation message
        mock_response = MagicMock()
        mock_response.content = "no"
        mock_ctx.bot.wait_for = AsyncMock(return_value=mock_response)
        
        from main import reset_guild_settings
        await reset_guild_settings.callback(mock_ctx)
        
        # Verify the config was NOT updated
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_not_called()
        
        # Verify cancellation message was sent
        assert mock_ctx.send.call_count == 2  # Initial prompt + cancellation message
    
    @pytest.mark.asyncio
    async def test_reset_guild_settings_timeout(self, mock_ctx):
        """Test resetting guild settings when user doesn't respond."""
        mock_ctx.bot.guild_config_manager.update_guild_config = AsyncMock()
        
        # Mock the wait_for to timeout
        mock_ctx.bot.wait_for = AsyncMock(side_effect=asyncio.TimeoutError())
        
        from main import reset_guild_settings
        await reset_guild_settings.callback(mock_ctx)
        
        # Verify the config was NOT updated
        mock_ctx.bot.guild_config_manager.update_guild_config.assert_not_called()
        
        # Verify timeout message was sent
        assert mock_ctx.send.call_count == 2  # Initial prompt + timeout message


class TestParseDuration:
    """Test the parse_duration utility function."""
    
    def test_parse_seconds(self):
        """Test parsing seconds."""
        assert parse_duration("300") == 300
        assert parse_duration("30s") == 30
    
    def test_parse_minutes(self):
        """Test parsing minutes."""
        assert parse_duration("5m") == 300
        assert parse_duration("10m") == 600
    
    def test_parse_hours(self):
        """Test parsing hours."""
        assert parse_duration("1h") == 3600
        assert parse_duration("2h") == 7200
    
    def test_parse_days(self):
        """Test parsing days."""
        assert parse_duration("1d") == 86400
        assert parse_duration("2d") == 172800
    
    def test_parse_complex_duration(self):
        """Test parsing complex duration strings."""
        assert parse_duration("1h30m") == 5400  # 1 hour + 30 minutes
        assert parse_duration("2h15m30s") == 8130  # 2 hours + 15 minutes + 30 seconds
        assert parse_duration("1d2h") == 93600  # 1 day + 2 hours
    
    def test_parse_invalid_format(self):
        """Test parsing invalid duration formats."""
        with pytest.raises(ValueError):
            parse_duration("invalid")
        
        with pytest.raises(ValueError):
            parse_duration("5x")  # Invalid unit
        
        with pytest.raises(ValueError):
            parse_duration("")
    
    def test_parse_zero_duration(self):
        """Test parsing zero duration."""
        assert parse_duration("0") == 0
        assert parse_duration("0s") == 0
        assert parse_duration("0m") == 0


class TestCommandPermissions:
    """Test command permission requirements."""
    
    @pytest.fixture
    def mock_ctx_no_perms(self):
        """Create a mock context without administrator permissions."""
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.author.guild_permissions = MagicMock()
        ctx.author.guild_permissions.administrator = False
        return ctx
    
    def test_settings_command_requires_admin(self):
        """Test that settings commands require administrator permission."""
        from main import show_guild_settings
        
        # Check that the command has the correct permission decorator
        assert hasattr(show_guild_settings, '__commands_checks__')
        # The actual permission check is handled by discord.py's decorator system
    
    def test_all_settings_commands_have_admin_permission(self):
        """Test that all settings management commands require administrator permission."""
        from main import (show_guild_settings, set_timeout_duration, 
                         set_log_channel, set_dm_timeout, reset_guild_settings)
        
        commands_to_check = [
            show_guild_settings,
            set_timeout_duration,
            set_log_channel,
            set_dm_timeout,
            reset_guild_settings
        ]
        
        for command in commands_to_check:
            assert hasattr(command, '__commands_checks__'), f"{command.__name__} missing permission check"


if __name__ == "__main__":
    pytest.main([__file__])