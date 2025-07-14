# Reacter

A Discord bot that automatically removes blacklisted emoji reactions and applies timeouts to users who use them.

## Features

- **Automatic reaction removal** for blacklisted emojis
- **User timeouts** with configurable duration
- **Support for both Unicode and custom emojis**
- **Persistent blacklist storage** (JSON file)
- **Optional DM notifications** to timed-out users
- **Comprehensive admin commands** for blacklist management

## Commands

| Command | Permission | Description |
|---------|------------|-------------|
| ```!blacklist``` | Administrator | Show all blacklisted emojis |
| ```!add_blacklist <emoji>``` | Administrator | Add emoji to blacklist |
| ```!remove_blacklist <emoji>``` | Administrator | Remove emoji from blacklist |
| ```!clear_blacklist``` | Administrator | Clear entire blacklist (requires confirmation) |
| ```!timeout_info``` | Moderate Members | Show timeout configuration |
| ```!bot_perms``` | Administrator | Check bot permissions |

### Debug Commands
- ```!debug_blacklist``` - Show raw blacklist contents
- ```!test_emoji_check <emoji>``` - Test if emoji is blacklisted
- ```!test_reaction``` - Test reaction detection

## Prerequisites

- **Python 3.8+**
- **uv** package manager ([install here](https://docs.astral.sh/uv/getting-started/installation/))
- **Discord Bot Token** with the following:
  - **Bot Permissions**: View Channels, Moderate Members, Send Messages, Send Messages in Threads, Manage Messages, Manage Threads, Read Message History, Use External Emoji
  - **Privileged Intents**: Server Members Intent, Message Content Intent

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd discord-emoji-blacklist-bot
   ```

2. **Install dependencies**
   ```bash
   uv add discord.py python-dotenv
   ```

3. **Create environment file**
   ```bash
   touch .env
   ```

   Edit ```.env``` with your configuration:
   ```env
   DISCORD_BOT_TOKEN=your_bot_token_here
   LOG_CHANNEL_ID=123456789012345678
   TIMEOUT_DURATION_SECONDS=300
   DM_ON_TIMEOUT=true
   BLACKLIST_FILE=blacklist.json
   ```

4. **Configure Discord Bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Enable **Server Members Intent** and **Message Content Intent**
   - Invite bot with required  permissions

5. **Run the bot**
   ```bash
   uv run bot.py
   ```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| ```DISCORD_BOT_TOKEN``` | Required | Your Discord bot token |
| ```LOG_CHANNEL_ID``` | ```0``` | Channel ID for logging actions |
| ```TIMEOUT_DURATION_SECONDS``` | ```300``` | Timeout duration in seconds |
| ```DM_ON_TIMEOUT``` | ```false``` | Send DM to timed-out users |
| ```BLACKLIST_FILE``` | ```blacklist.json``` | Blacklist storage file |

## Credits
Built with Claude Sonnet and Opus 4.0
