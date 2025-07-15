"""
Unit tests for DatabaseManager.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from pathlib import Path
from database.manager import DatabaseManager


class TestDatabaseManager:
    """Test cases for DatabaseManager class."""
    
    @pytest_asyncio.fixture
    async def temp_db_manager(self):
        """Create a temporary database manager for testing."""
        # Create temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        temp_file.close()
        
        db_manager = DatabaseManager(temp_file.name)
        await db_manager.initialize_database()
        
        yield db_manager
        
        # Cleanup
        await db_manager.close()
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)
    
    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_db_manager):
        """Test database initialization creates tables correctly."""
        db_manager = temp_db_manager
        
        # Check that tables exist by querying them
        guild_configs = await db_manager.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_configs'"
        )
        guild_blacklists = await db_manager.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='guild_blacklists'"
        )
        
        assert len(guild_configs) == 1
        assert len(guild_blacklists) == 1
        assert guild_configs[0]['name'] == 'guild_configs'
        assert guild_blacklists[0]['name'] == 'guild_blacklists'
    
    @pytest.mark.asyncio
    async def test_execute_query_insert(self, temp_db_manager):
        """Test executing INSERT queries."""
        db_manager = temp_db_manager
        
        # Insert a guild config
        result = await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (123456789, 600)
        )
        
        assert result is not None  # Should return lastrowid
        
        # Verify the insert
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        assert config is not None
        assert config['guild_id'] == 123456789
        assert config['timeout_duration'] == 600
    
    @pytest.mark.asyncio
    async def test_execute_query_update(self, temp_db_manager):
        """Test executing UPDATE queries."""
        db_manager = temp_db_manager
        
        # Insert a guild config first
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (123456789, 300)
        )
        
        # Update the config
        await db_manager.execute_query(
            "UPDATE guild_configs SET timeout_duration = ? WHERE guild_id = ?",
            (600, 123456789)
        )
        
        # Verify the update
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        assert config['timeout_duration'] == 600
    
    @pytest.mark.asyncio
    async def test_execute_query_delete(self, temp_db_manager):
        """Test executing DELETE queries."""
        db_manager = temp_db_manager
        
        # Insert a guild config first
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (123456789, 300)
        )
        
        # Delete the config
        await db_manager.execute_query(
            "DELETE FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        # Verify the deletion
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        assert config is None
    
    @pytest.mark.asyncio
    async def test_fetch_one_existing(self, temp_db_manager):
        """Test fetching a single existing row."""
        db_manager = temp_db_manager
        
        # Insert test data
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, log_channel_id, timeout_duration) VALUES (?, ?, ?)",
            (123456789, 987654321, 450)
        )
        
        # Fetch the row
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        assert config is not None
        assert config['guild_id'] == 123456789
        assert config['log_channel_id'] == 987654321
        assert config['timeout_duration'] == 450
        assert config['dm_on_timeout'] == 0  # SQLite stores boolean as 0/1
    
    @pytest.mark.asyncio
    async def test_fetch_one_nonexistent(self, temp_db_manager):
        """Test fetching a non-existent row returns None."""
        db_manager = temp_db_manager
        
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (999999999,)
        )
        
        assert config is None
    
    @pytest.mark.asyncio
    async def test_fetch_all_multiple_rows(self, temp_db_manager):
        """Test fetching multiple rows."""
        db_manager = temp_db_manager
        
        # Insert multiple guild configs
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (111111111, 300)
        )
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (222222222, 600)
        )
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (333333333, 900)
        )
        
        # Fetch all configs
        configs = await db_manager.fetch_all("SELECT * FROM guild_configs ORDER BY guild_id")
        
        assert len(configs) == 3
        assert configs[0]['guild_id'] == 111111111
        assert configs[1]['guild_id'] == 222222222
        assert configs[2]['guild_id'] == 333333333
    
    @pytest.mark.asyncio
    async def test_fetch_all_empty_result(self, temp_db_manager):
        """Test fetching from empty table returns empty list."""
        db_manager = temp_db_manager
        
        configs = await db_manager.fetch_all("SELECT * FROM guild_configs")
        
        assert configs == []
    
    @pytest.mark.asyncio
    async def test_guild_blacklists_foreign_key_constraint(self, temp_db_manager):
        """Test foreign key constraint between guild_blacklists and guild_configs."""
        db_manager = temp_db_manager
        
        # Insert guild config first
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id) VALUES (?)",
            (123456789,)
        )
        
        # Insert blacklisted emoji
        await db_manager.execute_query(
            "INSERT INTO guild_blacklists (guild_id, emoji_type, emoji_value) VALUES (?, ?, ?)",
            (123456789, "unicode", "😀")
        )
        
        # Verify the insert
        emoji = await db_manager.fetch_one(
            "SELECT * FROM guild_blacklists WHERE guild_id = ?",
            (123456789,)
        )
        
        assert emoji is not None
        assert emoji['guild_id'] == 123456789
        assert emoji['emoji_type'] == "unicode"
        assert emoji['emoji_value'] == "😀"
    
    @pytest.mark.asyncio
    async def test_guild_blacklists_unique_constraint(self, temp_db_manager):
        """Test unique constraint on guild_blacklists."""
        db_manager = temp_db_manager
        
        # Insert guild config first
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id) VALUES (?)",
            (123456789,)
        )
        
        # Insert blacklisted emoji
        await db_manager.execute_query(
            "INSERT INTO guild_blacklists (guild_id, emoji_type, emoji_value) VALUES (?, ?, ?)",
            (123456789, "unicode", "😀")
        )
        
        # Try to insert the same emoji again - should fail
        with pytest.raises(Exception):  # Should raise integrity error
            await db_manager.execute_query(
                "INSERT INTO guild_blacklists (guild_id, emoji_type, emoji_value) VALUES (?, ?, ?)",
                (123456789, "unicode", "😀")
            )
    
    @pytest.mark.asyncio
    async def test_database_path_creation(self):
        """Test that database manager creates directory path if it doesn't exist."""
        # Create a temporary directory path that doesn't exist
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "subdir", "test.db")
        
        # Ensure the subdirectory doesn't exist
        subdir = os.path.dirname(db_path)
        if os.path.exists(subdir):
            os.rmdir(subdir)
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        
        # Check that the directory was created
        assert os.path.exists(subdir)
        assert os.path.exists(db_path)
        
        # Cleanup
        await db_manager.close()
        os.unlink(db_path)
        os.rmdir(subdir)
        os.rmdir(temp_dir)
    
    @pytest.mark.asyncio
    async def test_connection_handling(self, temp_db_manager):
        """Test proper connection handling and cleanup."""
        db_manager = temp_db_manager
        
        # Perform some operations
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id) VALUES (?)",
            (123456789,)
        )
        
        config = await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (123456789,)
        )
        
        assert config is not None
        
        # Close should not raise an error
        await db_manager.close()