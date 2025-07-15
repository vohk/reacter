"""
Unit tests for EmojiBlacklistCompat.
"""

import pytest
import pytest_asyncio
import tempfile
import os
from unittest.mock import Mock
import discord

from database.manager import DatabaseManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.emoji_blacklist_compat import EmojiBlacklistCompat, GlobalEmojiBlacklistManager


class TestEmojiBlacklistCompat:
    """Test cases for EmojiBlacklistCompat."""
    
    @pytest_asyncio.fixture
    async def db_manager(self):
        """Create a test database manager with temporary database."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name
        
        try:
            manager = DatabaseManager(db_path)
            await manager.initialize_database()
            yield manager
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    @pytest_asyncio.fixture
    async def guild_blacklist_manager(self, db_manager):
        """Create a GuildBlacklistManager instance."""
        return GuildBlacklistManager(db_manager)
    
    @pytest_asyncio.fixture
    async def compat_blacklist(self, guild_blacklist_manager):
        """Create an EmojiBlacklistCompat instance."""
        guild_id = 12345
        return EmojiBlacklistCompat(guild_blacklist_manager, guild_id)
    
    @pytest.fixture
    def mock_unicode_emoji(self):
        """Mock Unicode emoji."""
        return "😀"
    
    @pytest.fixture
    def mock_custom_emoji(self):
        """Mock custom Discord emoji."""
        emoji = Mock(spec=discord.Emoji)
        emoji.id = 123456789
        emoji.name = "test_emoji"
        emoji.animated = False
        return emoji

    @pytest.mark.asyncio
    async def test_add_and_check_unicode_emoji(self, compat_blacklist, mock_unicode_emoji):
        """Test adding and checking a Unicode emoji."""
        # Add emoji
        result = await compat_blacklist.add_emoji(mock_unicode_emoji)
        assert result is True
        
        # Check if blacklisted
        is_blacklisted = await compat_blacklist.is_blacklisted(mock_unicode_emoji)
        assert is_blacklisted is True
        
        # Try to add again (should return False)
        result = await compat_blacklist.add_emoji(mock_unicode_emoji)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_add_and_check_custom_emoji(self, compat_blacklist, mock_custom_emoji):
        """Test adding and checking a custom emoji."""
        # Add emoji
        result = await compat_blacklist.add_emoji(mock_custom_emoji)
        assert result is True
        
        # Check if blacklisted
        is_blacklisted = await compat_blacklist.is_blacklisted(mock_custom_emoji)
        assert is_blacklisted is True
    
    @pytest.mark.asyncio
    async def test_remove_emoji(self, compat_blacklist, mock_unicode_emoji):
        """Test removing an emoji."""
        # Add emoji first
        await compat_blacklist.add_emoji(mock_unicode_emoji)
        
        # Remove emoji
        result = await compat_blacklist.remove_emoji(mock_unicode_emoji)
        assert result is True
        
        # Check if no longer blacklisted
        is_blacklisted = await compat_blacklist.is_blacklisted(mock_unicode_emoji)
        assert is_blacklisted is False
    
    @pytest.mark.asyncio
    async def test_get_emoji_display(self, compat_blacklist, mock_unicode_emoji, mock_custom_emoji):
        """Test getting emoji display strings."""
        # Unicode emoji
        display = compat_blacklist.get_emoji_display(mock_unicode_emoji)
        assert display == mock_unicode_emoji
        
        # Custom emoji
        display = compat_blacklist.get_emoji_display(mock_custom_emoji)
        expected = f"<:{mock_custom_emoji.name}:{mock_custom_emoji.id}>"
        assert display == expected
    
    @pytest.mark.asyncio
    async def test_get_all_display(self, compat_blacklist, mock_unicode_emoji, mock_custom_emoji):
        """Test getting all display strings."""
        # Add emojis
        await compat_blacklist.add_emoji(mock_unicode_emoji)
        await compat_blacklist.add_emoji(mock_custom_emoji)
        
        # Get all displays
        displays = await compat_blacklist.get_all_display()
        assert len(displays) == 2
        assert mock_unicode_emoji in displays
        
        custom_display = f"<:{mock_custom_emoji.name}:{mock_custom_emoji.id}>"
        assert custom_display in displays
    
    @pytest.mark.asyncio
    async def test_to_dict_and_from_dict(self, compat_blacklist, mock_unicode_emoji, mock_custom_emoji):
        """Test dictionary serialization and deserialization."""
        # Add emojis
        await compat_blacklist.add_emoji(mock_unicode_emoji)
        await compat_blacklist.add_emoji(mock_custom_emoji)
        
        # Convert to dict
        data = await compat_blacklist.to_dict()
        assert mock_unicode_emoji in data['unicode_emojis']
        assert mock_custom_emoji.id in data['custom_emoji_ids']
        assert data['custom_emoji_names'][mock_custom_emoji.id] == mock_custom_emoji.name
        
        # Clear and reload from dict
        await compat_blacklist.clear_all()
        await compat_blacklist.from_dict(data)
        
        # Verify emojis are restored
        assert await compat_blacklist.is_blacklisted(mock_unicode_emoji) is True
        assert await compat_blacklist.is_blacklisted(mock_custom_emoji) is True
    
    @pytest.mark.asyncio
    async def test_clear_all(self, compat_blacklist, mock_unicode_emoji, mock_custom_emoji):
        """Test clearing all emojis."""
        # Add emojis
        await compat_blacklist.add_emoji(mock_unicode_emoji)
        await compat_blacklist.add_emoji(mock_custom_emoji)
        
        # Clear all
        await compat_blacklist.clear_all()
        
        # Verify they're gone
        assert await compat_blacklist.is_blacklisted(mock_unicode_emoji) is False
        assert await compat_blacklist.is_blacklisted(mock_custom_emoji) is False
        
        displays = await compat_blacklist.get_all_display()
        assert len(displays) == 0


class TestGlobalEmojiBlacklistManager:
    """Test cases for GlobalEmojiBlacklistManager."""
    
    @pytest_asyncio.fixture
    async def db_manager(self):
        """Create a test database manager with temporary database."""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.db') as tmp_file:
            db_path = tmp_file.name
        
        try:
            manager = DatabaseManager(db_path)
            await manager.initialize_database()
            yield manager
        finally:
            # Cleanup
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    @pytest_asyncio.fixture
    async def guild_blacklist_manager(self, db_manager):
        """Create a GuildBlacklistManager instance."""
        return GuildBlacklistManager(db_manager)
    
    @pytest_asyncio.fixture
    async def global_manager(self, guild_blacklist_manager):
        """Create a GlobalEmojiBlacklistManager instance."""
        return GlobalEmojiBlacklistManager(guild_blacklist_manager)

    @pytest.mark.asyncio
    async def test_get_guild_blacklist(self, global_manager):
        """Test getting guild-specific blacklist instances."""
        guild_id_1 = 12345
        guild_id_2 = 67890
        
        # Get instances
        blacklist_1 = global_manager.get_guild_blacklist(guild_id_1)
        blacklist_2 = global_manager.get_guild_blacklist(guild_id_2)
        
        # Should be different instances
        assert blacklist_1 is not blacklist_2
        assert blacklist_1.guild_id == guild_id_1
        assert blacklist_2.guild_id == guild_id_2
        
        # Getting same guild ID should return same instance
        blacklist_1_again = global_manager.get_guild_blacklist(guild_id_1)
        assert blacklist_1 is blacklist_1_again
    
    @pytest.mark.asyncio
    async def test_migrate_global_blacklist(self, global_manager):
        """Test migrating global blacklist to multiple guilds."""
        guild_ids = [12345, 67890]
        global_data = {
            'unicode_emojis': ['😀', '🎉'],
            'custom_emoji_ids': [123456, 789012],
            'custom_emoji_names': {'123456': 'test1', '789012': 'test2'}
        }
        
        # Perform migration
        await global_manager.migrate_global_blacklist(guild_ids, global_data)
        
        # Verify migration for each guild
        for guild_id in guild_ids:
            blacklist = global_manager.get_guild_blacklist(guild_id)
            
            # Check Unicode emojis
            for emoji in global_data['unicode_emojis']:
                assert await blacklist.is_blacklisted(emoji) is True
            
            # Check display strings
            displays = await blacklist.get_all_display()
            assert len(displays) == 4  # 2 unicode + 2 custom
            
            for emoji in global_data['unicode_emojis']:
                assert emoji in displays
            
            assert "<:test1:123456>" in displays
            assert "<:test2:789012>" in displays


if __name__ == "__main__":
    pytest.main([__file__])