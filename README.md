# Reacter

A Discord bot that automatically removes blacklisted emoji reactions and applies timeouts to users who use them. Features guild-specific configurations and database storage for scalable multi-server management.

## Features

- **Guild-specific configurations** - Each server has independent settings
- **Automatic reaction removal** for blacklisted emojis
- **User timeouts** with configurable duration per guild
- **Support for both Unicode and custom emojis**
- **SQLite database storage** with automatic migration from JSON
- **Optional DM notifications** to timed-out users
- **Comprehensive logging** with configurable log channels
- **Permission-based commands** using moderate_members instead of administrator

## Commands

### Blacklist Management
| Command | Permission | Description |
|---------|------------|-------------|
| ```!blacklist``` | Moderate Members | Show all blacklisted emojis for this server |
| ```!add_blacklist <emoji>``` | Moderate Members | Add emoji to this server's blacklist |
| ```!remove_blacklist <emoji>``` | Moderate Members | Remove emoji from this server's blacklist |
| ```!clear_blacklist``` | Moderate Members | Clear entire blacklist for this server (requires confirmation) |

### Guild Settings
| Command | Permission | Description |
|---------|------------|-------------|
| ```!settings``` | Administrator | Show current guild configuration |
| ```!set_timeout <duration>``` | Administrator | Set timeout duration (e.g., 5m, 300s, 1h30m) |
| ```!set_log_channel [#channel]``` | Administrator | Set or disable log channel |
| ```!set_dm_timeout <true/false>``` | Administrator | Enable/disable DM notifications |
| ```!reset_settings``` | Administrator | Reset all settings to defaults (requires confirmation) |

### Information & Debug
| Command | Permission | Description |
|---------|------------|-------------|
| ```!timeout_info``` | Moderate Members | Show timeout configuration for this server |
| ```!bot_perms``` | Moderate Members | Check bot permissions |
| ```!debug_blacklist``` | Moderate Members | Show raw blacklist contents |
| ```!test_emoji_check <emoji>``` | Moderate Members | Test if emoji is blacklisted |
| ```!test_reaction``` | Moderate Members | Test reaction detection |

## Prerequisites

- **Python 3.13+**
- **uv** package manager ([install here](https://docs.astral.sh/uv/getting-started/installation/))
- **Discord Bot Token** with the following:
  - **Bot Permissions**: View Channels, Moderate Members, Send Messages, Send Messages in Threads, Manage Messages, Manage Threads, Read Message History, Use External Emoji
  - **Privileged Intents**: Server Members Intent, Message Content Intent

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd reacter
   ```

2. **Install dependencies**
   ```bash
   uv sync
   ```

3. **Create environment file**
   ```bash
   touch .env
   ```

   Add your Discord bot token:
   ```env
   DISCORD_BOT_TOKEN=your_bot_token_here
   ```

4. **Configure Discord Bot**
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application and bot
   - Enable **Server Members Intent** and **Message Content Intent**
   - Invite bot with **Moderate Members** and **Manage Messages** permissions

5. **Run the bot**
   ```bash
   uv run main.py
   ```

The bot will automatically:
- Initialize the SQLite database
- Migrate existing JSON blacklists (if any)
- Create default configurations for each guild

## Docker Deployment

For production deployment, you can use Docker:

1. **Using Docker Compose (Recommended)**
   ```bash
   # Create data directories
   mkdir -p data logs
   
   # Build and run
   docker-compose up -d
   ```

2. **Using Docker directly**
   ```bash
   # Build the image
   docker build -t reacter .
   
   # Run the container
   docker run -d \
     --name reacter-bot \
     --restart unless-stopped \
     -e DISCORD_BOT_TOKEN=your_bot_token_here \
     -v $(pwd)/data:/app/data \
     -v $(pwd)/logs:/app/logs \
     reacter
   ```

3. **View logs**
   ```bash
   docker-compose logs -f reacter
   # or
   docker logs -f reacter-bot
   ```

The Docker setup includes:
- Persistent storage for database and logs
- Automatic restarts
- Health checks
- Resource limits
- Non-root user for security

## Configuration

All configuration is now managed per-guild using bot commands. The following environment variables are supported for backward compatibility:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| ```DISCORD_BOT_TOKEN``` | Required | Your Discord bot token |
| ```BLACKLIST_FILE``` | ```blacklist.json``` | Legacy blacklist file for migration |

Use the ```!settings``` command to configure each guild's specific settings including timeout duration, log channel, and DM preferences.

## Credits
Built with Claude Sonnet and Opus 4.0, Kiro.dev
