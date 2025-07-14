
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('BlacklistBot')

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

class BlacklistBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.reactions = True
        intents.message_content = True
        intents.members = True
        intents.guilds = True

        super().__init__(command_prefix='!', intents=intents)

        self.emoji_blacklist = EmojiBlacklist()
        self.timeout_cooldowns: Dict[int, Dict[int, datetime]] = defaultdict(dict)
        self.load_blacklist()

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

bot = BlacklistBot()

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
    logger.info(f"Payload emoji type: {type(payload.emoji)}")
    logger.info(f"Payload emoji repr: {repr(payload.emoji)}")

    # Debug the blacklist contents
    logger.info(f"Unicode blacklist contents: {bot.emoji_blacklist.unicode_emojis}")
    logger.info(f"Custom emoji blacklist contents: {bot.emoji_blacklist.custom_emoji_ids}")

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

    # Check if emoji is blacklisted
    is_blacklisted = bot.emoji_blacklist.is_blacklisted(payload.emoji)
    logger.info(f"Emoji {payload.emoji} blacklisted: {is_blacklisted}")

    # Additional debug info
    if isinstance(payload.emoji, str):
        logger.info(f"Checking Unicode emoji: '{payload.emoji}' in {bot.emoji_blacklist.unicode_emojis}")
    elif hasattr(payload.emoji, 'id') and payload.emoji.id:
        logger.info(f"Checking custom emoji ID: {payload.emoji.id} in {bot.emoji_blacklist.custom_emoji_ids}")
    elif hasattr(payload.emoji, 'name'):
        logger.info(f"Checking PartialEmoji name: '{payload.emoji.name}' in {bot.emoji_blacklist.unicode_emojis}")

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
    emoji_display = bot.emoji_blacklist.get_emoji_display(payload.emoji)

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

    # Apply timeout
    try:
        timeout_until = discord.utils.utcnow() + timedelta(seconds=TIMEOUT_DURATION)
        await member.timeout(timeout_until, reason=f"Used blacklisted reaction: {emoji_display}")

        # Update cooldown
        bot.timeout_cooldowns[guild.id][member.id] = datetime.now(timezone.utc)

        # Log the action
        log_message = (
            f"⚠️ **Timeout Applied**\n"
            f"**User:** {member.mention} ({member.name})\n"
            f"**Reaction:** {emoji_display}\n"
            f"**Channel:** {channel.mention}\n"
            f"**Duration:** {TIMEOUT_DURATION} seconds"
        )
        await bot.log_action(guild, log_message)

        # Optional: DM the user
        if DM_ON_TIMEOUT:
            try:
                dm_message = (
                    f"You have been timed out in **{guild.name}** for {TIMEOUT_DURATION} seconds "
                    f"for using the blacklisted reaction: {emoji_display}"
                )
                await member.send(dm_message)
            except discord.Forbidden:
                logger.info(f"Cannot DM {member}")
            except discord.HTTPException:
                pass

        logger.info(f"Timed out {member} in {guild.name} for {TIMEOUT_DURATION}s")

    except discord.Forbidden:
        logger.error(f"Cannot timeout {member} in {guild.name} (missing permissions)")
    except discord.HTTPException as e:
        logger.error(f"Failed to timeout {member}: {e}")

# Admin commands
@bot.command(name='blacklist')
@commands.has_permissions(administrator=True)
async def blacklist_command(ctx: commands.Context):
    """Show current blacklisted emojis."""
    all_emojis = bot.emoji_blacklist.get_all_display()

    if not all_emojis:
        await ctx.send("No emojis are currently blacklisted.")
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
        title="Blacklisted Emojis",
        color=discord.Color.red()
    )

    for i, chunk in enumerate(chunks):
        field_name = "Emojis" if i == 0 else f"Emojis (cont. {i})"
        embed.add_field(name=field_name, value=chunk, inline=False)

    embed.set_footer(text=f"Total: {len(all_emojis)} emojis")
    await ctx.send(embed=embed)

@bot.command(name='add_blacklist', aliases=['blacklist_add'])
@commands.has_permissions(administrator=True)
async def add_blacklist(ctx: commands.Context, *, emoji_input: str):
    """Add an emoji to the blacklist. Supports Unicode and custom emojis."""
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

    if bot.emoji_blacklist.add_emoji(emoji):
        bot.save_blacklist()
        emoji_display = bot.emoji_blacklist.get_emoji_display(emoji)
        await ctx.send(f"✅ Added {emoji_display} to the blacklist.")
        logger.info(f"{ctx.author} added {emoji_display} to blacklist in {ctx.guild.name}")
    else:
        emoji_display = bot.emoji_blacklist.get_emoji_display(emoji)
        await ctx.send(f"{emoji_display} is already blacklisted.")

@bot.command(name='remove_blacklist', aliases=['blacklist_remove'])
@commands.has_permissions(administrator=True)
async def remove_blacklist(ctx: commands.Context, *, emoji_input: str):
    """Remove an emoji from the blacklist."""
    # Try to parse as custom emoji
    parsed = parse_emoji(emoji_input.strip())

    if isinstance(parsed, int):
        # Custom emoji ID
        # Get display name before removing
        emoji_name = bot.emoji_blacklist.custom_emoji_names.get(parsed, f"ID: {parsed}")

        if bot.emoji_blacklist.remove_emoji(parsed):
            bot.save_blacklist()
            await ctx.send(f"✅ Removed custom emoji ({emoji_name}) from the blacklist.")
            logger.info(f"{ctx.author} removed custom emoji {emoji_name} from blacklist in {ctx.guild.name}")
        else:
            await ctx.send(f"❌ Custom emoji with ID {parsed} is not blacklisted.")
    else:
        # Unicode emoji
        if bot.emoji_blacklist.remove_emoji(parsed):
            bot.save_blacklist()
            await ctx.send(f"✅ Removed {parsed} from the blacklist.")
            logger.info(f"{ctx.author} removed {parsed} from blacklist in {ctx.guild.name}")
        else:
            await ctx.send(f"❌ {parsed} is not blacklisted.")

@bot.command(name='clear_blacklist')
@commands.has_permissions(administrator=True)
async def clear_blacklist(ctx: commands.Context):
    """Clear all blacklisted emojis (requires confirmation)."""
    await ctx.send("⚠️ Are you sure you want to clear ALL blacklisted emojis? Type `yes` to confirm.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'

    try:
        await bot.wait_for('message', check=check, timeout=30.0)
        bot.emoji_blacklist = EmojiBlacklist()
        bot.save_blacklist()
        await ctx.send("✅ Cleared all blacklisted emojis.")
        logger.info(f"{ctx.author} cleared emoji blacklist in {ctx.guild.name}")
    except asyncio.TimeoutError:
        await ctx.send("❌ Clear blacklist cancelled (timeout).")

@bot.command(name='timeout_info')
@commands.has_permissions(moderate_members=True)
async def timeout_info(ctx: commands.Context):
    """Show timeout configuration."""
    embed = discord.Embed(
        title="Timeout Configuration",
        color=discord.Color.blue()
    )
    embed.add_field(name="Duration", value=f"{TIMEOUT_DURATION} seconds", inline=True)
    embed.add_field(name="DM on Timeout", value="Yes" if DM_ON_TIMEOUT else "No", inline=True)
    embed.add_field(name="Log Channel", value=f"<#{LOG_CHANNEL_ID}>" if LOG_CHANNEL_ID else "Not set", inline=True)

    unicode_count = len(bot.emoji_blacklist.unicode_emojis)
    custom_count = len(bot.emoji_blacklist.custom_emoji_ids)
    embed.add_field(
        name="Blacklisted Emojis",
        value=f"{unicode_count} Unicode, {custom_count} Custom",
        inline=True
    )

    await ctx.send(embed=embed)

@bot.command(name='debug_blacklist')
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
async def test_emoji_check(ctx, *, emoji_input: str):
    """Test if a specific emoji is detected as blacklisted"""
    # Test both the input and when processed through Discord
    is_blacklisted_direct = bot.emoji_blacklist.is_blacklisted(emoji_input)

    await ctx.send(f"Direct check of '{emoji_input}': {is_blacklisted_direct}")
    await ctx.send(f"Emoji repr: `{repr(emoji_input)}`")
    await ctx.send(f"In unicode blacklist: {emoji_input in bot.emoji_blacklist.unicode_emojis}")

@bot.command(name='test_reaction')
@commands.has_permissions(administrator=True)
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
@commands.has_permissions(administrator=True)
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
