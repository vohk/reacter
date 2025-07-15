"""
Comprehensive logging and monitoring system for database operations and configuration changes.
"""

import logging
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
from pathlib import Path
import asyncio
from contextlib import asynccontextmanager

# Configure structured logging
class DatabaseLogger:
    """Enhanced logger for database operations with performance monitoring."""
    
    def __init__(self, name: str = "database"):
        self.logger = logging.getLogger(name)
        self.performance_logger = logging.getLogger(f"{name}.performance")
        self.audit_logger = logging.getLogger(f"{name}.audit")
        
        # Set up formatters for different log types
        self._setup_formatters()
    
    def _setup_formatters(self):
        """Set up different formatters for different log types."""
        # Standard formatter
        standard_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Performance formatter with additional fields
        performance_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - PERFORMANCE - %(message)s'
        )
        
        # Audit formatter for configuration changes
        audit_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - AUDIT - %(message)s'
        )
        
        # Apply formatters to handlers if they exist
        for handler in self.logger.handlers:
            handler.setFormatter(standard_formatter)
        
        for handler in self.performance_logger.handlers:
            handler.setFormatter(performance_formatter)
            
        for handler in self.audit_logger.handlers:
            handler.setFormatter(audit_formatter)


@dataclass
class DatabaseOperation:
    """Data class for database operation metadata."""
    operation_type: str  # 'SELECT', 'INSERT', 'UPDATE', 'DELETE'
    table_name: str
    guild_id: Optional[int] = None
    query: Optional[str] = None
    params: Optional[tuple] = None
    execution_time: Optional[float] = None
    rows_affected: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class ConfigurationChange:
    """Data class for configuration change audit logs."""
    guild_id: int
    change_type: str  # 'CREATE', 'UPDATE', 'DELETE'
    field_name: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    user_id: Optional[int] = None
    command_name: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


class PerformanceMonitor:
    """Monitor and track database performance metrics."""
    
    def __init__(self):
        self.query_stats: Dict[str, List[float]] = {}
        self.slow_query_threshold = 1.0  # seconds
        self.logger = DatabaseLogger().performance_logger
    
    def record_query_time(self, query_type: str, execution_time: float):
        """Record query execution time for performance analysis."""
        if query_type not in self.query_stats:
            self.query_stats[query_type] = []
        
        self.query_stats[query_type].append(execution_time)
        
        # Log slow queries
        if execution_time > self.slow_query_threshold:
            self.logger.warning(
                f"Slow query detected: {query_type} took {execution_time:.3f}s "
                f"(threshold: {self.slow_query_threshold}s)"
            )
    
    def get_performance_stats(self) -> Dict[str, Dict[str, float]]:
        """Get performance statistics for all query types."""
        stats = {}
        for query_type, times in self.query_stats.items():
            if times:
                stats[query_type] = {
                    'count': len(times),
                    'avg_time': sum(times) / len(times),
                    'min_time': min(times),
                    'max_time': max(times),
                    'total_time': sum(times)
                }
        return stats
    
    def reset_stats(self):
        """Reset performance statistics."""
        self.query_stats.clear()
        self.logger.info("Performance statistics reset")


class AuditLogger:
    """Audit logger for configuration changes and sensitive operations."""
    
    def __init__(self):
        self.logger = DatabaseLogger().audit_logger
        self.audit_file = Path("logs/audit.jsonl")
        self.audit_file.parent.mkdir(parents=True, exist_ok=True)
    
    def log_config_change(self, change: ConfigurationChange):
        """Log a configuration change with full audit trail."""
        # Log to standard logger
        self.logger.info(
            f"Config change - Guild: {change.guild_id}, Type: {change.change_type}, "
            f"Field: {change.field_name}, Old: {change.old_value}, New: {change.new_value}, "
            f"User: {change.user_id}, Command: {change.command_name}"
        )
        
        # Write to audit file in JSON Lines format
        try:
            audit_record = asdict(change)
            # Convert datetime to ISO string for JSON serialization
            if audit_record['timestamp']:
                audit_record['timestamp'] = audit_record['timestamp'].isoformat()
            
            with open(self.audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(audit_record) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write audit record to file: {e}")
    
    def log_blacklist_change(self, guild_id: int, action: str, emoji_info: Dict[str, Any], 
                           user_id: Optional[int] = None, command_name: Optional[str] = None):
        """Log blacklist changes with emoji details."""
        change = ConfigurationChange(
            guild_id=guild_id,
            change_type=action.upper(),
            field_name='blacklist',
            old_value=None,
            new_value=emoji_info,
            user_id=user_id,
            command_name=command_name
        )
        self.log_config_change(change)
    
    def get_audit_history(self, guild_id: Optional[int] = None, 
                         limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve audit history from the audit file."""
        try:
            if not self.audit_file.exists():
                return []
            
            records = []
            with open(self.audit_file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        if guild_id is None or record.get('guild_id') == guild_id:
                            records.append(record)
                    except json.JSONDecodeError:
                        continue
            
            # Return most recent records first
            return sorted(records, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
        except Exception as e:
            self.logger.error(f"Failed to read audit history: {e}")
            return []


class DatabaseMonitoringManager:
    """Main manager for database logging and monitoring."""
    
    def __init__(self):
        self.db_logger = DatabaseLogger()
        self.performance_monitor = PerformanceMonitor()
        self.audit_logger = AuditLogger()
    
    @asynccontextmanager
    async def monitor_operation(self, operation: DatabaseOperation):
        """Context manager to monitor database operations."""
        start_time = time.time()
        
        # Log operation start
        self.db_logger.logger.info(
            f"Starting {operation.operation_type} operation on {operation.table_name} "
            f"for guild {operation.guild_id}"
        )
        
        try:
            yield operation
            
            # Calculate execution time
            execution_time = time.time() - start_time
            operation.execution_time = execution_time
            operation.success = True
            
            # Log successful completion
            self.db_logger.logger.info(
                f"Completed {operation.operation_type} operation on {operation.table_name} "
                f"in {execution_time:.3f}s"
            )
            
            # Record performance metrics
            self.performance_monitor.record_query_time(
                f"{operation.operation_type}_{operation.table_name}",
                execution_time
            )
            
        except Exception as e:
            # Calculate execution time even for failed operations
            execution_time = time.time() - start_time
            operation.execution_time = execution_time
            operation.success = False
            operation.error_message = str(e)
            
            # Log error
            self.db_logger.logger.error(
                f"Failed {operation.operation_type} operation on {operation.table_name} "
                f"after {execution_time:.3f}s: {e}"
            )
            
            # Still record performance metrics for failed operations
            self.performance_monitor.record_query_time(
                f"{operation.operation_type}_{operation.table_name}_FAILED",
                execution_time
            )
            
            raise
    
    def log_database_operation(self, operation: DatabaseOperation):
        """Log a database operation with full details."""
        log_message = (
            f"DB Operation: {operation.operation_type} on {operation.table_name} "
            f"- Guild: {operation.guild_id} "
            f"- Time: {operation.execution_time:.3f}s "
            f"- Success: {operation.success}"
        )
        
        if operation.rows_affected is not None:
            log_message += f" - Rows: {operation.rows_affected}"
        
        if not operation.success and operation.error_message:
            log_message += f" - Error: {operation.error_message}"
        
        if operation.success:
            self.db_logger.logger.info(log_message)
        else:
            self.db_logger.logger.error(log_message)
    
    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get a summary of monitoring data."""
        return {
            'performance_stats': self.performance_monitor.get_performance_stats(),
            'slow_query_threshold': self.performance_monitor.slow_query_threshold,
            'audit_file_exists': self.audit_logger.audit_file.exists(),
            'audit_file_size': self.audit_logger.audit_file.stat().st_size if self.audit_logger.audit_file.exists() else 0
        }


# Global monitoring instance
monitoring_manager = DatabaseMonitoringManager()