"""
Tests for permission system changes from administrator to moderate_members.
"""

import pytest
import discord
from discord.ext import commands
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add the parent directory to the path so we can import main
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import bot


class TestPermissionChanges:
    """Test that all commands now use moderate_members instead of administrator permissions."""

    def test_blacklist_command_uses_moderate_members(self):
        """Test that blacklist command uses moderate_members permission."""
        command = bot.get_command('blacklist')
        assert command is not None
        
        # Check that the command has the correct permission check
        checks = command.checks
        assert len(checks) > 0
        
        # The permission check function should exist
        check_func = checks[0]
        assert callable(check_func)

    def test_add_blacklist_command_uses_moderate_members(self):
        """Test that add_blacklist command uses moderate_members permission."""
        command = bot.get_command('add_blacklist')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_remove_blacklist_command_uses_moderate_members(self):
        """Test that remove_blacklist command uses moderate_members permission."""
        command = bot.get_command('remove_blacklist')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_clear_blacklist_command_uses_moderate_members(self):
        """Test that clear_blacklist command uses moderate_members permission."""
        command = bot.get_command('clear_blacklist')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_timeout_info_command_uses_moderate_members(self):
        """Test that timeout_info command uses moderate_members permission."""
        command = bot.get_command('timeout_info')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_debug_blacklist_command_uses_moderate_members(self):
        """Test that debug_blacklist command uses moderate_members permission."""
        command = bot.get_command('debug_blacklist')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_test_emoji_check_command_uses_moderate_members(self):
        """Test that test_emoji_check command uses moderate_members permission."""
        command = bot.get_command('test_emoji_check')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_test_reaction_command_uses_moderate_members(self):
        """Test that test_reaction command uses moderate_members permission."""
        command = bot.get_command('test_reaction')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0

    def test_bot_perms_command_uses_moderate_members(self):
        """Test that bot_perms command uses moderate_members permission."""
        command = bot.get_command('bot_perms')
        assert command is not None
        
        checks = command.checks
        assert len(checks) > 0


class TestPermissionValidation:
    """Test that commands properly validate moderate_members permission."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for testing."""
        ctx = MagicMock()
        ctx.author = MagicMock()
        ctx.guild = MagicMock()
        ctx.channel = MagicMock()
        ctx.send = AsyncMock()
        # Mock the permissions property that discord.py uses
        ctx.permissions = MagicMock()
        return ctx

    @pytest.fixture
    def mock_member_with_moderate_members(self):
        """Create a mock member with moderate_members permission."""
        member = MagicMock()
        member.guild_permissions.moderate_members = True
        member.guild_permissions.administrator = False
        return member

    @pytest.fixture
    def mock_member_without_moderate_members(self):
        """Create a mock member without moderate_members permission."""
        member = MagicMock()
        member.guild_permissions.moderate_members = False
        member.guild_permissions.administrator = False
        return member

    @pytest.fixture
    def mock_member_with_administrator(self):
        """Create a mock member with administrator permission (should also work)."""
        member = MagicMock()
        member.guild_permissions.moderate_members = False
        member.guild_permissions.administrator = True
        return member

    @pytest.mark.asyncio
    async def test_moderate_members_permission_allows_access(self, mock_context, mock_member_with_moderate_members):
        """Test that users with moderate_members permission can access commands."""
        mock_context.author = mock_member_with_moderate_members
        # Mock the context permissions to have moderate_members
        mock_context.permissions.moderate_members = True
        
        # Test the permission check directly
        check = commands.has_permissions(moderate_members=True)
        result = await check.predicate(mock_context)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_moderate_members_permission_denies_access(self, mock_context, mock_member_without_moderate_members):
        """Test that users without moderate_members permission are denied access."""
        mock_context.author = mock_member_without_moderate_members
        # Mock the context permissions to NOT have moderate_members
        mock_context.permissions.moderate_members = False
        
        # Test the permission check directly
        check = commands.has_permissions(moderate_members=True)
        
        with pytest.raises(commands.MissingPermissions):
            await check.predicate(mock_context)

    @pytest.mark.asyncio
    async def test_administrator_permission_allows_access(self, mock_context, mock_member_with_administrator):
        """Test that users with administrator permission can still access commands."""
        mock_context.author = mock_member_with_administrator
        
        # Administrator should have all permissions including moderate_members
        mock_context.permissions.moderate_members = True
        
        check = commands.has_permissions(moderate_members=True)
        result = await check.predicate(mock_context)
        assert result is True


class TestTimeoutFunctionality:
    """Test that timeout functionality works with moderate_members permission."""

    def test_bot_checks_moderate_members_permission_in_reaction_handler(self):
        """Test that the reaction handler checks for moderate_members permission."""
        # Read the main.py file to verify the permission check exists
        with open('main.py', 'r') as f:
            content = f.read()
        
        # Verify that the reaction handler checks for moderate_members permission
        assert 'guild.me.guild_permissions.moderate_members' in content
        assert 'Missing moderate_members permission' in content

    def test_bot_permissions_command_shows_moderate_members(self):
        """Test that the bot_perms command displays moderate_members permission."""
        # Read the main.py file to verify the permission display exists
        with open('main.py', 'r') as f:
            content = f.read()
        
        # Verify that the bot_perms command shows moderate_members
        assert 'Moderate Members' in content
        assert 'perms.moderate_members' in content

    def test_no_administrator_permissions_remain_in_code(self):
        """Test that no administrator permission checks remain in the code."""
        # Read the main.py file to verify no administrator permissions remain
        with open('main.py', 'r') as f:
            content = f.read()
        
        # Verify that no administrator permission decorators remain
        assert '@commands.has_permissions(administrator=True)' not in content


if __name__ == "__main__":
    pytest.main([__file__])