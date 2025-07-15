"""
Unit tests for database models.
"""

import pytest
from datetime import datetime
from database.models import GuildConfig, BlacklistedEmoji


class TestGuildConfig:
    """Test cases for GuildConfig dataclass."""
    
    def test_guild_config_creation_with_defaults(self):
        """Test creating GuildConfig with default values."""
        config = GuildConfig(guild_id=123456789)
        
        assert config.guild_id == 123456789
        assert config.log_channel_id is None
        assert config.timeout_duration == 300
        assert config.dm_on_timeout is False
        assert config.created_at is None
        assert config.updated_at is None
    
    def test_guild_config_creation_with_custom_values(self):
        """Test creating GuildConfig with custom values."""
        now = datetime.now()
        config = GuildConfig(
            guild_id=987654321,
            log_channel_id=111222333,
            timeout_duration=600,
            dm_on_timeout=True,
            created_at=now,
            updated_at=now
        )
        
        assert config.guild_id == 987654321
        assert config.log_channel_id == 111222333
        assert config.timeout_duration == 600
        assert config.dm_on_timeout is True
        assert config.created_at == now
        assert config.updated_at == now
    
    def test_guild_config_equality(self):
        """Test GuildConfig equality comparison."""
        config1 = GuildConfig(guild_id=123, timeout_duration=300)
        config2 = GuildConfig(guild_id=123, timeout_duration=300)
        config3 = GuildConfig(guild_id=456, timeout_duration=300)
        
        assert config1 == config2
        assert config1 != config3


class TestBlacklistedEmoji:
    """Test cases for BlacklistedEmoji dataclass."""
    
    def test_blacklisted_emoji_unicode_creation(self):
        """Test creating BlacklistedEmoji for Unicode emoji."""
        emoji = BlacklistedEmoji(
            guild_id=123456789,
            emoji_type="unicode",
            emoji_value="😀"
        )
        
        assert emoji.guild_id == 123456789
        assert emoji.emoji_type == "unicode"
        assert emoji.emoji_value == "😀"
        assert emoji.emoji_name is None
        assert emoji.created_at is None
    
    def test_blacklisted_emoji_custom_creation(self):
        """Test creating BlacklistedEmoji for custom emoji."""
        now = datetime.now()
        emoji = BlacklistedEmoji(
            guild_id=987654321,
            emoji_type="custom",
            emoji_value="123456789012345678",
            emoji_name="custom_emoji",
            created_at=now
        )
        
        assert emoji.guild_id == 987654321
        assert emoji.emoji_type == "custom"
        assert emoji.emoji_value == "123456789012345678"
        assert emoji.emoji_name == "custom_emoji"
        assert emoji.created_at == now
    
    def test_blacklisted_emoji_equality(self):
        """Test BlacklistedEmoji equality comparison."""
        emoji1 = BlacklistedEmoji(guild_id=123, emoji_type="unicode", emoji_value="😀")
        emoji2 = BlacklistedEmoji(guild_id=123, emoji_type="unicode", emoji_value="😀")
        emoji3 = BlacklistedEmoji(guild_id=123, emoji_type="unicode", emoji_value="😂")
        
        assert emoji1 == emoji2
        assert emoji1 != emoji3
    
    def test_blacklisted_emoji_type_validation(self):
        """Test that emoji_type accepts expected values."""
        # Test valid types
        unicode_emoji = BlacklistedEmoji(guild_id=123, emoji_type="unicode", emoji_value="😀")
        custom_emoji = BlacklistedEmoji(guild_id=123, emoji_type="custom", emoji_value="123")
        
        assert unicode_emoji.emoji_type == "unicode"
        assert custom_emoji.emoji_type == "custom"