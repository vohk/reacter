"""
Migration manager for handling data migration from JSON to SQLite.
"""

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
import asyncio

from .manager import DatabaseManager
from .guild_blacklist_manager import GuildBlacklistManager
from .guild_config_manager import GuildConfigManager

logger = logging.getLogger(__name__)


class MigrationManager:
    """Manages data migration from JSON blacklist format to SQLite database."""
    
    def __init__(self, db_manager: DatabaseManager, json_file_path: str = "blacklist.json"):
        """
        Initialize migration manager.
        
        Args:
            db_manager: Database manager instance
            json_file_path: Path to the JSON blacklist file
        """
        self.db_manager = db_manager
        self.json_file_path = Path(json_file_path)
        self.backup_dir = Path("migration_backups")
        self.guild_blacklist_manager = GuildBlacklistManager(db_manager)
        self.guild_config_manager = GuildConfigManager(db_manager)
    
    async def migrate_from_json(self, guild_ids: List[int], default_guild_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Migrate blacklist data from JSON to SQLite for specified guilds.
        
        Args:
            guild_ids: List of guild IDs to create configurations for
            default_guild_id: Primary guild ID to migrate existing data to (optional)
            
        Returns:
            Dictionary containing migration results and statistics
        """
        migration_result = {
            "success": False,
            "backup_created": False,
            "guilds_migrated": [],
            "errors": [],
            "statistics": {
                "unicode_emojis_migrated": 0,
                "custom_emojis_migrated": 0,
                "guilds_configured": 0,
                "total_blacklist_entries": 0
            },
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            logger.info(f"Starting migration from {self.json_file_path} for {len(guild_ids)} guilds")
            
            # Step 1: Create backup
            backup_path = await self.backup_json_data()
            migration_result["backup_created"] = True
            migration_result["backup_path"] = str(backup_path)
            logger.info(f"Backup created at {backup_path}")
            
            # Step 2: Load and validate JSON data
            json_data = await self._load_json_data()
            if not json_data:
                migration_result["errors"].append("No JSON data found or file is empty")
                return migration_result
            
            # Step 3: Validate JSON structure
            validation_result = await self._validate_json_structure(json_data)
            if not validation_result["valid"]:
                migration_result["errors"].extend(validation_result["errors"])
                return migration_result
            
            # Step 4: Initialize database if needed
            await self.db_manager.initialize_database()
            
            # Step 5: Create default configurations for all guilds
            for guild_id in guild_ids:
                try:
                    await self.guild_config_manager.create_default_config(guild_id)
                    migration_result["statistics"]["guilds_configured"] += 1
                    logger.info(f"Created default configuration for guild {guild_id}")
                except Exception as e:
                    error_msg = f"Failed to create config for guild {guild_id}: {str(e)}"
                    migration_result["errors"].append(error_msg)
                    logger.error(error_msg)
            
            # Step 6: Migrate blacklist data to primary guild (if specified)
            if default_guild_id and default_guild_id in guild_ids:
                try:
                    await self._migrate_blacklist_data(default_guild_id, json_data)
                    migration_result["guilds_migrated"].append(default_guild_id)
                    
                    # Update statistics
                    migration_result["statistics"]["unicode_emojis_migrated"] = len(json_data.get("unicode_emojis", []))
                    migration_result["statistics"]["custom_emojis_migrated"] = len(json_data.get("custom_emoji_ids", []))
                    migration_result["statistics"]["total_blacklist_entries"] = (
                        migration_result["statistics"]["unicode_emojis_migrated"] + 
                        migration_result["statistics"]["custom_emojis_migrated"]
                    )
                    
                    logger.info(f"Migrated blacklist data to guild {default_guild_id}")
                except Exception as e:
                    error_msg = f"Failed to migrate blacklist data to guild {default_guild_id}: {str(e)}"
                    migration_result["errors"].append(error_msg)
                    logger.error(error_msg)
            
            # Step 7: Validate migration
            validation_passed = await self.validate_migration(guild_ids, json_data, default_guild_id)
            if not validation_passed:
                migration_result["errors"].append("Migration validation failed")
                return migration_result
            
            migration_result["success"] = True
            logger.info("Migration completed successfully")
            
        except Exception as e:
            error_msg = f"Migration failed with unexpected error: {str(e)}"
            migration_result["errors"].append(error_msg)
            logger.error(error_msg)
        
        return migration_result
    
    async def backup_json_data(self) -> Path:
        """
        Create a backup of the JSON file before migration.
        
        Returns:
            Path to the backup file
            
        Raises:
            FileNotFoundError: If JSON file doesn't exist
            IOError: If backup creation fails
        """
        if not self.json_file_path.exists():
            raise FileNotFoundError(f"JSON file not found: {self.json_file_path}")
        
        # Create backup directory
        self.backup_dir.mkdir(exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"blacklist_backup_{timestamp}.json"
        backup_path = self.backup_dir / backup_filename
        
        try:
            # Copy the file
            shutil.copy2(self.json_file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise IOError(f"Failed to create backup: {e}")
    
    async def validate_migration(self, guild_ids: List[int], original_data: Dict[str, Any], primary_guild_id: Optional[int] = None) -> bool:
        """
        Validate that migration was successful by comparing data.
        
        Args:
            guild_ids: List of guild IDs that should have configurations
            original_data: Original JSON data
            primary_guild_id: Guild ID that should have blacklist data
            
        Returns:
            True if validation passes, False otherwise
        """
        try:
            logger.info("Starting migration validation")
            
            # Validate guild configurations exist
            for guild_id in guild_ids:
                config = await self.guild_config_manager.get_guild_config(guild_id)
                if not config:
                    logger.error(f"Guild configuration missing for guild {guild_id}")
                    return False
            
            # Validate blacklist data if primary guild specified
            if primary_guild_id:
                blacklisted = await self.guild_blacklist_manager.get_all_blacklisted(primary_guild_id)
                
                # Count migrated emojis by type
                unicode_count = sum(1 for item in blacklisted if item['emoji_type'] == 'unicode')
                custom_count = sum(1 for item in blacklisted if item['emoji_type'] == 'custom')
                
                # Compare with original data
                original_unicode = len(original_data.get("unicode_emojis", []))
                original_custom = len(original_data.get("custom_emoji_ids", []))
                
                if unicode_count != original_unicode:
                    logger.error(f"Unicode emoji count mismatch: expected {original_unicode}, got {unicode_count}")
                    return False
                
                if custom_count != original_custom:
                    logger.error(f"Custom emoji count mismatch: expected {original_custom}, got {custom_count}")
                    return False
                
                # Validate specific emoji values
                if not await self._validate_emoji_data(primary_guild_id, original_data):
                    return False
            
            logger.info("Migration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Migration validation failed: {e}")
            return False
    
    async def rollback_migration(self, backup_path: Path, guild_ids: List[int]) -> Dict[str, Any]:
        """
        Rollback migration by restoring backup and cleaning up database.
        
        Args:
            backup_path: Path to the backup file
            guild_ids: List of guild IDs to clean up
            
        Returns:
            Dictionary containing rollback results
        """
        rollback_result = {
            "success": False,
            "backup_restored": False,
            "database_cleaned": False,
            "errors": [],
            "timestamp": datetime.now().isoformat()
        }
        
        try:
            logger.info(f"Starting rollback from backup {backup_path}")
            
            # Step 1: Restore backup file
            if backup_path.exists():
                shutil.copy2(backup_path, self.json_file_path)
                rollback_result["backup_restored"] = True
                logger.info(f"Restored backup to {self.json_file_path}")
            else:
                rollback_result["errors"].append(f"Backup file not found: {backup_path}")
            
            # Step 2: Clean up database entries
            try:
                for guild_id in guild_ids:
                    # Clear blacklists
                    await self.guild_blacklist_manager.clear_blacklist(guild_id)
                    
                    # Remove guild configuration
                    await self.guild_config_manager.delete_guild_config(guild_id)
                
                rollback_result["database_cleaned"] = True
                logger.info("Database cleanup completed")
                
            except Exception as e:
                error_msg = f"Database cleanup failed: {str(e)}"
                rollback_result["errors"].append(error_msg)
                logger.error(error_msg)
            
            rollback_result["success"] = rollback_result["backup_restored"] and rollback_result["database_cleaned"]
            
        except Exception as e:
            error_msg = f"Rollback failed: {str(e)}"
            rollback_result["errors"].append(error_msg)
            logger.error(error_msg)
        
        return rollback_result
    
    async def _load_json_data(self) -> Optional[Dict[str, Any]]:
        """Load and parse JSON data from file."""
        try:
            if not self.json_file_path.exists():
                logger.warning(f"JSON file not found: {self.json_file_path}")
                return None
            
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            logger.info(f"Loaded JSON data from {self.json_file_path}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON format in {self.json_file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load JSON data: {e}")
            return None
    
    async def _validate_json_structure(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON data structure.
        
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check required keys
        required_keys = ["unicode_emojis", "custom_emoji_ids", "custom_emoji_names"]
        for key in required_keys:
            if key not in data:
                validation_result["errors"].append(f"Missing required key: {key}")
                validation_result["valid"] = False
        
        if not validation_result["valid"]:
            return validation_result
        
        # Validate data types
        if not isinstance(data["unicode_emojis"], list):
            validation_result["errors"].append("unicode_emojis must be a list")
            validation_result["valid"] = False
        
        if not isinstance(data["custom_emoji_ids"], list):
            validation_result["errors"].append("custom_emoji_ids must be a list")
            validation_result["valid"] = False
        
        if not isinstance(data["custom_emoji_names"], dict):
            validation_result["errors"].append("custom_emoji_names must be a dictionary")
            validation_result["valid"] = False
        
        # Check for empty data
        total_emojis = len(data.get("unicode_emojis", [])) + len(data.get("custom_emoji_ids", []))
        if total_emojis == 0:
            validation_result["warnings"].append("No emoji data found in JSON file")
        
        return validation_result
    
    async def _migrate_blacklist_data(self, guild_id: int, json_data: Dict[str, Any]) -> None:
        """Migrate blacklist data from JSON to database for a specific guild."""
        unicode_emojis = set(json_data.get("unicode_emojis", []))
        custom_emoji_ids = set(json_data.get("custom_emoji_ids", []))
        custom_emoji_names = json_data.get("custom_emoji_names", {})
        
        # Convert custom emoji IDs to integers if they're strings
        custom_emoji_ids = {int(emoji_id) if isinstance(emoji_id, str) else emoji_id for emoji_id in custom_emoji_ids}
        
        # Convert custom emoji names keys to integers
        custom_emoji_names = {
            int(k) if isinstance(k, str) else k: v 
            for k, v in custom_emoji_names.items()
        }
        
        await self.guild_blacklist_manager.migrate_from_global_blacklist(
            guild_id, unicode_emojis, custom_emoji_ids, custom_emoji_names
        )
    
    async def _validate_emoji_data(self, guild_id: int, original_data: Dict[str, Any]) -> bool:
        """Validate that emoji data was migrated correctly."""
        try:
            blacklisted = await self.guild_blacklist_manager.get_all_blacklisted(guild_id)
            
            # Create sets for comparison
            migrated_unicode = {item['emoji_value'] for item in blacklisted if item['emoji_type'] == 'unicode'}
            migrated_custom = {item['emoji_value'] for item in blacklisted if item['emoji_type'] == 'custom'}
            
            original_unicode = set(original_data.get("unicode_emojis", []))
            original_custom = {str(emoji_id) for emoji_id in original_data.get("custom_emoji_ids", [])}
            
            # Compare sets
            if migrated_unicode != original_unicode:
                logger.error(f"Unicode emoji mismatch: {migrated_unicode} != {original_unicode}")
                return False
            
            if migrated_custom != original_custom:
                logger.error(f"Custom emoji mismatch: {migrated_custom} != {original_custom}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Emoji data validation failed: {e}")
            return False
    
    def get_migration_status(self) -> Dict[str, Any]:
        """
        Get current migration status information.
        
        Returns:
            Dictionary containing migration status
        """
        status = {
            "json_file_exists": self.json_file_path.exists(),
            "json_file_path": str(self.json_file_path),
            "backup_directory": str(self.backup_dir),
            "backup_directory_exists": self.backup_dir.exists(),
            "available_backups": []
        }
        
        # List available backups
        if self.backup_dir.exists():
            backup_files = list(self.backup_dir.glob("blacklist_backup_*.json"))
            status["available_backups"] = [
                {
                    "filename": backup.name,
                    "path": str(backup),
                    "created": datetime.fromtimestamp(backup.stat().st_mtime).isoformat(),
                    "size": backup.stat().st_size
                }
                for backup in sorted(backup_files, key=lambda x: x.stat().st_mtime, reverse=True)
            ]
        
        return status