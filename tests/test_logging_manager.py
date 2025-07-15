"""
Tests for the logging and monitoring system.
"""

import pytest
import asyncio
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from database.logging_manager import (
    DatabaseLogger, DatabaseOperation, ConfigurationChange, 
    PerformanceMonitor, AuditLogger, DatabaseMonitoringManager,
    monitoring_manager
)


class TestDatabaseLogger:
    """Test the DatabaseLogger class."""
    
    def test_logger_initialization(self):
        """Test that DatabaseLogger initializes correctly."""
        db_logger = DatabaseLogger("test_db")
        
        assert db_logger.logger.name == "test_db"
        assert db_logger.performance_logger.name == "test_db.performance"
        assert db_logger.audit_logger.name == "test_db.audit"


class TestDatabaseOperation:
    """Test the DatabaseOperation dataclass."""
    
    def test_database_operation_creation(self):
        """Test creating a DatabaseOperation instance."""
        operation = DatabaseOperation(
            operation_type="SELECT",
            table_name="guild_configs",
            guild_id=12345
        )
        
        assert operation.operation_type == "SELECT"
        assert operation.table_name == "guild_configs"
        assert operation.guild_id == 12345
        assert operation.success is True
        assert operation.timestamp is not None
    
    def test_database_operation_with_error(self):
        """Test DatabaseOperation with error information."""
        operation = DatabaseOperation(
            operation_type="INSERT",
            table_name="guild_blacklists",
            guild_id=67890,
            success=False,
            error_message="Database locked"
        )
        
        assert operation.success is False
        assert operation.error_message == "Database locked"


class TestConfigurationChange:
    """Test the ConfigurationChange dataclass."""
    
    def test_configuration_change_creation(self):
        """Test creating a ConfigurationChange instance."""
        change = ConfigurationChange(
            guild_id=12345,
            change_type="UPDATE",
            field_name="timeout_duration",
            old_value=300,
            new_value=600,
            user_id=98765,
            command_name="set_timeout"
        )
        
        assert change.guild_id == 12345
        assert change.change_type == "UPDATE"
        assert change.field_name == "timeout_duration"
        assert change.old_value == 300
        assert change.new_value == 600
        assert change.user_id == 98765
        assert change.command_name == "set_timeout"
        assert change.timestamp is not None


class TestPerformanceMonitor:
    """Test the PerformanceMonitor class."""
    
    def test_performance_monitor_initialization(self):
        """Test PerformanceMonitor initialization."""
        monitor = PerformanceMonitor()
        
        assert monitor.query_stats == {}
        assert monitor.slow_query_threshold == 1.0
    
    def test_record_query_time(self):
        """Test recording query execution times."""
        monitor = PerformanceMonitor()
        
        monitor.record_query_time("SELECT_guild_configs", 0.5)
        monitor.record_query_time("SELECT_guild_configs", 0.3)
        monitor.record_query_time("INSERT_guild_blacklists", 0.8)
        
        assert len(monitor.query_stats["SELECT_guild_configs"]) == 2
        assert len(monitor.query_stats["INSERT_guild_blacklists"]) == 1
        assert 0.5 in monitor.query_stats["SELECT_guild_configs"]
        assert 0.8 in monitor.query_stats["INSERT_guild_blacklists"]
    
    def test_slow_query_detection(self):
        """Test that slow queries are detected and logged."""
        monitor = PerformanceMonitor()
        
        with patch.object(monitor.logger, 'warning') as mock_warning:
            monitor.record_query_time("SLOW_SELECT", 2.5)
            mock_warning.assert_called_once()
            assert "Slow query detected" in mock_warning.call_args[0][0]
    
    def test_get_performance_stats(self):
        """Test getting performance statistics."""
        monitor = PerformanceMonitor()
        
        monitor.record_query_time("SELECT_test", 0.1)
        monitor.record_query_time("SELECT_test", 0.2)
        monitor.record_query_time("SELECT_test", 0.3)
        
        stats = monitor.get_performance_stats()
        
        assert "SELECT_test" in stats
        test_stats = stats["SELECT_test"]
        assert test_stats["count"] == 3
        assert abs(test_stats["avg_time"] - 0.2) < 0.001
        assert test_stats["min_time"] == 0.1
        assert test_stats["max_time"] == 0.3
        assert test_stats["total_time"] == 0.6
    
    def test_reset_stats(self):
        """Test resetting performance statistics."""
        monitor = PerformanceMonitor()
        
        monitor.record_query_time("SELECT_test", 0.1)
        assert len(monitor.query_stats) > 0
        
        monitor.reset_stats()
        assert len(monitor.query_stats) == 0


class TestAuditLogger:
    """Test the AuditLogger class."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.audit_file = Path(self.temp_dir) / "audit.jsonl"
    
    def tearDown(self):
        """Clean up test environment."""
        if self.audit_file.exists():
            self.audit_file.unlink()
        os.rmdir(self.temp_dir)
    
    def test_audit_logger_initialization(self):
        """Test AuditLogger initialization."""
        with patch('database.logging_manager.Path') as mock_path:
            mock_path.return_value.parent.mkdir = Mock()
            audit_logger = AuditLogger()
            assert audit_logger.logger is not None
    
    def test_log_config_change(self):
        """Test logging configuration changes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_file = Path(temp_dir) / "audit.jsonl"
            
            with patch.object(AuditLogger, '__init__', lambda x: None):
                audit_logger = AuditLogger()
                audit_logger.logger = Mock()
                audit_logger.audit_file = audit_file
                
                change = ConfigurationChange(
                    guild_id=12345,
                    change_type="UPDATE",
                    field_name="timeout_duration",
                    old_value=300,
                    new_value=600
                )
                
                audit_logger.log_config_change(change)
                
                # Check that the audit file was created and contains the record
                assert audit_file.exists()
                with open(audit_file, 'r') as f:
                    line = f.readline().strip()
                    record = json.loads(line)
                    assert record['guild_id'] == 12345
                    assert record['change_type'] == "UPDATE"
                    assert record['field_name'] == "timeout_duration"
    
    def test_log_blacklist_change(self):
        """Test logging blacklist changes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_file = Path(temp_dir) / "audit.jsonl"
            
            with patch.object(AuditLogger, '__init__', lambda x: None):
                audit_logger = AuditLogger()
                audit_logger.logger = Mock()
                audit_logger.audit_file = audit_file
                
                emoji_info = {
                    'emoji_type': 'unicode',
                    'emoji_value': '😀',
                    'emoji_name': None,
                    'display': '😀'
                }
                
                audit_logger.log_blacklist_change(
                    guild_id=12345,
                    action="ADD",
                    emoji_info=emoji_info,
                    user_id=98765,
                    command_name="add_blacklist"
                )
                
                # Check that the audit file contains the blacklist change
                assert audit_file.exists()
                with open(audit_file, 'r') as f:
                    line = f.readline().strip()
                    record = json.loads(line)
                    assert record['guild_id'] == 12345
                    assert record['change_type'] == "ADD"
                    assert record['field_name'] == "blacklist"
                    assert record['user_id'] == 98765
    
    def test_get_audit_history(self):
        """Test retrieving audit history."""
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_file = Path(temp_dir) / "audit.jsonl"
            
            # Create test audit records
            test_records = [
                {
                    'guild_id': 12345,
                    'change_type': 'UPDATE',
                    'field_name': 'timeout_duration',
                    'timestamp': '2024-01-01T10:00:00'
                },
                {
                    'guild_id': 67890,
                    'change_type': 'CREATE',
                    'field_name': 'default_config',
                    'timestamp': '2024-01-01T11:00:00'
                }
            ]
            
            with open(audit_file, 'w') as f:
                for record in test_records:
                    f.write(json.dumps(record) + '\n')
            
            with patch.object(AuditLogger, '__init__', lambda x: None):
                audit_logger = AuditLogger()
                audit_logger.logger = Mock()
                audit_logger.audit_file = audit_file
                
                # Test getting all history
                history = audit_logger.get_audit_history()
                assert len(history) == 2
                
                # Test filtering by guild_id
                guild_history = audit_logger.get_audit_history(guild_id=12345)
                assert len(guild_history) == 1
                assert guild_history[0]['guild_id'] == 12345


class TestDatabaseMonitoringManager:
    """Test the DatabaseMonitoringManager class."""
    
    @pytest.mark.asyncio
    async def test_monitor_operation_success(self):
        """Test monitoring a successful database operation."""
        manager = DatabaseMonitoringManager()
        
        operation = DatabaseOperation(
            operation_type="SELECT",
            table_name="guild_configs",
            guild_id=12345
        )
        
        async with manager.monitor_operation(operation):
            # Simulate some work
            await asyncio.sleep(0.01)
        
        assert operation.success is True
        assert operation.execution_time is not None
        assert operation.execution_time > 0
    
    @pytest.mark.asyncio
    async def test_monitor_operation_failure(self):
        """Test monitoring a failed database operation."""
        manager = DatabaseMonitoringManager()
        
        operation = DatabaseOperation(
            operation_type="INSERT",
            table_name="guild_blacklists",
            guild_id=12345
        )
        
        with pytest.raises(ValueError):
            async with manager.monitor_operation(operation):
                raise ValueError("Test error")
        
        assert operation.success is False
        assert operation.error_message == "Test error"
        assert operation.execution_time is not None
    
    def test_log_database_operation(self):
        """Test logging database operations."""
        manager = DatabaseMonitoringManager()
        
        # Test successful operation
        success_operation = DatabaseOperation(
            operation_type="SELECT",
            table_name="guild_configs",
            guild_id=12345,
            execution_time=0.5,
            rows_affected=1,
            success=True
        )
        
        with patch.object(manager.db_logger.logger, 'info') as mock_info:
            manager.log_database_operation(success_operation)
            mock_info.assert_called_once()
            assert "SELECT on guild_configs" in mock_info.call_args[0][0]
        
        # Test failed operation
        failed_operation = DatabaseOperation(
            operation_type="INSERT",
            table_name="guild_blacklists",
            guild_id=12345,
            execution_time=0.3,
            success=False,
            error_message="Database locked"
        )
        
        with patch.object(manager.db_logger.logger, 'error') as mock_error:
            manager.log_database_operation(failed_operation)
            mock_error.assert_called_once()
            assert "INSERT on guild_blacklists" in mock_error.call_args[0][0]
    
    def test_get_monitoring_summary(self):
        """Test getting monitoring summary."""
        manager = DatabaseMonitoringManager()
        
        # Add some performance data
        manager.performance_monitor.record_query_time("SELECT_test", 0.1)
        
        summary = manager.get_monitoring_summary()
        
        assert 'performance_stats' in summary
        assert 'slow_query_threshold' in summary
        assert 'audit_file_exists' in summary
        assert 'audit_file_size' in summary
        assert summary['slow_query_threshold'] == 1.0


class TestGlobalMonitoringManager:
    """Test the global monitoring manager instance."""
    
    def test_global_instance_exists(self):
        """Test that the global monitoring manager instance exists."""
        assert monitoring_manager is not None
        assert isinstance(monitoring_manager, DatabaseMonitoringManager)
    
    def test_global_instance_components(self):
        """Test that the global instance has all required components."""
        assert hasattr(monitoring_manager, 'db_logger')
        assert hasattr(monitoring_manager, 'performance_monitor')
        assert hasattr(monitoring_manager, 'audit_logger')


@pytest.mark.asyncio
async def test_integration_monitoring_workflow():
    """Test the complete monitoring workflow integration."""
    manager = DatabaseMonitoringManager()
    
    # Test database operation monitoring
    operation = DatabaseOperation(
        operation_type="UPDATE",
        table_name="guild_configs",
        guild_id=12345,
        query="UPDATE guild_configs SET timeout_duration = ? WHERE guild_id = ?",
        params=(600, 12345)
    )
    
    async with manager.monitor_operation(operation):
        await asyncio.sleep(0.01)  # Simulate database work
    
    # Verify operation was monitored
    assert operation.success is True
    assert operation.execution_time > 0
    
    # Test configuration change logging
    change = ConfigurationChange(
        guild_id=12345,
        change_type="UPDATE",
        field_name="timeout_duration",
        old_value=300,
        new_value=600,
        user_id=98765,
        command_name="set_timeout"
    )
    
    with patch.object(manager.audit_logger, 'log_config_change') as mock_log:
        manager.audit_logger.log_config_change(change)
        mock_log.assert_called_once_with(change)
    
    # Test performance monitoring
    manager.performance_monitor.record_query_time("UPDATE_guild_configs", operation.execution_time)
    stats = manager.performance_monitor.get_performance_stats()
    assert "UPDATE_guild_configs" in stats


if __name__ == "__main__":
    pytest.main([__file__])