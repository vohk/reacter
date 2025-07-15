"""
Unit tests for GuildBlacklistManager.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from unittest.mock import Mock, AsyncMock, patch
import discord

from database.manager import DatabaseManager
from database.guild_blacklist_manager import GuildBlacklistManager


class TestGuildBlacklistManager:
    """Test cases for GuildBlacklistManager."""
    
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
    async def blacklist_manager(self, db_manager):
        """Create a GuildBlacklistManager instance."""
        return GuildBlacklistManager(db_manager)
    
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
        return emoji
    
    @pytest.fixture
    def mock_partial_emoji(self):
        """Mock partial Discord emoji."""
        emoji = Mock(spec=discord.PartialEmoji)
        emoji.id = 987654321
        emoji.name = "partial_emoji"
        return emoji
    
    @pytest.fixture
    def mock_unicode_partial_emoji(self):
        """Mock partial emoji for Unicode (id is None)."""
        emoji = Mock(spec=discord.PartialEmoji)
        emoji.id = None
        emoji.name = "🎉"
        return emoji

    @pytest.mark.asyncio
    async def test_add_unicode_emoji(self, blacklist_manager, mock_unicode_emoji):
        """Test adding a Unicode emoji to blacklist."""
        guild_id = 12345
        
        # Add emoji
        result = await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        assert result is True
        
        # Verify it's blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_unicode_emoji)
        assert is_blacklisted is True
        
        # Try to add again (should return False)
        result = await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_add_custom_emoji(self, blacklist_manager, mock_custom_emoji):
        """Test adding a custom emoji to blacklist."""
        guild_id = 12345
        
        # Add emoji
        result = await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        assert result is True
        
        # Verify it's blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_custom_emoji)
        assert is_blacklisted is True
        
        # Try to add again (should return False)
        result = await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_add_partial_emoji(self, blacklist_manager, mock_partial_emoji):
        """Test adding a partial emoji to blacklist."""
        guild_id = 12345
        
        # Add emoji
        result = await blacklist_manager.add_emoji(guild_id, mock_partial_emoji)
        assert result is True
        
        # Verify it's blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_partial_emoji)
        assert is_blacklisted is True
    
    @pytest.mark.asyncio
    async def test_add_unicode_partial_emoji(self, blacklist_manager, mock_unicode_partial_emoji):
        """Test adding a Unicode partial emoji to blacklist."""
        guild_id = 12345
        
        # Add emoji
        result = await blacklist_manager.add_emoji(guild_id, mock_unicode_partial_emoji)
        assert result is True
        
        # Verify it's blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_unicode_partial_emoji)
        assert is_blacklisted is True
    
    @pytest.mark.asyncio
    async def test_remove_unicode_emoji(self, blacklist_manager, mock_unicode_emoji):
        """Test removing a Unicode emoji from blacklist."""
        guild_id = 12345
        
        # Add emoji first
        await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        
        # Remove emoji
        result = await blacklist_manager.remove_emoji(guild_id, mock_unicode_emoji)
        assert result is True
        
        # Verify it's no longer blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_unicode_emoji)
        assert is_blacklisted is False
        
        # Try to remove again (should return False)
        result = await blacklist_manager.remove_emoji(guild_id, mock_unicode_emoji)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_remove_custom_emoji(self, blacklist_manager, mock_custom_emoji):
        """Test removing a custom emoji from blacklist."""
        guild_id = 12345
        
        # Add emoji first
        await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        
        # Remove emoji
        result = await blacklist_manager.remove_emoji(guild_id, mock_custom_emoji)
        assert result is True
        
        # Verify it's no longer blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_custom_emoji)
        assert is_blacklisted is False
    
    @pytest.mark.asyncio
    async def test_remove_custom_emoji_by_id(self, blacklist_manager, mock_custom_emoji):
        """Test removing a custom emoji by ID."""
        guild_id = 12345
        
        # Add emoji first
        await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        
        # Remove emoji by ID
        result = await blacklist_manager.remove_emoji(guild_id, mock_custom_emoji.id)
        assert result is True
        
        # Verify it's no longer blacklisted
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_custom_emoji)
        assert is_blacklisted is False
    
    @pytest.mark.asyncio
    async def test_is_blacklisted_not_found(self, blacklist_manager, mock_unicode_emoji):
        """Test checking if non-blacklisted emoji is blacklisted."""
        guild_id = 12345
        
        # Check emoji that hasn't been added
        is_blacklisted = await blacklist_manager.is_blacklisted(guild_id, mock_unicode_emoji)
        assert is_blacklisted is False
    
    @pytest.mark.asyncio
    async def test_get_all_blacklisted_empty(self, blacklist_manager):
        """Test getting all blacklisted emojis when none exist."""
        guild_id = 12345
        
        result = await blacklist_manager.get_all_blacklisted(guild_id)
        assert result == []
    
    @pytest.mark.asyncio
    async def test_get_all_blacklisted_with_emojis(self, blacklist_manager, mock_unicode_emoji, mock_custom_emoji):
        """Test getting all blacklisted emojis."""
        guild_id = 12345
        
        # Add emojis
        await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        
        # Get all blacklisted
        result = await blacklist_manager.get_all_blacklisted(guild_id)
        assert len(result) == 2
        
        # Check that both emoji types are present
        emoji_types = {item['emoji_type'] for item in result}
        assert 'unicode' in emoji_types
        assert 'custom' in emoji_types
    
    @pytest.mark.asyncio
    async def test_clear_blacklist(self, blacklist_manager, mock_unicode_emoji, mock_custom_emoji):
        """Test clearing all blacklisted emojis."""
        guild_id = 12345
        
        # Add emojis
        await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        
        # Verify they're added
        result = await blacklist_manager.get_all_blacklisted(guild_id)
        assert len(result) == 2
        
        # Clear blacklist
        await blacklist_manager.clear_blacklist(guild_id)
        
        # Verify they're gone
        result = await blacklist_manager.get_all_blacklisted(guild_id)
        assert len(result) == 0
        
        # Verify they're not blacklisted
        assert await blacklist_manager.is_blacklisted(guild_id, mock_unicode_emoji) is False
        assert await blacklist_manager.is_blacklisted(guild_id, mock_custom_emoji) is False
    
    @pytest.mark.asyncio
    async def test_get_blacklist_display(self, blacklist_manager, mock_unicode_emoji, mock_custom_emoji):
        """Test getting display strings for blacklisted emojis."""
        guild_id = 12345
        
        # Add emojis
        await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        await blacklist_manager.add_emoji(guild_id, mock_custom_emoji)
        
        # Get display strings
        displays = await blacklist_manager.get_blacklist_display(guild_id)
        assert len(displays) == 2
        
        # Check that Unicode emoji is displayed as-is
        assert mock_unicode_emoji in displays
        
        # Check that custom emoji is displayed in proper format
        custom_display = f"<:{mock_custom_emoji.name}:{mock_custom_emoji.id}>"
        assert custom_display in displays
    
    @pytest.mark.asyncio
    async def test_guild_isolation(self, blacklist_manager, mock_unicode_emoji):
        """Test that guilds have isolated blacklists."""
        guild_id_1 = 12345
        guild_id_2 = 67890
        
        # Add emoji to guild 1
        await blacklist_manager.add_emoji(guild_id_1, mock_unicode_emoji)
        
        # Check that it's blacklisted in guild 1 but not guild 2
        assert await blacklist_manager.is_blacklisted(guild_id_1, mock_unicode_emoji) is True
        assert await blacklist_manager.is_blacklisted(guild_id_2, mock_unicode_emoji) is False
        
        # Check that guild 2 has empty blacklist
        result = await blacklist_manager.get_all_blacklisted(guild_id_2)
        assert len(result) == 0
    
    @pytest.mark.asyncio
    async def test_emoji_type_detection(self, blacklist_manager):
        """Test emoji type detection for different emoji formats."""
        # Test Unicode string
        emoji_type, emoji_value, emoji_name = blacklist_manager._parse_emoji("😀")
        assert emoji_type == "unicode"
        assert emoji_value == "😀"
        assert emoji_name is None
        
        # Test custom emoji
        custom_emoji = Mock(spec=discord.Emoji)
        custom_emoji.id = 123456
        custom_emoji.name = "test"
        
        emoji_type, emoji_value, emoji_name = blacklist_manager._parse_emoji(custom_emoji)
        assert emoji_type == "custom"
        assert emoji_value == "123456"
        assert emoji_name == "test"
        
        # Test partial emoji (Unicode)
        partial_emoji = Mock(spec=discord.PartialEmoji)
        partial_emoji.id = None
        partial_emoji.name = "🎉"
        
        emoji_type, emoji_value, emoji_name = blacklist_manager._parse_emoji(partial_emoji)
        assert emoji_type == "unicode"
        assert emoji_value == "🎉"
        assert emoji_name is None
    
    @pytest.mark.asyncio
    async def test_cache_functionality(self, blacklist_manager, mock_unicode_emoji):
        """Test that caching works correctly."""
        guild_id = 12345
        
        # Add emoji (should populate cache)
        await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        
        # Check that cache is populated
        assert guild_id in blacklist_manager._cache
        assert mock_unicode_emoji in blacklist_manager._cache[guild_id]["unicode"]
        
        # Remove emoji (should update cache)
        await blacklist_manager.remove_emoji(guild_id, mock_unicode_emoji)
        
        # Check that cache is updated
        assert mock_unicode_emoji not in blacklist_manager._cache[guild_id]["unicode"]
    
    @pytest.mark.asyncio
    async def test_migrate_from_global_blacklist(self, blacklist_manager):
        """Test migration from global blacklist format."""
        guild_id = 12345
        
        # Mock global blacklist data
        unicode_emojis = {"😀", "🎉"}
        custom_emoji_ids = {123456, 789012}
        custom_emoji_names = {123456: "test1", 789012: "test2"}
        
        # Perform migration
        await blacklist_manager.migrate_from_global_blacklist(
            guild_id, unicode_emojis, custom_emoji_ids, custom_emoji_names
        )
        
        # Verify migration
        all_blacklisted = await blacklist_manager.get_all_blacklisted(guild_id)
        assert len(all_blacklisted) == 4  # 2 unicode + 2 custom
        
        # Check that Unicode emojis are migrated
        for emoji in unicode_emojis:
            assert await blacklist_manager.is_blacklisted(guild_id, emoji) is True
        
        # Check display strings
        displays = await blacklist_manager.get_blacklist_display(guild_id)
        assert len(displays) == 4
        
        # Verify Unicode emojis in display
        for emoji in unicode_emojis:
            assert emoji in displays
        
        # Verify custom emojis in display
        assert "<:test1:123456>" in displays
        assert "<:test2:789012>" in displays
    
    @pytest.mark.asyncio
    async def test_error_handling_database_failure(self, blacklist_manager, mock_unicode_emoji):
        """Test error handling when database operations fail."""
        guild_id = 12345
        
        # Mock database manager to raise exception
        with patch.object(blacklist_manager.db_manager, 'execute_query', side_effect=Exception("DB Error")):
            # Should raise exception
            with pytest.raises(Exception):
                await blacklist_manager.add_emoji(guild_id, mock_unicode_emoji)
        
        # Test is_blacklisted with database error (should return False)
        with patch.object(blacklist_manager.db_manager, 'fetch_all', side_effect=Exception("DB Error")):
            result = await blacklist_manager.is_blacklisted(guild_id, mock_unicode_emoji)
            assert result is False
    
    @pytest.mark.asyncio
    async def test_invalid_emoji_parsing(self, blacklist_manager):
        """Test handling of invalid emoji objects."""
        # Test with object that doesn't match expected patterns
        invalid_emoji = Mock()
        # Remove expected attributes
        if hasattr(invalid_emoji, 'id'):
            delattr(invalid_emoji, 'id')
        if hasattr(invalid_emoji, 'name'):
            delattr(invalid_emoji, 'name')
        
        with pytest.raises(ValueError):
            blacklist_manager._parse_emoji(invalid_emoji)


if __name__ == "__main__":
    pytest.main([__file__])