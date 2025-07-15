
import discord
from discord.ext import commands
from datetime import datetime, timedelta, timezone
import logging
import os
import json
from typing import Optional, Set, Dict, Union, List
from collections import defaultdict
import asyncio
import re
from dotenv import load_dotenv

# Import database managers
from database.manager import DatabaseManager
from database.guild_config_manager import GuildConfigManager
from database.guild_blacklist_manager import GuildBlacklistManager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('Reacter')

load_dotenv()

# Configuration from environment variables
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID', '0'))
TIMEOUT_DURATION = int(os.getenv('TIMEOUT_DURATION_SECONDS', '300'))
DM_ON_TIMEOUT = os.getenv('DM_ON_TIMEOUT', 'false').lower() == 'true'
BLACKLIST_FILE = os.getenv('BLACKLIST_FILE', 'blacklist.json')

# Default blacklisted emojis
DEFAULT_BLACKLIST = []

class EmojiBlacklist:
    """Manages both Unicode and custom emoji blacklisting."""

    def __init__(self):
        self.unicode_emojis: Set[str] = set()
        self.custom_emoji_ids: Set[int] = set()
        self.custom_emoji_names: Dict[int, str] = {}  # For display purposes

    def add_emoji(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> bool:
        """Add an emoji to the blacklist. Returns True if added, False if already exists."""
        if isinstance(emoji, str):
            # Unicode emoji
            if emoji not in self.unicode_emojis:
                self.unicode_emojis.add(emoji)
                return True
        elif hasattr(emoji, 'id') and emoji.id:
            # Custom emoji
            if emoji.id not in self.custom_emoji_ids:
                self.custom_emoji_ids.add(emoji.id)
                self.custom_emoji_names[emoji.id] = emoji.name
                return True
        return False

    def remove_emoji(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji, int]) -> bool:
        """Remove an emoji from the blacklist. Returns True if removed, False if not found."""
        if isinstance(emoji, str):
            # Unicode emoji
            if emoji in self.unicode_emojis:
                self.unicode_emojis.remove(emoji)
                return True
        elif isinstance(emoji, int):
            # Custom emoji by ID
            if emoji in self.custom_emoji_ids:
                self.custom_emoji_ids.remove(emoji)
                self.custom_emoji_names.pop(emoji, None)
                return True
        elif hasattr(emoji, 'id') and emoji.id:
            # Custom emoji object
            if emoji.id in self.custom_emoji_ids:
                self.custom_emoji_ids.remove(emoji.id)
                self.custom_emoji_names.pop(emoji.id, None)
                return True
        return False

    def is_blacklisted(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> bool:
        """Check if an emoji is blacklisted."""
        # Add debug logging
        logger.info(f"Checking emoji: {emoji}, type: {type(emoji)}")

        if isinstance(emoji, str):
            result = emoji in self.unicode_emojis
            logger.info(f"String emoji check: {result}")
            return result
        elif hasattr(emoji, 'id') and emoji.id is not None:
            # Custom emoji (has actual ID)
            result = emoji.id in self.custom_emoji_ids
            logger.info(f"Custom emoji check: {result}")
            return result
        elif hasattr(emoji, 'name'):
            # Unicode emoji as PartialEmoji (id is None)
            result = emoji.name in self.unicode_emojis
            logger.info(f"PartialEmoji name check: {result}")
            return result

        logger.info("No matching emoji type found")
        return False

    def get_emoji_display(self, emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> str:
        """Get a display string for an emoji."""
        if isinstance(emoji, str):
            return emoji
        elif hasattr(emoji, 'id') and emoji.id:
            if emoji.animated:
                return f"<a:{emoji.name}:{emoji.id}>"
            else:
                return f"<:{emoji.name}:{emoji.id}>"
        return str(emoji)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage."""
        return {
            'unicode_emojis': list(self.unicode_emojis),
            'custom_emoji_ids': list(self.custom_emoji_ids),
            'custom_emoji_names': self.custom_emoji_names
        }

    def from_dict(self, data: dict):
        """Load from dictionary."""
        self.unicode_emojis = set(data.get('unicode_emojis', []))
        self.custom_emoji_ids = set(data.get('custom_emoji_ids', []))
        self.custom_emoji_names = data.get('custom_emoji_names', {})
        # Convert string keys to int for custom_emoji_names
        self.custom_emoji_names = {int(k): v for k, v in self.custom_emoji_names.items()}

    def get_all_display(self) -> List[str]:
        """Get display strings for all blacklisted emojis."""
        displays = list(self.unicode_emojis)
        for emoji_id, emoji_name in self.custom_emoji_names.items():
            displays.append(f"<:{emoji_name}:{emoji_id}>")
        return displays

class Reacter(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(command_prefix='!', intents=intents)

        # Initialize database managers
        self.db_manager = DatabaseManager()
        self.guild_config_manager = GuildConfigManager(self.db_manager)
        self.guild_blacklist_manager = GuildBlacklistManager(self.db_manager)

        # Legacy blacklist for backward compatibility during migration
        self.emoji_blacklist = EmojiBlacklist()
        self.timeout_cooldowns: Dict[int, Dict[int, datetime]] = defaultdict(dict)
        self.load_blacklist()

    async def setup_hook(self):
        """Initialize database when bot starts."""
        await self.db_manager.initialize_database()
        logger.info("Database initialized successfully")

    def load_blacklist(self) -> None:
        """Load blacklist from file or use defaults."""
        try:
            if os.path.exists(BLACKLIST_FILE):
                with open(BLACKLIST_FILE, 'r') as f:
                    data = json.load(f)
                    if 'emojis' in data:
                        # Legacy format - convert to new format
                        for emoji in data['emojis']:
                            self.emoji_blacklist.add_emoji(emoji)
                        self.save_blacklist()
                    else:
                        # New format
                        self.emoji_blacklist.from_dict(data)
                logger.info(f"Loaded {len(self.emoji_blacklist.unicode_emojis)} Unicode and "
                          f"{len(self.emoji_blacklist.custom_emoji_ids)} custom blacklisted emojis")
            else:
                # Initialize with defaults
                for emoji in DEFAULT_BLACKLIST:
                    self.emoji_blacklist.add_emoji(emoji)
                self.save_blacklist()
                logger.info("Created new blacklist file with defaults")
        except Exception as e:
            logger.error(f"Failed to load blacklist: {e}")
            for emoji in DEFAULT_BLACKLIST:
                self.emoji_blacklist.add_emoji(emoji)

    def save_blacklist(self) -> None:
        """Save current blacklist to file."""
        try:
            with open(BLACKLIST_FILE, 'w') as f:
                json.dump(self.emoji_blacklist.to_dict(), f, indent=2)
            logger.info("Saved blacklist to file")
        except Exception as e:
            logger.error(f"Failed to save blacklist: {e}")

    async def check_timeout_cooldown(self, guild_id: int, user_id: int) -> bool:
        """Check if user is on timeout cooldown (prevents spam)."""
        guild_cooldowns = self.timeout_cooldowns[guild_id]
        if user_id in guild_cooldowns:
            last_timeout = guild_cooldowns[user_id]
            if datetime.now(timezone.utc) - last_timeout < timedelta(minutes=1):
                return False
        return True

    async def log_action(self, guild: discord.Guild, message: str) -> None:
        """Send a log message to the designated log channel."""
        if not LOG_CHANNEL_ID:
            return

        log_channel = guild.get_channel(LOG_CHANNEL_ID)
        if log_channel and isinstance(log_channel, discord.TextChannel):
            try:
                await log_channel.send(message)
            except discord.Forbidden:
                logger.warning(f"Cannot send to log channel in {guild.name}")
            except discord.HTTPException as e:
                logger.error(f"Failed to send log message: {e}")

bot = Reacter()

def parse_emoji(emoji_str: str) -> Optional[Union[str, int]]:
    """Parse an emoji string and return either the Unicode emoji or custom emoji ID."""
    # Check if it's a custom emoji format <:name:id> or <a:name:id>
    custom_emoji_pattern = r'<a?:(\w+):(\d+)>'
    match = re.match(custom_emoji_pattern, emoji_str)
    if match:
        return int(match.group(2))

    # Check if it's just an ID
    if emoji_str.isdigit():
        return int(emoji_str)

    # Otherwise treat as Unicode emoji
    return emoji_str

def get_emoji_display(emoji: Union[str, discord.Emoji, discord.PartialEmoji]) -> str:
    """Get a display string for an emoji."""
    if isinstance(emoji, str):
        return emoji
    elif hasattr(emoji, 'id') and emoji.id:
        if hasattr(emoji, 'animated') and emoji.animated:
            return f"<a:{emoji.name}:{emoji.id}>"
        else:
            return f"<:{emoji.name}:{emoji.id}>"
    elif hasattr(emoji, 'name'):
        return emoji.name
    return str(emoji)

async def log_guild_action(guild: discord.Guild, guild_config, message: str) -> None:
    """Send a log message to the guild's designated log channel."""
    if not guild_config.log_channel_id:
        return

    log_channel = guild.get_channel(guild_config.log_channel_id)
    if log_channel and isinstance(log_channel, discord.TextChannel):
        try:
            await log_channel.send(message)
        except discord.Forbidden:
            logger.warning(f"Cannot send to log channel in {guild.name}")
        except discord.HTTPException as e:
            logger.error(f"Failed to send log message: {e}")
    else:
        logger.warning(f"Log channel {guild_config.log_channel_id} not found or not accessible in {guild.name}")

@bot.event
async def on_ready():
    logger.info(f'Bot is ready. Logged in as {bot.user}')
    logger.info(f'Connected to {len(bot.guilds)} guilds')
    all_emojis = bot.emoji_blacklist.get_all_display()
    if all_emojis:
        logger.info(f'Blacklisted emojis: {", ".join(all_emojis[:10])}{"..." if len(all_emojis) > 10 else ""}')

@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    logger.info(f"Reaction detected: {payload.emoji} by user {payload.user_id}")

    # Ignore bot reactions
    if payload.user_id == bot.user.id:
        logger.info("Ignoring bot's own reaction")
        return

    # Ignore DMs
    if not payload.guild_id:
        logger.info("Ignoring DM reaction")
        return

    # Get guild
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        logger.warning(f"Guild {payload.guild_id} not found")
        return

    logger.info(f"Processing reaction in guild: {guild.name}")

    # Get guild configuration
    try:
        guild_config = await bot.guild_config_manager.get_guild_config(guild.id)
    except Exception as e:
        logger.error(f"Failed to get guild config for {guild.name}: {e}")
        return

    # Check if emoji is blacklisted using guild-specific blacklist
    try:
        is_blacklisted = await bot.guild_blacklist_manager.is_blacklisted(guild.id, payload.emoji)
    except Exception as e:
        logger.error(f"Failed to check blacklist for guild {guild.name}: {e}")
        return

    logger.info(f"Emoji {payload.emoji} blacklisted in guild {guild.name}: {is_blacklisted}")

    if not is_blacklisted:
        logger.info("Emoji not blacklisted, ignoring")
        return

    logger.info(f"Processing blacklisted emoji: {payload.emoji}")

    # Get member (with fallback to fetch)
    member = guild.get_member(payload.user_id)
    if not member:
        try:
            member = await guild.fetch_member(payload.user_id)
        except discord.NotFound:
            logger.warning(f"Member {payload.user_id} not found")
            return
        except discord.HTTPException as e:
            logger.error(f"Failed to fetch member: {e}")
            return

    # Skip if member is a bot or has manage messages permission
    if member.bot or member.guild_permissions.manage_messages:
        return

    # Get channel and message
    channel = guild.get_channel(payload.channel_id)
    if not channel or not isinstance(channel, discord.TextChannel):
        return

    # Check bot permissions
    bot_member = guild.me
    if not bot_member:
        return

    channel_perms = channel.permissions_for(bot_member)
    if not channel_perms.manage_messages:
        logger.warning(f"Missing manage_messages permission in {channel.name}")
        return

    if not guild.me.guild_permissions.moderate_members:
        logger.warning(f"Missing moderate_members permission in {guild.name}")
        return

    # Get emoji display string
    emoji_display = get_emoji_display(payload.emoji)

    # Remove reaction
    try:
        message = await channel.fetch_message(payload.message_id)
        await message.remove_reaction(payload.emoji, member)
        logger.info(f"Removed reaction {emoji_display} from {member} in {guild.name}")
    except discord.NotFound:
        return
    except discord.Forbidden:
        logger.error(f"Cannot remove reaction in {channel.name}")
        return
    except discord.HTTPException as e:
        logger.error(f"Failed to remove reaction: {e}")
        return

    # Check cooldown
    if not await bot.check_timeout_cooldown(guild.id, member.id):
        logger.info(f"Skipping timeout for {member} (cooldown active)")
        return

    # Apply timeout using guild-specific timeout duration
    try:
        timeout_duration = guild_config.timeout_duration
        timeout_until = discord.utils.utcnow() + timedelta(seconds=timeout_duration)
        await member.timeout(timeout_until, reason=f"Used blacklisted reaction: {emoji_display}")

        # Update cooldown
        bot.timeout_cooldowns[guild.id][member.id] = datetime.now(timezone.utc)

        # Log the action using guild-specific log channel
        log_message = (
            f"⚠️ **Timeout Applied**\n"
            f"**User:** {member.mention} ({member.name})\n"
            f"**Reaction:** {emoji_display}\n"
            f"**Channel:** {channel.mention}\n"
            f"**Duration:** {timeout_duration} seconds"
        )
        await log_guild_action(guild, guild_config, log_message)

        # Optional: DM the user using guild-specific setting
        if guild_config.dm_on_timeout:
            try:
                dm_message = (
                    f"You have been timed out in **{guild.name}** for {timeout_duration} seconds "
                    f"for using the blacklisted reaction: {emoji_display}"
                )
                await member.send(dm_message)
            except discord.Forbidden:
                logger.info(f"Cannot DM {member}")
            except discord.HTTPException:
                pass

        logger.info(f"Timed out {member} in {guild.name} for {timeout_duration}s")

    except discord.Forbidden:
        logger.error(f"Cannot timeout {member} in {guild.name} (missing permissions)")
    except discord.HTTPException as e:
        logger.error(f"Failed to timeout {member}: {e}")

# Admin commands
@bot.command(name='blacklist')
@commands.has_permissions(moderate_members=True)
async def blacklist_command(ctx: commands.Context):
    """Show current blacklisted emojis for this guild."""
    try:
        all_emojis = await bot.guild_blacklist_manager.get_blacklist_display(ctx.guild.id)

        if not all_emojis:
            await ctx.send("No emojis are currently blacklisted in this server.")
            return

        # Split into chunks if too many emojis
        chunks = []
        current_chunk = []
        current_length = 0

        for emoji in all_emojis:
            emoji_length = len(emoji) + 2  # +2 for comma and space
            if current_length + emoji_length > 1024:  # Discord embed field limit
                chunks.append(", ".join(current_chunk))
                current_chunk = [emoji]
                current_length = emoji_length
            else:
                current_chunk.append(emoji)
                current_length += emoji_length

        if current_chunk:
            chunks.append(", ".join(current_chunk))

        embed = discord.Embed(
            title=f"Blacklisted Emojis - {ctx.guild.name}",
            color=discord.Color.red()
        )

        for i, chunk in enumerate(chunks):
            field_name = "Emojis" if i == 0 else f"Emojis (cont. {i})"
            embed.add_field(name=field_name, value=chunk, inline=False)

        embed.set_footer(text=f"Total: {len(all_emojis)} emojis")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Failed to show blacklist for guild {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to retrieve blacklist. Please try again.")

@bot.command(name='add_blacklist', aliases=['blacklist_add'])
@commands.has_permissions(moderate_members=True)
async def add_blacklist(ctx: commands.Context, *, emoji_input: str):
    """Add an emoji to this guild's blacklist. Supports Unicode and custom emojis."""
    try:
        # Try to parse as custom emoji
        parsed = parse_emoji(emoji_input.strip())

        if isinstance(parsed, int):
            # Custom emoji ID - try to fetch it
            try:
                emoji = bot.get_emoji(parsed)
                if not emoji:
                    # Try to parse from the full custom emoji format
                    custom_match = re.match(r'<a?:(\w+):(\d+)>', emoji_input.strip())
                    if custom_match:
                        emoji = discord.PartialEmoji(
                            name=custom_match.group(1),
                            id=int(custom_match.group(2)),
                            animated=emoji_input.strip().startswith('<a:')
                        )
                    else:
                        await ctx.send("❌ Invalid custom emoji or emoji not found.")
                        return
            except (ValueError, AttributeError) as e:
                await ctx.send("❌ Invalid emoji format.")
                logger.error(f"Error parsing emoji: {e}")
                return
        else:
            # Unicode emoji
            emoji = parsed

        # Add to guild-specific blacklist
        if await bot.guild_blacklist_manager.add_emoji(ctx.guild.id, emoji):
            emoji_display = get_emoji_display(emoji)
            await ctx.send(f"✅ Added {emoji_display} to this server's blacklist.")
            logger.info(f"{ctx.author} added {emoji_display} to blacklist in {ctx.guild.name}")
        else:
            emoji_display = get_emoji_display(emoji)
            await ctx.send(f"{emoji_display} is already blacklisted in this server.")
            
    except Exception as e:
        logger.error(f"Failed to add emoji to blacklist for guild {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to add emoji to blacklist. Please try again.")

@bot.command(name='remove_blacklist', aliases=['blacklist_remove'])
@commands.has_permissions(moderate_members=True)
async def remove_blacklist(ctx: commands.Context, *, emoji_input: str):
    """Remove an emoji from this guild's blacklist."""
    try:
        # Try to parse as custom emoji
        parsed = parse_emoji(emoji_input.strip())

        if isinstance(parsed, int):
            # Custom emoji ID - get display name before removing
            blacklisted_emojis = await bot.guild_blacklist_manager.get_all_blacklisted(ctx.guild.id)
            emoji_name = None
            for emoji_data in blacklisted_emojis:
                if emoji_data['emoji_type'] == 'custom' and emoji_data['emoji_value'] == str(parsed):
                    emoji_name = emoji_data['emoji_name'] or f"ID: {parsed}"
                    break
            
            if not emoji_name:
                emoji_name = f"ID: {parsed}"

            if await bot.guild_blacklist_manager.remove_emoji(ctx.guild.id, parsed):
                await ctx.send(f"✅ Removed custom emoji ({emoji_name}) from this server's blacklist.")
                logger.info(f"{ctx.author} removed custom emoji {emoji_name} from blacklist in {ctx.guild.name}")
            else:
                await ctx.send(f"❌ Custom emoji with ID {parsed} is not blacklisted in this server.")
        else:
            # Unicode emoji
            if await bot.guild_blacklist_manager.remove_emoji(ctx.guild.id, parsed):
                await ctx.send(f"✅ Removed {parsed} from this server's blacklist.")
                logger.info(f"{ctx.author} removed {parsed} from blacklist in {ctx.guild.name}")
            else:
                await ctx.send(f"❌ {parsed} is not blacklisted in this server.")
                
    except Exception as e:
        logger.error(f"Failed to remove emoji from blacklist for guild {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to remove emoji from blacklist. Please try again.")

@bot.command(name='clear_blacklist')
@commands.has_permissions(moderate_members=True)
async def clear_blacklist(ctx: commands.Context):
    """Clear all blacklisted emojis for this guild (requires confirmation)."""
    await ctx.send("⚠️ Are you sure you want to clear ALL blacklisted emojis for this server? Type `yes` to confirm.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'

    try:
        await bot.wait_for('message', check=check, timeout=30.0)
        await bot.guild_blacklist_manager.clear_blacklist(ctx.guild.id)
        await ctx.send("✅ Cleared all blacklisted emojis for this server.")
        logger.info(f"{ctx.author} cleared emoji blacklist in {ctx.guild.name}")
    except asyncio.TimeoutError:
        await ctx.send("❌ Clear blacklist cancelled (timeout).")
    except Exception as e:
        logger.error(f"Failed to clear blacklist for guild {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to clear blacklist. Please try again.")

@bot.command(name='timeout_info')
@commands.has_permissions(moderate_members=True)
async def timeout_info(ctx: commands.Context):
    """Show timeout configuration for this guild."""
    try:
        # Get guild-specific configuration
        guild_config = await bot.guild_config_manager.get_guild_config(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"Timeout Configuration - {ctx.guild.name}",
            color=discord.Color.blue()
        )
        
        # Timeout Duration
        timeout_minutes = guild_config.timeout_duration // 60
        timeout_seconds = guild_config.timeout_duration % 60
        if timeout_minutes > 0:
            timeout_display = f"{timeout_minutes}m {timeout_seconds}s" if timeout_seconds > 0 else f"{timeout_minutes}m"
        else:
            timeout_display = f"{timeout_seconds}s"
        
        embed.add_field(
            name="Duration", 
            value=f"{timeout_display} ({guild_config.timeout_duration} seconds)", 
            inline=True
        )
        
        # DM on Timeout
        embed.add_field(
            name="DM on Timeout", 
            value="Yes" if guild_config.dm_on_timeout else "No", 
            inline=True
        )
        
        # Log Channel
        if guild_config.log_channel_id:
            log_channel = ctx.guild.get_channel(guild_config.log_channel_id)
            if log_channel:
                log_value = log_channel.mention
            else:
                log_value = f"Channel not found (ID: {guild_config.log_channel_id})"
        else:
            log_value = "Not set"
        
        embed.add_field(name="Log Channel", value=log_value, inline=True)

        # Get guild-specific blacklist count
        blacklisted_emojis = await bot.guild_blacklist_manager.get_all_blacklisted(ctx.guild.id)
        unicode_count = sum(1 for emoji in blacklisted_emojis if emoji['emoji_type'] == 'unicode')
        custom_count = sum(1 for emoji in blacklisted_emojis if emoji['emoji_type'] == 'custom')
        
        embed.add_field(
            name="Blacklisted Emojis",
            value=f"{unicode_count} Unicode, {custom_count} Custom",
            inline=True
        )

        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Failed to show timeout info for guild {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to retrieve timeout configuration. Please try again.")

@bot.command(name='debug_blacklist')
@commands.has_permissions(moderate_members=True)
async def debug_blacklist(ctx):
    """Debug blacklist contents"""
    unicode_emojis = list(bot.emoji_blacklist.unicode_emojis)
    custom_emojis = list(bot.emoji_blacklist.custom_emoji_ids)

    embed = discord.Embed(title="Blacklist Debug", color=discord.Color.orange())
    embed.add_field(
        name="Unicode Emojis (raw)",
        value=f"```{unicode_emojis}```" if unicode_emojis else "None",
        inline=False
    )
    embed.add_field(
        name="Unicode Emojis (repr)",
        value=f"```{[repr(e) for e in unicode_emojis]}```" if unicode_emojis else "None",
        inline=False
    )
    embed.add_field(
        name="Custom Emoji IDs",
        value=f"```{custom_emojis}```" if custom_emojis else "None",
        inline=False
    )

    await ctx.send(embed=embed)

@bot.command(name='test_emoji_check')
@commands.has_permissions(moderate_members=True)
async def test_emoji_check(ctx, *, emoji_input: str):
    """Test if a specific emoji is detected as blacklisted"""
    # Test both the input and when processed through Discord
    is_blacklisted_direct = bot.emoji_blacklist.is_blacklisted(emoji_input)

    await ctx.send(f"Direct check of '{emoji_input}': {is_blacklisted_direct}")
    await ctx.send(f"Emoji repr: `{repr(emoji_input)}`")
    await ctx.send(f"In unicode blacklist: {emoji_input in bot.emoji_blacklist.unicode_emojis}")

@bot.command(name='test_reaction')
@commands.has_permissions(moderate_members=True)
async def test_reaction(ctx):
    """Test if the bot can detect reactions"""
    msg = await ctx.send("React to this message with any emoji to test detection!")

    def check(payload):
        return payload.message_id == msg.id and payload.user_id != bot.user.id

    try:
        payload = await bot.wait_for('raw_reaction_add', check=check, timeout=30.0)
        await ctx.send(f"✅ Detected reaction: {payload.emoji} from <@{payload.user_id}>")
    except asyncio.TimeoutError:
        await ctx.send("❌ No reaction detected within 30 seconds")

@bot.command(name='bot_perms')
@commands.has_permissions(moderate_members=True)
async def check_bot_permissions(ctx):
    """Check bot permissions"""
    bot_member = ctx.guild.me
    perms = bot_member.guild_permissions

    embed = discord.Embed(title="Bot Permissions", color=discord.Color.blue())
    embed.add_field(name="Manage Messages", value="✅" if perms.manage_messages else "❌")
    embed.add_field(name="Moderate Members", value="✅" if perms.moderate_members else "❌")
    embed.add_field(name="Add Reactions", value="✅" if perms.add_reactions else "❌")
    embed.add_field(name="Read Message History", value="✅" if perms.read_message_history else "❌")

    await ctx.send(embed=embed)

# Guild settings management commands
@bot.command(name='settings', aliases=['config', 'guild_settings'])
@commands.has_permissions(administrator=True)
async def show_guild_settings(ctx: commands.Context):
    """Show current guild configuration settings."""
    try:
        guild_config = await bot.guild_config_manager.get_guild_config(ctx.guild.id)
        
        embed = discord.Embed(
            title=f"Guild Settings - {ctx.guild.name}",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        # Default values for comparison
        default_config = {
            'log_channel_id': None,
            'timeout_duration': 300,
            'dm_on_timeout': False
        }
        
        # Log Channel
        if guild_config.log_channel_id:
            log_channel = ctx.guild.get_channel(guild_config.log_channel_id)
            if log_channel:
                log_value = f"{log_channel.mention}"
                is_custom = guild_config.log_channel_id != default_config['log_channel_id']
            else:
                log_value = f"Channel not found (ID: {guild_config.log_channel_id})"
                is_custom = True
        else:
            log_value = "Not set"
            is_custom = guild_config.log_channel_id != default_config['log_channel_id']
        
        embed.add_field(
            name="🔗 Log Channel",
            value=f"{log_value} {'*(custom)*' if is_custom else '*(default)*'}",
            inline=False
        )
        
        # Timeout Duration
        timeout_minutes = guild_config.timeout_duration // 60
        timeout_seconds = guild_config.timeout_duration % 60
        if timeout_minutes > 0:
            timeout_display = f"{timeout_minutes}m {timeout_seconds}s" if timeout_seconds > 0 else f"{timeout_minutes}m"
        else:
            timeout_display = f"{timeout_seconds}s"
        
        is_timeout_custom = guild_config.timeout_duration != default_config['timeout_duration']
        embed.add_field(
            name="⏱️ Timeout Duration",
            value=f"{timeout_display} ({guild_config.timeout_duration}s) {'*(custom)*' if is_timeout_custom else '*(default)*'}",
            inline=True
        )
        
        # DM on Timeout
        is_dm_custom = guild_config.dm_on_timeout != default_config['dm_on_timeout']
        embed.add_field(
            name="📨 DM on Timeout",
            value=f"{'Enabled' if guild_config.dm_on_timeout else 'Disabled'} {'*(custom)*' if is_dm_custom else '*(default)*'}",
            inline=True
        )
        
        # Configuration timestamps
        if guild_config.created_at:
            embed.add_field(
                name="📅 Created",
                value=f"<t:{int(guild_config.created_at.timestamp())}:R>",
                inline=True
            )
        
        if guild_config.updated_at and guild_config.updated_at != guild_config.created_at:
            embed.add_field(
                name="🔄 Last Updated",
                value=f"<t:{int(guild_config.updated_at.timestamp())}:R>",
                inline=True
            )
        
        embed.set_footer(text="Use !set_timeout, !set_log_channel, or !set_dm_timeout to modify settings")
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Failed to show guild settings for {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to retrieve guild settings. Please try again.")

@bot.command(name='set_timeout', aliases=['timeout_duration'])
@commands.has_permissions(administrator=True)
async def set_timeout_duration(ctx: commands.Context, duration: str):
    """
    Set the timeout duration for emoji violations.
    
    Usage: !set_timeout <duration>
    Examples: !set_timeout 5m, !set_timeout 300s, !set_timeout 1h30m
    """
    try:
        # Parse duration string
        timeout_seconds = parse_duration(duration)
        
        if timeout_seconds < 0:
            await ctx.send("❌ Timeout duration cannot be negative.")
            return
        
        if timeout_seconds > 2419200:  # 28 days max
            await ctx.send("❌ Timeout duration cannot exceed 28 days (2,419,200 seconds).")
            return
        
        # Update guild configuration
        await bot.guild_config_manager.update_guild_config(
            ctx.guild.id,
            timeout_duration=timeout_seconds
        )
        
        # Format duration for display
        if timeout_seconds == 0:
            duration_display = "0 seconds (no timeout)"
        else:
            minutes = timeout_seconds // 60
            seconds = timeout_seconds % 60
            if minutes > 0:
                duration_display = f"{minutes}m {seconds}s" if seconds > 0 else f"{minutes}m"
            else:
                duration_display = f"{seconds}s"
        
        embed = discord.Embed(
            title="✅ Timeout Duration Updated",
            description=f"Timeout duration set to **{duration_display}** ({timeout_seconds} seconds)",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        logger.info(f"{ctx.author} updated timeout duration to {timeout_seconds}s in {ctx.guild.name}")
        
    except ValueError as e:
        await ctx.send(f"❌ Invalid duration format: {e}")
    except Exception as e:
        logger.error(f"Failed to set timeout duration in {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to update timeout duration. Please try again.")

@bot.command(name='set_log_channel', aliases=['log_channel'])
@commands.has_permissions(administrator=True)
async def set_log_channel(ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
    """
    Set the log channel for bot actions.
    
    Usage: !set_log_channel [#channel]
    Use without a channel to disable logging.
    """
    try:
        channel_id = channel.id if channel else None
        
        # Update guild configuration
        await bot.guild_config_manager.update_guild_config(
            ctx.guild.id,
            log_channel_id=channel_id
        )
        
        if channel:
            embed = discord.Embed(
                title="✅ Log Channel Updated",
                description=f"Log channel set to {channel.mention}",
                color=discord.Color.green()
            )
            logger.info(f"{ctx.author} set log channel to {channel.name} in {ctx.guild.name}")
        else:
            embed = discord.Embed(
                title="✅ Log Channel Disabled",
                description="Bot actions will no longer be logged",
                color=discord.Color.orange()
            )
            logger.info(f"{ctx.author} disabled log channel in {ctx.guild.name}")
        
        await ctx.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Failed to set log channel in {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to update log channel. Please try again.")

@bot.command(name='set_dm_timeout', aliases=['dm_timeout'])
@commands.has_permissions(administrator=True)
async def set_dm_timeout(ctx: commands.Context, enabled: str):
    """
    Enable or disable DM notifications when users are timed out.
    
    Usage: !set_dm_timeout <true/false|yes/no|on/off|enable/disable>
    """
    try:
        # Parse boolean input
        enabled_lower = enabled.lower()
        if enabled_lower in ['true', 'yes', 'on', 'enable', '1']:
            dm_enabled = True
        elif enabled_lower in ['false', 'no', 'off', 'disable', '0']:
            dm_enabled = False
        else:
            await ctx.send("❌ Invalid value. Use: true/false, yes/no, on/off, or enable/disable")
            return
        
        # Update guild configuration
        await bot.guild_config_manager.update_guild_config(
            ctx.guild.id,
            dm_on_timeout=dm_enabled
        )
        
        embed = discord.Embed(
            title="✅ DM Timeout Setting Updated",
            description=f"DM notifications on timeout: **{'Enabled' if dm_enabled else 'Disabled'}**",
            color=discord.Color.green()
        )
        
        await ctx.send(embed=embed)
        logger.info(f"{ctx.author} set DM timeout to {dm_enabled} in {ctx.guild.name}")
        
    except Exception as e:
        logger.error(f"Failed to set DM timeout setting in {ctx.guild.name}: {e}")
        await ctx.send("❌ Failed to update DM timeout setting. Please try again.")

@bot.command(name='reset_settings', aliases=['reset_config'])
@commands.has_permissions(administrator=True)
async def reset_guild_settings(ctx: commands.Context):
    """Reset all guild settings to default values (requires confirmation)."""
    embed = discord.Embed(
        title="⚠️ Reset Guild Settings",
        description="Are you sure you want to reset ALL guild settings to default values?\n\n"
                   "This will reset:\n"
                   "• Log channel (disabled)\n"
                   "• Timeout duration (5 minutes)\n"
                   "• DM on timeout (disabled)\n\n"
                   "Type `yes` to confirm or `no` to cancel.",
        color=discord.Color.orange()
    )
    
    await ctx.send(embed=embed)
    
    def check(m):
        return (m.author == ctx.author and 
                m.channel == ctx.channel and 
                m.content.lower() in ['yes', 'no'])
    
    try:
        response = await bot.wait_for('message', check=check, timeout=30.0)
        
        if response.content.lower() == 'yes':
            # Reset to default values
            await bot.guild_config_manager.update_guild_config(
                ctx.guild.id,
                log_channel_id=None,
                timeout_duration=300,
                dm_on_timeout=False
            )
            
            embed = discord.Embed(
                title="✅ Settings Reset",
                description="All guild settings have been reset to default values.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            logger.info(f"{ctx.author} reset guild settings in {ctx.guild.name}")
        else:
            embed = discord.Embed(
                title="❌ Reset Cancelled",
                description="Guild settings were not changed.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            
    except asyncio.TimeoutError:
        embed = discord.Embed(
            title="❌ Reset Cancelled",
            description="No response received within 30 seconds. Settings were not changed.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

def parse_duration(duration_str: str) -> int:
    """
    Parse a duration string into seconds.
    
    Supports formats like: 5m, 300s, 1h30m, 2h, 1d, etc.
    
    Args:
        duration_str: Duration string to parse
        
    Returns:
        Duration in seconds
        
    Raises:
        ValueError: If the duration format is invalid
    """
    duration_str = duration_str.lower().strip()
    
    # Handle pure numbers (assume seconds)
    if duration_str.isdigit():
        return int(duration_str)
    
    # Parse complex duration strings
    import re
    
    # Pattern to match number + unit combinations
    pattern = r'(\d+)([smhd])'
    matches = re.findall(pattern, duration_str)
    
    if not matches:
        raise ValueError("Invalid duration format. Use formats like: 5m, 300s, 1h30m, 2d")
    
    total_seconds = 0
    units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
    
    for value, unit in matches:
        if unit not in units:
            raise ValueError(f"Invalid time unit: {unit}. Use s, m, h, or d")
        total_seconds += int(value) * units[unit]
    
    return total_seconds

# Error handlers
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    elif isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    else:
        logger.error(f"Command error: {error}")
        await ctx.send("❌ An error occurred while processing the command.")

# Startup
if __name__ == "__main__":
    if not TOKEN:
        logger.error("DISCORD_BOT_TOKEN environment variable not set!")
        exit(1)

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        logger.error("Invalid bot token!")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
