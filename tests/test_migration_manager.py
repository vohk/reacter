"""
Tests for MigrationManager class.
"""

import pytest
import pytest_asyncio
import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from database.migration_manager import MigrationManager
from database.manager import DatabaseManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.guild_config_manager import GuildConfigManager


class TestMigrationManager:
    """Test cases for MigrationManager."""
    
    @pytest_asyncio.fixture
    async def temp_dir(self):
        """Create temporary directory for test files."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    @pytest_asyncio.fixture
    async def sample_json_data(self):
        """Sample JSON data for testing."""
        return {
            "unicode_emojis": ["😀", "😂", "🎉"],
            "custom_emoji_ids": [123456, 789012],
            "custom_emoji_names": {
                "123456": "test_emoji",
                "789012": "another_emoji"
            }
        }
    
    @pytest_asyncio.fixture
    async def json_file(self, temp_dir, sample_json_data):
        """Create temporary JSON file with sample data."""
        json_file = temp_dir / "test_blacklist.json"
        with open(json_file, 'w') as f:
            json.dump(sample_json_data, f)
        return json_file
    
    @pytest_asyncio.fixture
    async def empty_json_file(self, temp_dir):
        """Create empty JSON file."""
        json_file = temp_dir / "empty_blacklist.json"
        with open(json_file, 'w') as f:
            json.dump({
                "unicode_emojis": [],
                "custom_emoji_ids": [],
                "custom_emoji_names": {}
            }, f)
        return json_file
    
    @pytest_asyncio.fixture
    async def invalid_json_file(self, temp_dir):
        """Create invalid JSON file."""
        json_file = temp_dir / "invalid_blacklist.json"
        with open(json_file, 'w') as f:
            f.write("{ invalid json content")
        return json_file
    
    @pytest_asyncio.fixture
    async def db_manager(self):
        """Mock database manager."""
        mock_db = AsyncMock(spec=DatabaseManager)
        mock_db.initialize_database = AsyncMock()
        mock_db.execute_query = AsyncMock()
        mock_db.fetch_one = AsyncMock()
        mock_db.fetch_all = AsyncMock()
        return mock_db
    
    @pytest_asyncio.fixture
    async def migration_manager(self, db_manager, json_file):
        """Create MigrationManager instance for testing."""
        manager = MigrationManager(db_manager, str(json_file))
        
        # Mock the dependent managers
        manager.guild_blacklist_manager = AsyncMock(spec=GuildBlacklistManager)
        manager.guild_config_manager = AsyncMock(spec=GuildConfigManager)
        
        return manager
    
    @pytest.mark.asyncio
    async def test_init(self, db_manager, json_file):
        """Test MigrationManager initialization."""
        manager = MigrationManager(db_manager, str(json_file))
        
        assert manager.db_manager == db_manager
        assert manager.json_file_path == Path(json_file)
        assert manager.backup_dir == Path("migration_backups")
        assert isinstance(manager.guild_blacklist_manager, GuildBlacklistManager)
        assert isinstance(manager.guild_config_manager, GuildConfigManager)
    
    @pytest.mark.asyncio
    async def test_backup_json_data_success(self, migration_manager, json_file):
        """Test successful backup creation."""
        backup_path = await migration_manager.backup_json_data()
        
        assert backup_path.exists()
        assert backup_path.parent == migration_manager.backup_dir
        assert backup_path.name.startswith("blacklist_backup_")
        assert backup_path.suffix == ".json"
        
        # Verify backup content matches original
        with open(backup_path) as f:
            backup_data = json.load(f)
        with open(json_file) as f:
            original_data = json.load(f)
        
        assert backup_data == original_data
    
    @pytest.mark.asyncio
    async def test_backup_json_data_file_not_found(self, migration_manager):
        """Test backup creation when JSON file doesn't exist."""
        migration_manager.json_file_path = Path("nonexistent.json")
        
        with pytest.raises(FileNotFoundError):
            await migration_manager.backup_json_data()
    
    @pytest.mark.asyncio
    async def test_load_json_data_success(self, migration_manager, sample_json_data):
        """Test successful JSON data loading."""
        data = await migration_manager._load_json_data()
        
        assert data == sample_json_data
    
    @pytest.mark.asyncio
    async def test_load_json_data_file_not_found(self, migration_manager):
        """Test JSON loading when file doesn't exist."""
        migration_manager.json_file_path = Path("nonexistent.json")
        
        data = await migration_manager._load_json_data()
        assert data is None
    
    @pytest.mark.asyncio
    async def test_load_json_data_invalid_json(self, db_manager, invalid_json_file):
        """Test JSON loading with invalid JSON content."""
        manager = MigrationManager(db_manager, str(invalid_json_file))
        
        data = await manager._load_json_data()
        assert data is None
    
    @pytest.mark.asyncio
    async def test_validate_json_structure_valid(self, migration_manager, sample_json_data):
        """Test JSON structure validation with valid data."""
        result = await migration_manager._validate_json_structure(sample_json_data)
        
        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["warnings"]) == 0
    
    @pytest.mark.asyncio
    async def test_validate_json_structure_missing_keys(self, migration_manager):
        """Test JSON structure validation with missing keys."""
        invalid_data = {"unicode_emojis": []}
        
        result = await migration_manager._validate_json_structure(invalid_data)
        
        assert result["valid"] is False
        assert "Missing required key: custom_emoji_ids" in result["errors"]
        assert "Missing required key: custom_emoji_names" in result["errors"]
    
    @pytest.mark.asyncio
    async def test_validate_json_structure_wrong_types(self, migration_manager):
        """Test JSON structure validation with wrong data types."""
        invalid_data = {
            "unicode_emojis": "not a list",
            "custom_emoji_ids": "not a list",
            "custom_emoji_names": "not a dict"
        }
        
        result = await migration_manager._validate_json_structure(invalid_data)
        
        assert result["valid"] is False
        assert "unicode_emojis must be a list" in result["errors"]
        assert "custom_emoji_ids must be a list" in result["errors"]
        assert "custom_emoji_names must be a dictionary" in result["errors"]
    
    @pytest.mark.asyncio
    async def test_validate_json_structure_empty_data(self, migration_manager):
        """Test JSON structure validation with empty data."""
        empty_data = {
            "unicode_emojis": [],
            "custom_emoji_ids": [],
            "custom_emoji_names": {}
        }
        
        result = await migration_manager._validate_json_structure(empty_data)
        
        assert result["valid"] is True
        assert "No emoji data found in JSON file" in result["warnings"]
    
    @pytest.mark.asyncio
    async def test_migrate_from_json_success(self, migration_manager, sample_json_data):
        """Test successful migration from JSON."""
        guild_ids = [12345, 67890]
        default_guild_id = 12345
        
        # Mock successful operations
        migration_manager.guild_config_manager.create_default_config = AsyncMock()
        migration_manager.guild_blacklist_manager.migrate_from_global_blacklist = AsyncMock()
        
        with patch.object(migration_manager, 'backup_json_data') as mock_backup, \
             patch.object(migration_manager, 'validate_migration', return_value=True) as mock_validate:
            
            mock_backup.return_value = Path("backup.json")
            
            result = await migration_manager.migrate_from_json(guild_ids, default_guild_id)
        
        assert result["success"] is True
        assert result["backup_created"] is True
        assert len(result["guilds_migrated"]) == 1
        assert result["guilds_migrated"][0] == default_guild_id
        assert result["statistics"]["unicode_emojis_migrated"] == 3
        assert result["statistics"]["custom_emojis_migrated"] == 2
        assert result["statistics"]["guilds_configured"] == 2
        
        # Verify method calls
        assert migration_manager.guild_config_manager.create_default_config.call_count == 2
        migration_manager.guild_blacklist_manager.migrate_from_global_blacklist.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_migrate_from_json_backup_failure(self, migration_manager):
        """Test migration when backup creation fails."""
        guild_ids = [12345]
        
        with patch.object(migration_manager, 'backup_json_data', side_effect=IOError("Backup failed")):
            result = await migration_manager.migrate_from_json(guild_ids)
        
        assert result["success"] is False
        assert result["backup_created"] is False
        assert "Backup failed" in str(result["errors"])
    
    @pytest.mark.asyncio
    async def test_migrate_from_json_no_data(self, db_manager, temp_dir):
        """Test migration when JSON file doesn't exist."""
        nonexistent_file = temp_dir / "nonexistent.json"
        manager = MigrationManager(db_manager, str(nonexistent_file))
        
        guild_ids = [12345]
        
        with patch.object(manager, 'backup_json_data') as mock_backup:
            mock_backup.return_value = Path("backup.json")
            result = await manager.migrate_from_json(guild_ids)
        
        assert result["success"] is False
        assert "No JSON data found or file is empty" in result["errors"]
    
    @pytest.mark.asyncio
    async def test_migrate_from_json_validation_failure(self, migration_manager):
        """Test migration when validation fails."""
        guild_ids = [12345]
        
        with patch.object(migration_manager, 'backup_json_data') as mock_backup, \
             patch.object(migration_manager, 'validate_migration', return_value=False):
            
            mock_backup.return_value = Path("backup.json")
            result = await migration_manager.migrate_from_json(guild_ids)
        
        assert result["success"] is False
        assert "Migration validation failed" in result["errors"]
    
    @pytest.mark.asyncio
    async def test_validate_migration_success(self, migration_manager, sample_json_data):
        """Test successful migration validation."""
        guild_ids = [12345, 67890]
        primary_guild_id = 12345
        
        # Mock guild config exists
        migration_manager.guild_config_manager.get_guild_config.return_value = {"guild_id": 12345}
        
        # Mock blacklist data
        blacklisted_data = [
            {"emoji_type": "unicode", "emoji_value": "😀"},
            {"emoji_type": "unicode", "emoji_value": "😂"},
            {"emoji_type": "unicode", "emoji_value": "🎉"},
            {"emoji_type": "custom", "emoji_value": "123456"},
            {"emoji_type": "custom", "emoji_value": "789012"}
        ]
        migration_manager.guild_blacklist_manager.get_all_blacklisted.return_value = blacklisted_data
        
        with patch.object(migration_manager, '_validate_emoji_data', return_value=True):
            result = await migration_manager.validate_migration(guild_ids, sample_json_data, primary_guild_id)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_migration_missing_config(self, migration_manager, sample_json_data):
        """Test migration validation when guild config is missing."""
        guild_ids = [12345]
        
        # Mock missing guild config
        migration_manager.guild_config_manager.get_guild_config.return_value = None
        
        result = await migration_manager.validate_migration(guild_ids, sample_json_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_validate_migration_emoji_count_mismatch(self, migration_manager, sample_json_data):
        """Test migration validation when emoji counts don't match."""
        guild_ids = [12345]
        primary_guild_id = 12345
        
        # Mock guild config exists
        migration_manager.guild_config_manager.get_guild_config.return_value = {"guild_id": 12345}
        
        # Mock incorrect blacklist data (missing emojis)
        blacklisted_data = [
            {"emoji_type": "unicode", "emoji_value": "😀"},
            {"emoji_type": "custom", "emoji_value": "123456"}
        ]
        migration_manager.guild_blacklist_manager.get_all_blacklisted.return_value = blacklisted_data
        
        result = await migration_manager.validate_migration(guild_ids, sample_json_data, primary_guild_id)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_rollback_migration_success(self, migration_manager, temp_dir):
        """Test successful migration rollback."""
        guild_ids = [12345, 67890]
        
        # Create backup file
        backup_path = temp_dir / "backup.json"
        backup_data = {"test": "data"}
        with open(backup_path, 'w') as f:
            json.dump(backup_data, f)
        
        # Mock successful cleanup
        migration_manager.guild_blacklist_manager.clear_blacklist = AsyncMock()
        migration_manager.guild_config_manager.delete_guild_config = AsyncMock()
        
        result = await migration_manager.rollback_migration(backup_path, guild_ids)
        
        assert result["success"] is True
        assert result["backup_restored"] is True
        assert result["database_cleaned"] is True
        assert len(result["errors"]) == 0
        
        # Verify original file was restored
        with open(migration_manager.json_file_path) as f:
            restored_data = json.load(f)
        assert restored_data == backup_data
        
        # Verify cleanup calls
        assert migration_manager.guild_blacklist_manager.clear_blacklist.call_count == 2
        assert migration_manager.guild_config_manager.delete_guild_config.call_count == 2
    
    @pytest.mark.asyncio
    async def test_rollback_migration_backup_not_found(self, migration_manager):
        """Test rollback when backup file doesn't exist."""
        guild_ids = [12345]
        backup_path = Path("nonexistent_backup.json")
        
        result = await migration_manager.rollback_migration(backup_path, guild_ids)
        
        assert result["success"] is False
        assert result["backup_restored"] is False
        assert f"Backup file not found: {backup_path}" in result["errors"]
    
    @pytest.mark.asyncio
    async def test_rollback_migration_database_cleanup_failure(self, migration_manager, temp_dir):
        """Test rollback when database cleanup fails."""
        guild_ids = [12345]
        
        # Create backup file
        backup_path = temp_dir / "backup.json"
        with open(backup_path, 'w') as f:
            json.dump({"test": "data"}, f)
        
        # Mock cleanup failure
        migration_manager.guild_blacklist_manager.clear_blacklist = AsyncMock(side_effect=Exception("Cleanup failed"))
        
        result = await migration_manager.rollback_migration(backup_path, guild_ids)
        
        assert result["success"] is False
        assert result["backup_restored"] is True
        assert result["database_cleaned"] is False
        assert "Database cleanup failed" in str(result["errors"])
    
    @pytest.mark.asyncio
    async def test_validate_emoji_data_success(self, migration_manager, sample_json_data):
        """Test successful emoji data validation."""
        guild_id = 12345
        
        # Mock blacklist data that matches original
        blacklisted_data = [
            {"emoji_type": "unicode", "emoji_value": "😀"},
            {"emoji_type": "unicode", "emoji_value": "😂"},
            {"emoji_type": "unicode", "emoji_value": "🎉"},
            {"emoji_type": "custom", "emoji_value": "123456"},
            {"emoji_type": "custom", "emoji_value": "789012"}
        ]
        migration_manager.guild_blacklist_manager.get_all_blacklisted.return_value = blacklisted_data
        
        result = await migration_manager._validate_emoji_data(guild_id, sample_json_data)
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_emoji_data_mismatch(self, migration_manager, sample_json_data):
        """Test emoji data validation with mismatched data."""
        guild_id = 12345
        
        # Mock blacklist data that doesn't match original
        blacklisted_data = [
            {"emoji_type": "unicode", "emoji_value": "😀"},
            {"emoji_type": "custom", "emoji_value": "999999"}  # Wrong custom emoji
        ]
        migration_manager.guild_blacklist_manager.get_all_blacklisted.return_value = blacklisted_data
        
        result = await migration_manager._validate_emoji_data(guild_id, sample_json_data)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_migrate_blacklist_data(self, migration_manager, sample_json_data):
        """Test blacklist data migration."""
        guild_id = 12345
        
        await migration_manager._migrate_blacklist_data(guild_id, sample_json_data)
        
        # Verify the migration call
        migration_manager.guild_blacklist_manager.migrate_from_global_blacklist.assert_called_once()
        call_args = migration_manager.guild_blacklist_manager.migrate_from_global_blacklist.call_args
        
        assert call_args[0][0] == guild_id  # guild_id
        assert call_args[0][1] == {"😀", "😂", "🎉"}  # unicode_emojis
        assert call_args[0][2] == {123456, 789012}  # custom_emoji_ids
        assert call_args[0][3] == {123456: "test_emoji", 789012: "another_emoji"}  # custom_emoji_names
    
    @pytest.mark.asyncio
    async def test_migrate_blacklist_data_string_ids(self, migration_manager):
        """Test blacklist data migration with string emoji IDs."""
        guild_id = 12345
        json_data = {
            "unicode_emojis": ["😀"],
            "custom_emoji_ids": ["123456", "789012"],  # String IDs
            "custom_emoji_names": {
                "123456": "test_emoji",  # String key
                "789012": "another_emoji"
            }
        }
        
        await migration_manager._migrate_blacklist_data(guild_id, json_data)
        
        # Verify the migration call with converted integers
        call_args = migration_manager.guild_blacklist_manager.migrate_from_global_blacklist.call_args
        
        assert call_args[0][2] == {123456, 789012}  # Should be converted to integers
        assert call_args[0][3] == {123456: "test_emoji", 789012: "another_emoji"}  # Keys converted to integers
    
    def test_get_migration_status_no_backups(self, migration_manager):
        """Test migration status when no backups exist."""
        status = migration_manager.get_migration_status()
        
        assert "json_file_exists" in status
        assert "json_file_path" in status
        assert "backup_directory" in status
        assert "backup_directory_exists" in status
        assert "available_backups" in status
        assert isinstance(status["available_backups"], list)
    
    def test_get_migration_status_with_backups(self, migration_manager, temp_dir):
        """Test migration status with existing backups."""
        # Create backup directory and files
        backup_dir = temp_dir / "migration_backups"
        backup_dir.mkdir()
        migration_manager.backup_dir = backup_dir
        
        # Create test backup files
        backup1 = backup_dir / "blacklist_backup_20240101_120000.json"
        backup2 = backup_dir / "blacklist_backup_20240102_120000.json"
        
        backup1.write_text('{"test": "data1"}')
        backup2.write_text('{"test": "data2"}')
        
        status = migration_manager.get_migration_status()
        
        assert status["backup_directory_exists"] is True
        assert len(status["available_backups"]) == 2
        
        # Check backup info structure
        backup_info = status["available_backups"][0]
        assert "filename" in backup_info
        assert "path" in backup_info
        assert "created" in backup_info
        assert "size" in backup_info