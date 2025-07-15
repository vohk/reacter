"""
Database manager for SQLite operations.
"""

import sqlite3
import aiosqlite
import asyncio
import logging
import time
from typing import Any, Optional, List, Dict
from pathlib import Path
from .logging_manager import monitoring_manager, DatabaseOperation

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass


class DatabaseManager:
    """Manages SQLite database connections and operations."""
    
    def __init__(self, db_path: str = "bot_data.db"):
        """Initialize database manager with path to SQLite database."""
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
    
    async def initialize_database(self) -> None:
        """Initialize database schema and create tables if they don't exist."""
        try:
            # Ensure database directory exists
            db_file = Path(self.db_path)
            db_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Create connection and initialize schema
            async with aiosqlite.connect(self.db_path) as db:
                await self._create_schema(db)
                await db.commit()
                logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    async def _create_schema(self, db: aiosqlite.Connection) -> None:
        """Create database schema with guild_configs and guild_blacklists tables."""
        # Guild configurations table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id INTEGER PRIMARY KEY,
                log_channel_id INTEGER,
                timeout_duration INTEGER DEFAULT 300,
                dm_on_timeout BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Guild-specific emoji blacklists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS guild_blacklists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                emoji_type TEXT NOT NULL,
                emoji_value TEXT NOT NULL,
                emoji_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guild_id) REFERENCES guild_configs(guild_id),
                UNIQUE(guild_id, emoji_type, emoji_value)
            )
        """)
        
        # Create index for performance
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_guild_blacklists_guild_id 
            ON guild_blacklists(guild_id)
        """)
        
        logger.info("Database schema created successfully")
    
    async def execute_query(self, query: str, params: tuple = ()) -> Any:
        """Execute a query that modifies data (INSERT, UPDATE, DELETE)."""
        # Determine operation type and table name for monitoring
        operation_type = query.strip().split()[0].upper()
        table_name = self._extract_table_name(query, operation_type)
        guild_id = self._extract_guild_id(params)
        
        operation = DatabaseOperation(
            operation_type=operation_type,
            table_name=table_name,
            guild_id=guild_id,
            query=query,
            params=params
        )
        
        async with monitoring_manager.monitor_operation(operation):
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    async with aiosqlite.connect(self.db_path) as db:
                        cursor = await db.execute(query, params)
                        await db.commit()
                        
                        # Record rows affected for monitoring
                        operation.rows_affected = cursor.rowcount
                        
                        logger.debug(f"Executed {operation_type} on {table_name} - "
                                   f"Rows affected: {cursor.rowcount}, "
                                   f"Time: {time.time() - start_time:.3f}s")
                        
                        return cursor.lastrowid
                        
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    else:
                        logger.error(f"Database operational error: {e}")
                        raise DatabaseError(f"Database operation failed: {e}")
                except sqlite3.IntegrityError as e:
                    logger.error(f"Database integrity error: {e}")
                    raise DatabaseError(f"Data integrity violation: {e}")
                except sqlite3.Error as e:
                    logger.error(f"SQLite error: {e}")
                    raise DatabaseError(f"Database error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error executing query: {query} with params {params}. Error: {e}")
                    raise DatabaseError(f"Unexpected database error: {e}")
            
            raise DatabaseError("Database operation failed after maximum retries")
    
    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row from the database."""
        # Set up monitoring for SELECT operations
        operation_type = "SELECT"
        table_name = self._extract_table_name(query, operation_type)
        guild_id = self._extract_guild_id(params)
        
        operation = DatabaseOperation(
            operation_type=operation_type,
            table_name=table_name,
            guild_id=guild_id,
            query=query,
            params=params
        )
        
        async with monitoring_manager.monitor_operation(operation):
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    async with aiosqlite.connect(self.db_path) as db:
                        db.row_factory = aiosqlite.Row
                        cursor = await db.execute(query, params)
                        row = await cursor.fetchone()
                        
                        # Record performance metrics
                        operation.rows_affected = 1 if row else 0
                        
                        logger.debug(f"Executed SELECT on {table_name} - "
                                   f"Found: {1 if row else 0} row, "
                                   f"Time: {time.time() - start_time:.3f}s")
                        
                        return dict(row) if row else None
                        
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"Database locked during fetch_one, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"Database operational error during fetch_one: {e}")
                        raise DatabaseError(f"Database fetch operation failed: {e}")
                except sqlite3.Error as e:
                    logger.error(f"SQLite error during fetch_one: {e}")
                    raise DatabaseError(f"Database error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error during fetch_one: {query} with params {params}. Error: {e}")
                    raise DatabaseError(f"Unexpected database error: {e}")
            
            raise DatabaseError("Database fetch operation failed after maximum retries")
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows from the database."""
        # Set up monitoring for SELECT operations
        operation_type = "SELECT"
        table_name = self._extract_table_name(query, operation_type)
        guild_id = self._extract_guild_id(params)
        
        operation = DatabaseOperation(
            operation_type=operation_type,
            table_name=table_name,
            guild_id=guild_id,
            query=query,
            params=params
        )
        
        async with monitoring_manager.monitor_operation(operation):
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                try:
                    start_time = time.time()
                    async with aiosqlite.connect(self.db_path) as db:
                        db.row_factory = aiosqlite.Row
                        cursor = await db.execute(query, params)
                        rows = await cursor.fetchall()
                        
                        # Record performance metrics
                        operation.rows_affected = len(rows)
                        
                        logger.debug(f"Executed SELECT on {table_name} - "
                                   f"Found: {len(rows)} rows, "
                                   f"Time: {time.time() - start_time:.3f}s")
                        
                        return [dict(row) for row in rows]
                        
                except sqlite3.OperationalError as e:
                    if "database is locked" in str(e).lower() and attempt < max_retries - 1:
                        logger.warning(f"Database locked during fetch_all, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        logger.error(f"Database operational error during fetch_all: {e}")
                        raise DatabaseError(f"Database fetch operation failed: {e}")
                except sqlite3.Error as e:
                    logger.error(f"SQLite error during fetch_all: {e}")
                    raise DatabaseError(f"Database error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error during fetch_all: {query} with params {params}. Error: {e}")
                    raise DatabaseError(f"Unexpected database error: {e}")
            
            raise DatabaseError("Database fetch operation failed after maximum retries")
    
    async def close(self) -> None:
        """Close database connection if open."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")
    
    def _extract_table_name(self, query: str, operation_type: str) -> str:
        """Extract table name from SQL query for monitoring purposes."""
        try:
            query_lower = query.lower().strip()
            
            if operation_type == "SELECT":
                # Look for "FROM table_name"
                if " from " in query_lower:
                    parts = query_lower.split(" from ")[1].split()
                    return parts[0] if parts else "unknown"
            elif operation_type in ["INSERT", "REPLACE"]:
                # Look for "INSERT INTO table_name" or "REPLACE INTO table_name"
                if " into " in query_lower:
                    parts = query_lower.split(" into ")[1].split()
                    return parts[0] if parts else "unknown"
            elif operation_type == "UPDATE":
                # Look for "UPDATE table_name"
                parts = query_lower.split()
                if len(parts) > 1:
                    return parts[1]
            elif operation_type == "DELETE":
                # Look for "DELETE FROM table_name"
                if " from " in query_lower:
                    parts = query_lower.split(" from ")[1].split()
                    return parts[0] if parts else "unknown"
            
            return "unknown"
        except Exception:
            return "unknown"
    
    def _extract_guild_id(self, params: tuple) -> Optional[int]:
        """Extract guild_id from query parameters for monitoring purposes."""
        try:
            # Guild ID is typically the first parameter in our queries
            if params and len(params) > 0:
                first_param = params[0]
                if isinstance(first_param, int) and first_param > 0:
                    return first_param
            return None
        except Exception:
            return None