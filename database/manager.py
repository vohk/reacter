"""
Database manager for SQLite operations.
"""

import sqlite3
import aiosqlite
import logging
from typing import Any, Optional, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


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
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(query, params)
                await db.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to execute query: {query} with params {params}. Error: {e}")
            raise
    
    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
        """Fetch a single row from the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query, params)
                row = await cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to fetch one: {query} with params {params}. Error: {e}")
            raise
    
    async def fetch_all(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Fetch all rows from the database."""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(query, params)
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to fetch all: {query} with params {params}. Error: {e}")
            raise
    
    async def close(self) -> None:
        """Close database connection if open."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("Database connection closed")