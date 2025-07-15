"""
Integration tests for bot startup sequence and initialization.
"""

import pytest
import pytest_asyncio
import asyncio
import os
import json
import tempfile
import shutil
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

import discord
from database.manager import DatabaseManager, DatabaseError
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.migration_manager import MigrationManager
from database.models import GuildConfig


class TestBotStartupIntegration:
    """Integration tests for complete bot startup sequence."""
    
    @pytest_asyncio.fixture
    async def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        
        yield db_manager
        
        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass
    
    @pytest.fixture
    def temp_blacklist_file(self):
        """Create a temporary blacklist file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            blacklist_data = {
                "unicode_emojis": ["😀", "😂", "🎉"],
                "custom_emoji_ids": [123456789, 987654321],
                "custom_emoji_names": {
                    "123456789": "test_emoji",
                    "987654321": "another_emoji"
                }
            }
            json.dump(blacklist_data, tmp, indent=2)
            blacklist_path = tmp.name
        
        yield blacklist_path
        
        # Cleanup
        try:
            os.unlink(blacklist_path)
        except OSError:
            pass
    
    @pytest.fixture
    def mock_guilds(self):
        """Create mock guilds for testing."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111111111
        guild1.name = "Test Guild 1"
        guild1.member_count = 100
        
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222222222
        guild2.name = "Test Guild 2"
        guild2.member_count = 200
        
        return [guild1, guild2]
    
    @pytest.mark.asyncio
    async def test_complete_startup_sequence_with_migration(self, temp_db, temp_blacklist_file, mock_guilds):
        """Test complete bot startup sequence including migration."""
        from main import Reacter
        
        # Mock environment variables
        with patch.dict(os.environ, {
            'BLACKLIST_FILE': temp_blacklist_file,
            'LOG_CHANNEL_ID': '123456',
            'TIMEOUT_DURATION_SECONDS': '600',
            'DM_ON_TIMEOUT': 'true'
        }):
            # Create bot instance
            bot = Reacter()
            bot.db_manager = temp_db
            bot.guild_config_manager = GuildConfigManager(temp_db)
            bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
            bot.migration_manager = MigrationManager(temp_db, temp_blacklist_file)
            
            # Mock guilds property
            with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
                mock_guilds_prop.return_value = mock_guilds
                
                # Run startup sequence
                await bot.setup_hook()
                
                # Verify database initialization
                assert bot.database_initialized is True
                
                # Verify migration completion
                assert bot.migration_completed is True
                
                # Verify guild configurations were created
                for guild in mock_guilds:
                    config = await bot.guild_config_manager.get_guild_config(guild.id)
                    assert config is not None
                    assert config.guild_id == guild.id
                    assert config.timeout_duration == 300  # Default value
                
                # Verify blacklist migration (should be in first guild)
                primary_guild_id = mock_guilds[0].id
                blacklisted = await bot.guild_blacklist_manager.get_all_blacklisted(primary_guild_id)
                
                # Should have migrated emojis
                unicode_emojis = [item for item in blacklisted if item['emoji_type'] == 'unicode']
                custom_emojis = [item for item in blacklisted if item['emoji_type'] == 'custom']
                
                assert len(unicode_emojis) == 3  # 😀, 😂, 🎉
                assert len(custom_emojis) == 2   # Two custom emojis
    
    @pytest.mark.asyncio
    async def test_startup_without_migration_file(self, temp_db, mock_guilds):
        """Test startup when no blacklist file exists."""
        # Mock the BLACKLIST_FILE to point to a nonexistent file
        with patch('main.BLACKLIST_FILE', 'nonexistent_file.json'):
            from main import Reacter
            
            # Create bot instance
            bot = Reacter()
            bot.db_manager = temp_db
            bot.guild_config_manager = GuildConfigManager(temp_db)
            bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
            bot.migration_manager = MigrationManager(temp_db, "nonexistent_file.json")
            
            # Mock guilds property
            with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
                mock_guilds_prop.return_value = mock_guilds
                
                # Run startup sequence
                await bot.setup_hook()
                
                # Verify initialization
                assert bot.database_initialized is True
                # Migration should be marked complete when no file exists (nothing to migrate)
                assert bot.migration_completed is True
                
                # Verify guild configurations were created
                for guild in mock_guilds:
                    config = await bot.guild_config_manager.get_guild_config(guild.id)
                    assert config is not None
                    assert config.guild_id == guild.id
    
    @pytest.mark.asyncio
    async def test_startup_with_existing_configurations(self, temp_db, temp_blacklist_file, mock_guilds):
        """Test startup when guild configurations already exist."""
        from main import Reacter
        
        # Pre-create some guild configurations
        config_manager = GuildConfigManager(temp_db)
        await config_manager.create_default_config(mock_guilds[0].id)
        
        # Create bot instance
        bot = Reacter()
        bot.db_manager = temp_db
        bot.guild_config_manager = config_manager
        bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
        bot.migration_manager = MigrationManager(temp_db, temp_blacklist_file)
        
        # Mock guilds property
        with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
            mock_guilds_prop.return_value = mock_guilds
            
            # Run startup sequence
            await bot.setup_hook()
            
            # Verify initialization
            assert bot.database_initialized is True
            assert bot.migration_completed is True  # Should skip migration
            
            # Verify all guild configurations exist
            for guild in mock_guilds:
                config = await bot.guild_config_manager.get_guild_config(guild.id)
                assert config is not None
    
    @pytest.mark.asyncio
    async def test_startup_with_database_error(self, mock_guilds):
        """Test startup resilience when database initialization fails."""
        from main import Reacter
        
        # Create bot instance
        bot = Reacter()
        
        # Mock database to fail initialization
        with patch.object(bot.db_manager, 'initialize_database') as mock_init:
            mock_init.side_effect = DatabaseError("Database initialization failed")
            
            # Mock guilds property
            with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
                mock_guilds_prop.return_value = mock_guilds
                
                # Run startup sequence - should not raise exception
                await bot.setup_hook()
                
                # Verify graceful degradation
                assert bot.database_initialized is False
                assert bot.migration_completed is False
    
    @pytest.mark.asyncio
    async def test_effective_config_with_database_mode(self, temp_db, mock_guilds):
        """Test get_effective_config in database mode."""
        from main import Reacter
        
        # Create bot instance
        bot = Reacter()
        bot.db_manager = temp_db
        bot.guild_config_manager = GuildConfigManager(temp_db)
        bot.database_initialized = True
        bot.migration_completed = True
        
        guild_id = mock_guilds[0].id
        
        # Create a guild configuration
        await bot.guild_config_manager.create_default_config(guild_id)
        await bot.guild_config_manager.update_guild_config(
            guild_id, 
            timeout_duration=600,
            log_channel_id=123456
        )
        
        # Get effective config
        config = await bot.get_effective_config(guild_id)
        
        # Should return database configuration
        assert config.guild_id == guild_id
        assert config.timeout_duration == 600
        assert config.log_channel_id == 123456
    
    @pytest.mark.asyncio
    async def test_effective_config_with_legacy_mode(self, mock_guilds):
        """Test get_effective_config in legacy mode."""
        # Mock environment variables and reload main module
        with patch.dict(os.environ, {
            'LOG_CHANNEL_ID': '789012',
            'TIMEOUT_DURATION_SECONDS': '900',
            'DM_ON_TIMEOUT': 'true'
        }):
            # Mock the constants directly since they're loaded at import time
            with patch('main.LOG_CHANNEL_ID', 789012):
                with patch('main.TIMEOUT_DURATION', 900):
                    with patch('main.DM_ON_TIMEOUT', True):
                        from main import Reacter
                        
                        # Create bot instance in legacy mode
                        bot = Reacter()
                        bot.database_initialized = False
                        bot.migration_completed = False
                        
                        guild_id = mock_guilds[0].id
                        
                        # Get effective config
                        config = await bot.get_effective_config(guild_id)
                        
                        # Should return environment-based configuration
                        assert config.guild_id == guild_id
                        assert config.timeout_duration == 900
                        assert config.log_channel_id == 789012
                        assert config.dm_on_timeout is True
    
    @pytest.mark.asyncio
    async def test_effective_config_fallback_on_error(self, temp_db, mock_guilds):
        """Test get_effective_config fallback when database operations fail."""
        # Mock the constants directly since they're loaded at import time
        with patch('main.LOG_CHANNEL_ID', 555555):
            with patch('main.TIMEOUT_DURATION', 450):
                with patch('main.DM_ON_TIMEOUT', False):
                    from main import Reacter
                    
                    # Create bot instance
                    bot = Reacter()
                    bot.db_manager = temp_db
                    bot.guild_config_manager = GuildConfigManager(temp_db)
                    bot.database_initialized = True
                    bot.migration_completed = True
                    
                    guild_id = mock_guilds[0].id
                    
                    # Mock database error
                    with patch.object(bot.guild_config_manager, 'get_guild_config') as mock_get:
                        mock_get.side_effect = DatabaseError("Database error")
                        
                        # Get effective config
                        config = await bot.get_effective_config(guild_id)
                        
                        # Should return environment-based fallback
                        assert config.guild_id == guild_id
                        assert config.timeout_duration == 450
                        assert config.log_channel_id == 555555
                        assert config.dm_on_timeout is False
    
    @pytest.mark.asyncio
    async def test_guild_join_with_initialized_database(self, temp_db):
        """Test guild join event when database is initialized."""
        # Import the event handler function directly
        from main import bot
        
        # Replace bot's managers with test instances
        bot.db_manager = temp_db
        bot.guild_config_manager = GuildConfigManager(temp_db)
        bot.database_initialized = True
        
        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 333333333
        mock_guild.name = "New Guild"
        mock_guild.member_count = 50
        
        # Trigger guild join event
        await bot.on_guild_join(mock_guild)
        
        # Verify configuration was created
        config = await bot.guild_config_manager.get_guild_config(mock_guild.id)
        assert config is not None
        assert config.guild_id == mock_guild.id
    
    @pytest.mark.asyncio
    async def test_guild_join_without_initialized_database(self):
        """Test guild join event when database is not initialized."""
        from main import bot
        
        # Set bot to legacy mode
        bot.database_initialized = False
        
        # Mock guild
        mock_guild = MagicMock(spec=discord.Guild)
        mock_guild.id = 444444444
        mock_guild.name = "New Guild"
        mock_guild.member_count = 75
        
        # Trigger guild join event - should not raise exception
        await bot.on_guild_join(mock_guild)
        
        # No configuration should be created (legacy mode)
        # This test just ensures no exceptions are raised
    
    @pytest.mark.asyncio
    async def test_migration_with_no_guilds(self, temp_db, temp_blacklist_file):
        """Test migration behavior when bot has no guilds."""
        from main import Reacter
        
        # Create bot instance
        bot = Reacter()
        bot.db_manager = temp_db
        bot.guild_config_manager = GuildConfigManager(temp_db)
        bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
        bot.migration_manager = MigrationManager(temp_db, temp_blacklist_file)
        
        # Mock guilds property with empty list
        with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
            mock_guilds_prop.return_value = []
            
            # Run startup sequence
            await bot.setup_hook()
            
            # Should complete successfully
            assert bot.database_initialized is True
            assert bot.migration_completed is True
    
    @pytest.mark.asyncio
    async def test_backward_compatibility_during_transition(self, temp_db, mock_guilds):
        """Test that bot works during transition period with mixed configurations."""
        # Mock the constants directly since they're loaded at import time
        with patch('main.LOG_CHANNEL_ID', 111111):
            with patch('main.TIMEOUT_DURATION', 300):
                with patch('main.DM_ON_TIMEOUT', False):
                    from main import Reacter
                    
                    # Create bot instance
                    bot = Reacter()
                    bot.db_manager = temp_db
                    bot.guild_config_manager = GuildConfigManager(temp_db)
                    bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
                    
                    # Simulate partial initialization (database ready, migration not complete)
                    bot.database_initialized = True
                    bot.migration_completed = False
                    
                    guild_id = mock_guilds[0].id
                    
                    # Get effective config - should use environment variables
                    config = await bot.get_effective_config(guild_id)
                    
                    assert config.guild_id == guild_id
                    assert config.timeout_duration == 300
                    assert config.log_channel_id == 111111
                    assert config.dm_on_timeout is False
                    
                    # Now complete migration
                    bot.migration_completed = True
                    
                    # Create database configuration
                    await bot.guild_config_manager.create_default_config(guild_id)
                    await bot.guild_config_manager.update_guild_config(
                        guild_id, 
                        timeout_duration=600
                    )
                    
                    # Get effective config - should now use database
                    config = await bot.get_effective_config(guild_id)
                    
                    assert config.guild_id == guild_id
                    assert config.timeout_duration == 600  # From database


class TestStartupErrorRecovery:
    """Test error recovery scenarios during startup."""
    
    @pytest_asyncio.fixture
    async def temp_db(self):
        """Create a temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        
        yield db_manager
        
        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass
    
    @pytest.fixture
    def temp_blacklist_file(self):
        """Create a temporary blacklist file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as tmp:
            blacklist_data = {
                "unicode_emojis": ["😀", "😂", "🎉"],
                "custom_emoji_ids": [123456789, 987654321],
                "custom_emoji_names": {
                    "123456789": "test_emoji",
                    "987654321": "another_emoji"
                }
            }
            json.dump(blacklist_data, tmp, indent=2)
            blacklist_path = tmp.name
        
        yield blacklist_path
        
        # Cleanup
        try:
            os.unlink(blacklist_path)
        except OSError:
            pass
    
    @pytest.fixture
    def mock_guilds(self):
        """Create mock guilds for testing."""
        guild1 = MagicMock(spec=discord.Guild)
        guild1.id = 111111111
        guild1.name = "Test Guild 1"
        guild1.member_count = 100
        
        guild2 = MagicMock(spec=discord.Guild)
        guild2.id = 222222222
        guild2.name = "Test Guild 2"
        guild2.member_count = 200
        
        return [guild1, guild2]
    
    @pytest.mark.asyncio
    async def test_migration_failure_recovery(self, temp_db, temp_blacklist_file, mock_guilds):
        """Test recovery when migration fails."""
        from main import Reacter
        
        # Create bot instance
        bot = Reacter()
        bot.db_manager = temp_db
        bot.guild_config_manager = GuildConfigManager(temp_db)
        bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
        bot.migration_manager = MigrationManager(temp_db, temp_blacklist_file)
        
        # Mock guilds property
        with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
            mock_guilds_prop.return_value = mock_guilds
            
            # Mock migration to fail
            with patch.object(bot.migration_manager, 'migrate_from_json') as mock_migrate:
                mock_migrate.return_value = {
                    "success": False,
                    "errors": ["Migration failed"]
                }
                
                # Run startup sequence
                await bot.setup_hook()
                
                # Should continue with legacy mode
                assert bot.database_initialized is True
                assert bot.migration_completed is False
    
    @pytest.mark.asyncio
    async def test_guild_initialization_partial_failure(self, temp_db, mock_guilds):
        """Test when some guild initializations fail."""
        from main import Reacter
        
        # Create bot instance
        bot = Reacter()
        bot.db_manager = temp_db
        bot.guild_config_manager = GuildConfigManager(temp_db)
        bot.guild_blacklist_manager = GuildBlacklistManager(temp_db)
        
        # Mock guilds property
        with patch.object(type(bot), 'guilds', new_callable=PropertyMock) as mock_guilds_prop:
            mock_guilds_prop.return_value = mock_guilds
            
            # Mock one guild config creation to fail
            original_get_config = bot.guild_config_manager.get_guild_config
            
            async def mock_get_config(guild_id):
                if guild_id == mock_guilds[0].id:
                    raise DatabaseError("Config creation failed")
                return await original_get_config(guild_id)
            
            with patch.object(bot.guild_config_manager, 'get_guild_config', side_effect=mock_get_config):
                # Run startup sequence
                await bot.setup_hook()
                
                # Should complete despite partial failure
                assert bot.database_initialized is True
                
                # Second guild should have config
                config = await bot.guild_config_manager.get_guild_config(mock_guilds[1].id)
                assert config is not None


if __name__ == "__main__":
    pytest.main([__file__])