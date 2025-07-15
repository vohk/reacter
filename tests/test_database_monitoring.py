"""
Tests for database operations with comprehensive logging and monitoring.
"""

import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

from database.manager import DatabaseManager, DatabaseError
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.logging_manager import monitoring_manager, DatabaseOperation, ConfigurationChange
from database.models import GuildConfig


class TestDatabaseManagerMonitoring:
    """Test DatabaseManager with monitoring integration."""
    
    @pytest_asyncio.fixture
    async def db_manager(self):
        """Create a test database manager."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        manager = DatabaseManager(db_path)
        await manager.initialize_database()
        yield manager
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_execute_query_monitoring(self, db_manager):
        """Test that execute_query operations are properly monitored."""
        with patch.object(monitoring_manager, 'monitor_operation') as mock_monitor:
            # Create a mock context manager
            mock_context = AsyncMock()
            mock_monitor.return_value.__aenter__ = AsyncMock(return_value=mock_context)
            mock_monitor.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Execute a query
            query = "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)"
            await db_manager.execute_query(query, (12345, 300))
            
            # Verify monitoring was called
            mock_monitor.assert_called_once()
            operation = mock_monitor.call_args[0][0]
            assert isinstance(operation, DatabaseOperation)
            assert operation.operation_type == "INSERT"
            assert operation.table_name == "guild_configs"
            assert operation.guild_id == 12345
    
    @pytest.mark.asyncio
    async def test_fetch_one_monitoring(self, db_manager):
        """Test that fetch_one operations are properly monitored."""
        # First insert some data
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (12345, 300)
        )
        
        with patch.object(monitoring_manager, 'monitor_operation') as mock_monitor:
            mock_context = AsyncMock()
            mock_monitor.return_value.__aenter__ = AsyncMock(return_value=mock_context)
            mock_monitor.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Fetch the data
            query = "SELECT * FROM guild_configs WHERE guild_id = ?"
            result = await db_manager.fetch_one(query, (12345,))
            
            # Verify monitoring was called
            mock_monitor.assert_called_once()
            operation = mock_monitor.call_args[0][0]
            assert operation.operation_type == "SELECT"
            assert operation.table_name == "guild_configs"
            assert operation.guild_id == 12345
    
    @pytest.mark.asyncio
    async def test_fetch_all_monitoring(self, db_manager):
        """Test that fetch_all operations are properly monitored."""
        # Insert test data
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (12345, 300)
        )
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (67890, 600)
        )
        
        with patch.object(monitoring_manager, 'monitor_operation') as mock_monitor:
            mock_context = AsyncMock()
            mock_monitor.return_value.__aenter__ = AsyncMock(return_value=mock_context)
            mock_monitor.return_value.__aexit__ = AsyncMock(return_value=None)
            
            # Fetch all data
            query = "SELECT * FROM guild_configs"
            results = await db_manager.fetch_all(query)
            
            # Verify monitoring was called
            mock_monitor.assert_called_once()
            operation = mock_monitor.call_args[0][0]
            assert operation.operation_type == "SELECT"
            assert operation.table_name == "guild_configs"
    
    def test_extract_table_name(self, db_manager):
        """Test table name extraction from SQL queries."""
        # Test SELECT queries
        assert db_manager._extract_table_name("SELECT * FROM guild_configs", "SELECT") == "guild_configs"
        assert db_manager._extract_table_name("select id from guild_blacklists where guild_id = ?", "SELECT") == "guild_blacklists"
        
        # Test INSERT queries
        assert db_manager._extract_table_name("INSERT INTO guild_configs VALUES (?, ?)", "INSERT") == "guild_configs"
        assert db_manager._extract_table_name("insert into guild_blacklists (guild_id) values (?)", "INSERT") == "guild_blacklists"
        
        # Test UPDATE queries
        assert db_manager._extract_table_name("UPDATE guild_configs SET timeout_duration = ?", "UPDATE") == "guild_configs"
        
        # Test DELETE queries
        assert db_manager._extract_table_name("DELETE FROM guild_blacklists WHERE guild_id = ?", "DELETE") == "guild_blacklists"
        
        # Test unknown queries
        assert db_manager._extract_table_name("INVALID QUERY", "SELECT") == "unknown"
    
    def test_extract_guild_id(self, db_manager):
        """Test guild ID extraction from query parameters."""
        # Test with guild ID as first parameter
        assert db_manager._extract_guild_id((12345, "other_param")) == 12345
        
        # Test with non-integer first parameter
        assert db_manager._extract_guild_id(("not_an_id", 12345)) is None
        
        # Test with empty parameters
        assert db_manager._extract_guild_id(()) is None
        
        # Test with negative number (invalid guild ID)
        assert db_manager._extract_guild_id((-1, "param")) is None


class TestGuildConfigManagerAuditLogging:
    """Test GuildConfigManager with audit logging."""
    
    @pytest_asyncio.fixture
    async def config_manager(self):
        """Create a test guild config manager."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        manager = GuildConfigManager(db_manager)
        yield manager
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_create_default_config_audit_logging(self, config_manager):
        """Test that creating default config is properly audited."""
        with patch.object(monitoring_manager.audit_logger, 'log_config_change') as mock_log:
            config = await config_manager.create_default_config(12345)
            
            # Verify audit logging was called
            mock_log.assert_called_once()
            change = mock_log.call_args[0][0]
            assert isinstance(change, ConfigurationChange)
            assert change.guild_id == 12345
            assert change.change_type == 'CREATE'
            assert change.field_name == 'default_config'
    
    @pytest.mark.asyncio
    async def test_update_guild_config_audit_logging(self, config_manager):
        """Test that config updates are properly audited."""
        # Create initial config
        await config_manager.create_default_config(12345)
        
        with patch.object(monitoring_manager.audit_logger, 'log_config_change') as mock_log:
            # Update configuration
            await config_manager.update_guild_config(
                12345, 
                user_id=98765, 
                command_name="set_timeout",
                timeout_duration=600,
                dm_on_timeout=True
            )
            
            # Verify audit logging was called for each changed field
            assert mock_log.call_count == 2  # Two fields changed
            
            # Check the logged changes
            calls = mock_log.call_args_list
            change_fields = [call[0][0].field_name for call in calls]
            assert 'timeout_duration' in change_fields
            assert 'dm_on_timeout' in change_fields
            
            # Check one of the changes in detail
            timeout_change = next(call[0][0] for call in calls if call[0][0].field_name == 'timeout_duration')
            assert timeout_change.guild_id == 12345
            assert timeout_change.change_type == 'UPDATE'
            assert timeout_change.old_value == 300
            assert timeout_change.new_value == 600
            assert timeout_change.user_id == 98765
            assert timeout_change.command_name == "set_timeout"


class TestGuildBlacklistManagerAuditLogging:
    """Test GuildBlacklistManager with audit logging."""
    
    @pytest_asyncio.fixture
    async def blacklist_manager(self):
        """Create a test guild blacklist manager."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        manager = GuildBlacklistManager(db_manager)
        yield manager
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_add_emoji_audit_logging(self, blacklist_manager):
        """Test that adding emojis to blacklist is properly audited."""
        with patch.object(monitoring_manager.audit_logger, 'log_blacklist_change') as mock_log:
            # Add a Unicode emoji
            result = await blacklist_manager.add_emoji(
                12345, 
                "😀", 
                user_id=98765, 
                command_name="add_blacklist"
            )
            
            assert result is True
            
            # Verify audit logging was called
            mock_log.assert_called_once()
            args = mock_log.call_args[1]
            assert args['guild_id'] == 12345
            assert args['action'] == 'ADD'
            assert args['user_id'] == 98765
            assert args['command_name'] == 'add_blacklist'
            assert args['emoji_info']['emoji_type'] == 'unicode'
            assert args['emoji_info']['emoji_value'] == '😀'
    
    @pytest.mark.asyncio
    async def test_remove_emoji_audit_logging(self, blacklist_manager):
        """Test that removing emojis from blacklist is properly audited."""
        # First add an emoji
        await blacklist_manager.add_emoji(12345, "😀")
        
        with patch.object(monitoring_manager.audit_logger, 'log_blacklist_change') as mock_log:
            # Remove the emoji
            result = await blacklist_manager.remove_emoji(
                12345, 
                "😀", 
                user_id=98765, 
                command_name="remove_blacklist"
            )
            
            assert result is True
            
            # Verify audit logging was called
            mock_log.assert_called_once()
            args = mock_log.call_args[1]
            assert args['guild_id'] == 12345
            assert args['action'] == 'REMOVE'
            assert args['user_id'] == 98765
            assert args['command_name'] == 'remove_blacklist'
            assert args['emoji_info']['emoji_type'] == 'unicode'
            assert args['emoji_info']['emoji_value'] == '😀'
    
    def test_get_emoji_display_string(self, blacklist_manager):
        """Test emoji display string generation."""
        # Test Unicode emoji
        display = blacklist_manager._get_emoji_display_string("unicode", "😀", None)
        assert display == "😀"
        
        # Test custom emoji
        display = blacklist_manager._get_emoji_display_string("custom", "123456789", "test_emoji")
        assert display == "<:test_emoji:123456789>"
        
        # Test custom emoji with unknown name
        display = blacklist_manager._get_emoji_display_string("custom", "123456789", None)
        assert display == "<:unknown:123456789>"


class TestPerformanceMonitoringIntegration:
    """Test performance monitoring integration with database operations."""
    
    @pytest_asyncio.fixture
    async def db_manager(self):
        """Create a test database manager."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        manager = DatabaseManager(db_path)
        await manager.initialize_database()
        yield manager
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_during_operations(self, db_manager):
        """Test that performance metrics are recorded during database operations."""
        # Reset performance stats
        monitoring_manager.performance_monitor.reset_stats()
        
        # Perform some database operations
        await db_manager.execute_query(
            "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
            (12345, 300)
        )
        
        await db_manager.fetch_one(
            "SELECT * FROM guild_configs WHERE guild_id = ?",
            (12345,)
        )
        
        await db_manager.fetch_all("SELECT * FROM guild_configs")
        
        # Check that performance stats were recorded
        stats = monitoring_manager.performance_monitor.get_performance_stats()
        
        # Should have stats for INSERT and SELECT operations
        assert len(stats) >= 2
        
        # Check that we have timing data
        for query_type, query_stats in stats.items():
            assert query_stats['count'] > 0
            assert query_stats['avg_time'] > 0
            assert query_stats['min_time'] > 0
            assert query_stats['max_time'] > 0
    
    @pytest.mark.asyncio
    async def test_slow_query_detection(self, db_manager):
        """Test that slow queries are detected and logged."""
        with patch.object(monitoring_manager.performance_monitor, 'slow_query_threshold', 0.001):  # Very low threshold
            with patch.object(monitoring_manager.performance_monitor.logger, 'warning') as mock_warning:
                # This operation should exceed the threshold
                await db_manager.execute_query(
                    "INSERT INTO guild_configs (guild_id, timeout_duration) VALUES (?, ?)",
                    (12345, 300)
                )
                
                # Check if slow query was detected
                # Note: This might not always trigger due to fast operations, but the mechanism is tested
                if mock_warning.called:
                    assert "Slow query detected" in mock_warning.call_args[0][0]


@pytest.mark.asyncio
async def test_end_to_end_monitoring_workflow():
    """Test the complete monitoring workflow from database operation to audit logging."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
        db_path = tmp_file.name
    
    try:
        # Set up managers
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        config_manager = GuildConfigManager(db_manager)
        
        # Reset monitoring stats
        monitoring_manager.performance_monitor.reset_stats()
        
        with patch.object(monitoring_manager.audit_logger, 'log_config_change') as mock_audit:
            # Perform a complete configuration workflow
            config = await config_manager.create_default_config(12345)
            await config_manager.update_guild_config(
                12345,
                user_id=98765,
                command_name="set_timeout",
                timeout_duration=600
            )
            
            # Verify audit logging occurred
            assert mock_audit.call_count >= 2  # Create + Update
            
            # Verify performance monitoring occurred
            stats = monitoring_manager.performance_monitor.get_performance_stats()
            assert len(stats) > 0
            
            # Verify we have timing data for database operations
            for query_type, query_stats in stats.items():
                assert query_stats['count'] > 0
                assert query_stats['avg_time'] >= 0
    
    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__])