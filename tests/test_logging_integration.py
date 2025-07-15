"""
Integration tests for logging and monitoring with bot commands.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from database.manager import DatabaseManager
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager
from database.logging_manager import monitoring_manager


class TestLoggingIntegration:
    """Test logging and monitoring integration with actual bot operations."""
    
    @pytest_asyncio.fixture
    async def setup_managers(self):
        """Set up database managers for testing."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        # Initialize managers
        db_manager = DatabaseManager(db_path)
        await db_manager.initialize_database()
        config_manager = GuildConfigManager(db_manager)
        blacklist_manager = GuildBlacklistManager(db_manager)
        
        # Reset monitoring stats
        monitoring_manager.performance_monitor.reset_stats()
        
        yield {
            'db_manager': db_manager,
            'config_manager': config_manager,
            'blacklist_manager': blacklist_manager
        }
        
        # Cleanup
        if os.path.exists(db_path):
            os.unlink(db_path)
    
    @pytest.mark.asyncio
    async def test_complete_guild_setup_with_logging(self, setup_managers):
        """Test complete guild setup workflow with comprehensive logging."""
        managers = setup_managers
        config_manager = managers['config_manager']
        blacklist_manager = managers['blacklist_manager']
        
        guild_id = 12345
        user_id = 98765
        
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_file = Path(temp_dir) / "audit.jsonl"
            
            with patch.object(monitoring_manager.audit_logger, 'audit_file', audit_file):
                # Step 1: Create default guild configuration
                config = await config_manager.create_default_config(guild_id)
                assert config.guild_id == guild_id
                
                # Step 2: Update guild configuration
                await config_manager.update_guild_config(
                    guild_id,
                    user_id=user_id,
                    command_name="set_timeout",
                    timeout_duration=600,
                    dm_on_timeout=True
                )
                
                # Step 3: Add emojis to blacklist
                await blacklist_manager.add_emoji(
                    guild_id, 
                    "😀", 
                    user_id=user_id, 
                    command_name="add_blacklist"
                )
                
                await blacklist_manager.add_emoji(
                    guild_id, 
                    "🚫", 
                    user_id=user_id, 
                    command_name="add_blacklist"
                )
                
                # Step 4: Remove an emoji from blacklist
                await blacklist_manager.remove_emoji(
                    guild_id, 
                    "😀", 
                    user_id=user_id, 
                    command_name="remove_blacklist"
                )
                
                # Verify audit logging occurred
                assert audit_file.exists()
                
                # Read and verify audit records
                audit_records = []
                with open(audit_file, 'r') as f:
                    for line in f:
                        if line.strip():
                            audit_records.append(json.loads(line.strip()))
                
                # Should have multiple audit records
                assert len(audit_records) >= 5  # Create config + 2 config updates + 2 blacklist adds + 1 remove
                
                # Verify different types of changes were logged
                change_types = [record['change_type'] for record in audit_records]
                assert 'CREATE' in change_types
                assert 'UPDATE' in change_types
                assert 'ADD' in change_types
                assert 'REMOVE' in change_types
                
                # Verify guild_id is consistent
                for record in audit_records:
                    assert record['guild_id'] == guild_id
                
                # Verify user_id is recorded where applicable
                user_records = [r for r in audit_records if r.get('user_id')]
                assert len(user_records) >= 4  # Config updates + blacklist changes
                for record in user_records:
                    assert record['user_id'] == user_id
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_during_operations(self, setup_managers):
        """Test that performance metrics are collected during database operations."""
        managers = setup_managers
        config_manager = managers['config_manager']
        blacklist_manager = managers['blacklist_manager']
        
        guild_id = 12345
        
        # Reset performance stats
        monitoring_manager.performance_monitor.reset_stats()
        
        # Perform various database operations
        await config_manager.create_default_config(guild_id)
        await config_manager.update_guild_config(guild_id, timeout_duration=600)
        await blacklist_manager.add_emoji(guild_id, "😀")
        await blacklist_manager.add_emoji(guild_id, "🚫")
        await blacklist_manager.is_blacklisted(guild_id, "😀")
        await blacklist_manager.get_all_blacklisted(guild_id)
        await blacklist_manager.remove_emoji(guild_id, "😀")
        
        # Check performance statistics
        stats = monitoring_manager.performance_monitor.get_performance_stats()
        
        # Should have stats for various operations
        assert len(stats) > 0
        
        # Check that we have timing data for different operation types
        operation_types = list(stats.keys())
        
        # Should have INSERT operations (for creating configs and adding emojis)
        insert_ops = [op for op in operation_types if 'INSERT' in op]
        assert len(insert_ops) > 0
        
        # Should have SELECT operations (for checking blacklists and getting configs)
        select_ops = [op for op in operation_types if 'SELECT' in op]
        assert len(select_ops) > 0
        
        # Should have UPDATE operations (for config updates)
        update_ops = [op for op in operation_types if 'UPDATE' in op]
        assert len(update_ops) > 0
        
        # Should have DELETE operations (for removing emojis)
        delete_ops = [op for op in operation_types if 'DELETE' in op]
        assert len(delete_ops) > 0
        
        # Verify all stats have reasonable values
        for operation_type, operation_stats in stats.items():
            assert operation_stats['count'] > 0
            assert operation_stats['avg_time'] >= 0
            assert operation_stats['min_time'] >= 0
            assert operation_stats['max_time'] >= operation_stats['min_time']
            assert operation_stats['total_time'] >= operation_stats['max_time']
    
    @pytest.mark.asyncio
    async def test_error_logging_and_recovery(self, setup_managers):
        """Test that errors are properly logged and handled."""
        managers = setup_managers
        config_manager = managers['config_manager']
        
        guild_id = 12345
        
        # Test invalid configuration update
        with pytest.raises(ValueError):
            await config_manager.update_guild_config(
                guild_id,
                timeout_duration=-1  # Invalid timeout
            )
        
        # Test that the guild still works after error
        config = await config_manager.get_guild_config(guild_id)
        assert config.guild_id == guild_id
        
        # Test valid update after error
        await config_manager.update_guild_config(guild_id, timeout_duration=300)
        updated_config = await config_manager.get_guild_config(guild_id)
        assert updated_config.timeout_duration == 300
    
    @pytest.mark.asyncio
    async def test_monitoring_summary_generation(self, setup_managers):
        """Test that monitoring summary provides useful information."""
        managers = setup_managers
        config_manager = managers['config_manager']
        blacklist_manager = managers['blacklist_manager']
        
        guild_id = 12345
        
        # Perform some operations to generate data
        await config_manager.create_default_config(guild_id)
        await blacklist_manager.add_emoji(guild_id, "😀")
        
        # Get monitoring summary
        summary = monitoring_manager.get_monitoring_summary()
        
        # Verify summary structure
        assert 'performance_stats' in summary
        assert 'slow_query_threshold' in summary
        assert 'audit_file_exists' in summary
        assert 'audit_file_size' in summary
        
        # Verify performance stats are included
        assert isinstance(summary['performance_stats'], dict)
        assert len(summary['performance_stats']) > 0
        
        # Verify threshold is set
        assert summary['slow_query_threshold'] > 0
        
        # Verify audit file information
        assert isinstance(summary['audit_file_exists'], bool)
        assert isinstance(summary['audit_file_size'], int)
    
    @pytest.mark.asyncio
    async def test_concurrent_operations_logging(self, setup_managers):
        """Test that concurrent operations are properly logged."""
        managers = setup_managers
        config_manager = managers['config_manager']
        blacklist_manager = managers['blacklist_manager']
        
        guild_ids = [12345, 67890, 11111]
        
        # Reset performance stats
        monitoring_manager.performance_monitor.reset_stats()
        
        # Perform concurrent operations on multiple guilds
        import asyncio
        tasks = []
        
        for guild_id in guild_ids:
            # Create config for each guild
            tasks.append(config_manager.create_default_config(guild_id))
            
            # Add emojis for each guild
            tasks.append(blacklist_manager.add_emoji(guild_id, "😀"))
            tasks.append(blacklist_manager.add_emoji(guild_id, "🚫"))
        
        # Execute all tasks concurrently
        await asyncio.gather(*tasks)
        
        # Verify all guilds have configurations
        for guild_id in guild_ids:
            config = await config_manager.get_guild_config(guild_id)
            assert config.guild_id == guild_id
            
            # Verify blacklists
            blacklisted = await blacklist_manager.get_all_blacklisted(guild_id)
            assert len(blacklisted) == 2
        
        # Verify performance monitoring captured all operations
        stats = monitoring_manager.performance_monitor.get_performance_stats()
        assert len(stats) > 0
        
        # Should have multiple operations of each type
        for operation_type, operation_stats in stats.items():
            if 'INSERT' in operation_type:
                # Should have at least 3 guilds * operations per guild
                assert operation_stats['count'] >= 3


if __name__ == "__main__":
    pytest.main([__file__])