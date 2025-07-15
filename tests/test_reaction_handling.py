"""
Tests for guild-specific reaction handling functionality.
"""

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from datetime import datetime, timedelta, timezone

# Import the modules we need to test
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.manager import DatabaseManager
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.models import GuildConfig
from main import get_emoji_display, log_guild_action


class TestReactionHandling:
    """Test guild-specific reaction handling functionality."""

    @pytest_asyncio.fixture
    async def db_manager(self):
        """Create a test database manager."""
        db_manager = DatabaseManager(":memory:")
        await db_manager.initialize_database()
        return db_manager

    @pytest_asyncio.fixture
    async def guild_config_manager(self, db_manager):
        """Create a guild config manager with test database."""
        return GuildConfigManager(db_manager)

    @pytest_asyncio.fixture
    async def guild_blacklist_manager(self, db_manager):
        """Create a guild blacklist manager with test database."""
        return GuildBlacklistManager(db_manager)

    @pytest.fixture
    def mock_guild(self):
        """Create a mock Discord guild."""
        guild = MagicMock()
        guild.id = 12345
        guild.name = "Test Guild"
        guild.me = MagicMock()
        guild.me.guild_permissions.moderate_members = True
        return guild

    @pytest.fixture
    def mock_member(self):
        """Create a mock Discord member."""
        member = MagicMock()
        member.id = 67890
        member.name = "TestUser"
        member.mention = "<@67890>"
        member.bot = False
        member.guild_permissions.manage_messages = False
        return member

    @pytest.fixture
    def mock_channel(self):
        """Create a mock Discord channel."""
        channel = MagicMock()
        channel.id = 11111
        channel.name = "test-channel"
        channel.mention = "<#11111>"
        return channel

    @pytest.fixture
    def mock_payload(self):
        """Create a mock reaction payload."""
        payload = MagicMock()
        payload.user_id = 67890
        payload.guild_id = 12345
        payload.channel_id = 11111
        payload.message_id = 22222
        payload.emoji = "😀"
        return payload

    @pytest.mark.asyncio
    async def test_guild_specific_blacklist_checking(self, guild_config_manager, guild_blacklist_manager):
        """Test that blacklist checking is guild-specific."""
        guild1_id = 12345
        guild2_id = 54321
        test_emoji = "😀"

        # Add emoji to guild1's blacklist only
        await guild_blacklist_manager.add_emoji(guild1_id, test_emoji)

        # Check that emoji is blacklisted in guild1 but not guild2
        assert await guild_blacklist_manager.is_blacklisted(guild1_id, test_emoji) == True
        assert await guild_blacklist_manager.is_blacklisted(guild2_id, test_emoji) == False

    @pytest.mark.asyncio
    async def test_guild_specific_timeout_duration(self, guild_config_manager):
        """Test that timeout duration is guild-specific."""
        guild1_id = 12345
        guild2_id = 54321

        # Set different timeout durations for each guild
        await guild_config_manager.update_guild_config(guild1_id, timeout_duration=600)
        await guild_config_manager.update_guild_config(guild2_id, timeout_duration=1200)

        # Get configurations and verify they're different
        config1 = await guild_config_manager.get_guild_config(guild1_id)
        config2 = await guild_config_manager.get_guild_config(guild2_id)

        assert config1.timeout_duration == 600
        assert config2.timeout_duration == 1200

    @pytest.mark.asyncio
    async def test_guild_specific_logging_channel(self, guild_config_manager):
        """Test that logging channel is guild-specific."""
        guild1_id = 12345
        guild2_id = 54321

        # Set different log channels for each guild
        await guild_config_manager.update_guild_config(guild1_id, log_channel_id=11111)
        await guild_config_manager.update_guild_config(guild2_id, log_channel_id=22222)

        # Get configurations and verify they're different
        config1 = await guild_config_manager.get_guild_config(guild1_id)
        config2 = await guild_config_manager.get_guild_config(guild2_id)

        assert config1.log_channel_id == 11111
        assert config2.log_channel_id == 22222

    @pytest.mark.asyncio
    async def test_guild_specific_dm_on_timeout(self, guild_config_manager):
        """Test that DM on timeout setting is guild-specific."""
        guild1_id = 12345
        guild2_id = 54321

        # Set different DM settings for each guild
        await guild_config_manager.update_guild_config(guild1_id, dm_on_timeout=True)
        await guild_config_manager.update_guild_config(guild2_id, dm_on_timeout=False)

        # Get configurations and verify they're different
        config1 = await guild_config_manager.get_guild_config(guild1_id)
        config2 = await guild_config_manager.get_guild_config(guild2_id)

        assert config1.dm_on_timeout == True
        assert config2.dm_on_timeout == False

    @pytest.mark.asyncio
    async def test_multiple_guilds_different_blacklists(self, guild_blacklist_manager):
        """Test that multiple guilds can have completely different blacklists."""
        guild1_id = 12345
        guild2_id = 54321
        
        # Add different emojis to each guild's blacklist
        await guild_blacklist_manager.add_emoji(guild1_id, "😀")
        await guild_blacklist_manager.add_emoji(guild1_id, "😂")
        await guild_blacklist_manager.add_emoji(guild2_id, "🔥")
        await guild_blacklist_manager.add_emoji(guild2_id, "💯")

        # Verify guild1 blacklist
        guild1_blacklist = await guild_blacklist_manager.get_all_blacklisted(guild1_id)
        guild1_emojis = {item['emoji_value'] for item in guild1_blacklist}
        assert guild1_emojis == {"😀", "😂"}

        # Verify guild2 blacklist
        guild2_blacklist = await guild_blacklist_manager.get_all_blacklisted(guild2_id)
        guild2_emojis = {item['emoji_value'] for item in guild2_blacklist}
        assert guild2_emojis == {"🔥", "💯"}

        # Cross-check that emojis are not blacklisted in the wrong guild
        assert await guild_blacklist_manager.is_blacklisted(guild1_id, "🔥") == False
        assert await guild_blacklist_manager.is_blacklisted(guild2_id, "😀") == False

    def test_get_emoji_display_unicode(self):
        """Test emoji display for Unicode emojis."""
        emoji = "😀"
        display = get_emoji_display(emoji)
        assert display == "😀"

    def test_get_emoji_display_custom_emoji(self):
        """Test emoji display for custom emojis."""
        # Mock a custom emoji
        emoji = MagicMock()
        emoji.id = 123456789
        emoji.name = "custom_emoji"
        emoji.animated = False

        display = get_emoji_display(emoji)
        assert display == "<:custom_emoji:123456789>"

    def test_get_emoji_display_animated_emoji(self):
        """Test emoji display for animated custom emojis."""
        # Mock an animated custom emoji
        emoji = MagicMock()
        emoji.id = 123456789
        emoji.name = "animated_emoji"
        emoji.animated = True

        display = get_emoji_display(emoji)
        assert display == "<a:animated_emoji:123456789>"

    def test_get_emoji_display_partial_emoji(self):
        """Test emoji display for partial emojis (Unicode as PartialEmoji)."""
        # Mock a partial emoji (Unicode emoji represented as PartialEmoji)
        emoji = MagicMock()
        emoji.id = None
        emoji.name = "😀"

        display = get_emoji_display(emoji)
        assert display == "😀"

    @pytest.mark.asyncio
    async def test_log_guild_action_with_valid_channel(self, mock_guild):
        """Test logging to a valid guild-specific log channel."""
        # Mock guild config with log channel
        guild_config = MagicMock()
        guild_config.log_channel_id = 11111

        # Mock log channel as a TextChannel
        log_channel = AsyncMock(spec=discord.TextChannel)
        log_channel.send = AsyncMock()
        mock_guild.get_channel.return_value = log_channel

        # Test logging
        test_message = "Test log message"
        await log_guild_action(mock_guild, guild_config, test_message)

        # Verify the message was sent to the correct channel
        mock_guild.get_channel.assert_called_once_with(11111)
        log_channel.send.assert_called_once_with(test_message)

    @pytest.mark.asyncio
    async def test_log_guild_action_no_log_channel(self, mock_guild):
        """Test logging when no log channel is configured."""
        # Mock guild config without log channel
        guild_config = MagicMock()
        guild_config.log_channel_id = None

        # Test logging (should not attempt to send)
        test_message = "Test log message"
        await log_guild_action(mock_guild, guild_config, test_message)

        # Verify no channel lookup was attempted
        mock_guild.get_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_log_guild_action_invalid_channel(self, mock_guild):
        """Test logging when log channel is invalid or inaccessible."""
        # Mock guild config with log channel
        guild_config = MagicMock()
        guild_config.log_channel_id = 11111

        # Mock guild returning None for the channel (channel not found)
        mock_guild.get_channel.return_value = None

        # Test logging (should handle gracefully)
        test_message = "Test log message"
        await log_guild_action(mock_guild, guild_config, test_message)

        # Verify channel lookup was attempted but no error was raised
        mock_guild.get_channel.assert_called_once_with(11111)

    @pytest.mark.asyncio
    async def test_custom_emoji_blacklist_handling(self, guild_blacklist_manager):
        """Test handling of custom emoji blacklists."""
        guild_id = 12345

        # Mock a custom emoji
        custom_emoji = MagicMock()
        custom_emoji.id = 987654321
        custom_emoji.name = "test_custom"

        # Add custom emoji to blacklist
        await guild_blacklist_manager.add_emoji(guild_id, custom_emoji)

        # Verify it's blacklisted
        assert await guild_blacklist_manager.is_blacklisted(guild_id, custom_emoji) == True

        # Verify it appears in the blacklist
        blacklist = await guild_blacklist_manager.get_all_blacklisted(guild_id)
        assert len(blacklist) == 1
        assert blacklist[0]['emoji_type'] == 'custom'
        assert blacklist[0]['emoji_value'] == '987654321'
        assert blacklist[0]['emoji_name'] == 'test_custom'

    @pytest.mark.asyncio
    async def test_default_guild_config_creation(self, guild_config_manager):
        """Test that default configuration is created for new guilds."""
        guild_id = 99999

        # Get config for a new guild (should create default)
        config = await guild_config_manager.get_guild_config(guild_id)

        # Verify default values
        assert config.guild_id == guild_id
        assert config.log_channel_id is None
        assert config.timeout_duration == 300
        assert config.dm_on_timeout == False
        assert config.created_at is not None
        assert config.updated_at is not None

    @pytest.mark.asyncio
    async def test_guild_isolation(self, guild_blacklist_manager, guild_config_manager):
        """Test that guild configurations and blacklists are completely isolated."""
        guild1_id = 11111
        guild2_id = 22222

        # Set up different configurations for each guild
        await guild_config_manager.update_guild_config(guild1_id, timeout_duration=600, dm_on_timeout=True)
        await guild_config_manager.update_guild_config(guild2_id, timeout_duration=1200, dm_on_timeout=False)

        # Add different emojis to each guild's blacklist
        await guild_blacklist_manager.add_emoji(guild1_id, "😀")
        await guild_blacklist_manager.add_emoji(guild2_id, "😂")

        # Verify complete isolation
        config1 = await guild_config_manager.get_guild_config(guild1_id)
        config2 = await guild_config_manager.get_guild_config(guild2_id)

        assert config1.timeout_duration != config2.timeout_duration
        assert config1.dm_on_timeout != config2.dm_on_timeout

        assert await guild_blacklist_manager.is_blacklisted(guild1_id, "😀") == True
        assert await guild_blacklist_manager.is_blacklisted(guild1_id, "😂") == False
        assert await guild_blacklist_manager.is_blacklisted(guild2_id, "😀") == False
        assert await guild_blacklist_manager.is_blacklisted(guild2_id, "😂") == True


if __name__ == "__main__":
    pytest.main([__file__])