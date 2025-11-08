"""
Enhanced Instagram Monitor Discord Bot with improved API handling and features
"""
import asyncio
import logging
import random
import time
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands

from config import Config
from api_client import APIClient
from enhanced_database import EnhancedDatabaseManager
from enhanced_monitor import EnhancedInstagramMonitor

# Configure enhanced logging
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format=Config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(Config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize components
db = EnhancedDatabaseManager()
monitor = EnhancedInstagramMonitor(db)

# Discord bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=Config.DISCORD_COMMAND_PREFIXES, intents=intents)

def is_discord_owner(user_id: int) -> bool:
    """Check if user is the bot owner"""
    return user_id == Config.DISCORD_OWNER_ID

def is_discord_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot"""
    return db.is_user_authorized(user_id)

@bot.event
async def on_ready():
    """Bot ready event"""
    logger.info(f"✅ Enhanced Discord bot logged in as {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")
    logger.info(f"Guilds: {len(bot.guilds)}")
    
    # Update user last used time
    db.update_user_last_used(Config.DISCORD_OWNER_ID)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler"""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    
    logger.error(f"Command error in {ctx.command}: {error}")
    
    embed = discord.Embed(
        title="❌ Command Error",
        description=f"An error occurred: {str(error)}",
        color=0xFF0000
    )
    await ctx.send(embed=embed, ephemeral=True)

# Enhanced proxy management commands
@bot.command(name='addproxy')
async def add_proxy_command(ctx, *, proxy_url: str = None):
    """Add a proxy to the rotation"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not proxy_url:
        embed = discord.Embed(
            title="❌ Usage Error",
            description="**Usage:** `/addproxy <proxy_url>`\n\n**Examples:**\n• `http://123.456.789.0:8080`\n• `http://user:pass@123.456.789.1:3128`\n• `socks5://user:pass@123.456.789.2:1080`",
            color=0xFF0000
        )
        await ctx.send(embed=embed, ephemeral=True)
        return

    if monitor.proxy_manager.add_proxy(proxy_url):
        embed = discord.Embed(
            title="✅ Proxy Added",
            description=f"Successfully added proxy: `{proxy_url}`",
            color=0x00FF7F
        )
        embed.add_field(name="Total Proxies", value=f"{len(monitor.proxy_manager.proxies)}", inline=True)
        embed.add_field(name="Active Proxies", value=f"{len(monitor.proxy_manager.proxies) - len(monitor.proxy_manager.failed_proxies)}", inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"⚠️ Proxy `{proxy_url}` already exists.", ephemeral=True)

@bot.command(name='removeproxy')
async def remove_proxy_command(ctx, *, proxy_url: str = None):
    """Remove a proxy from the rotation"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not proxy_url:
        await ctx.send("❌ **Usage:** `/removeproxy <proxy_url>`", ephemeral=True)
        return

    if monitor.proxy_manager.remove_proxy(proxy_url):
        embed = discord.Embed(
            title="🗑️ Proxy Removed",
            description=f"Successfully removed proxy: `{proxy_url}`",
            color=0xFF6347
        )
        embed.add_field(name="Total Proxies", value=f"{len(monitor.proxy_manager.proxies)}", inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ Proxy `{proxy_url}` not found.", ephemeral=True)

@bot.command(name='listproxies')
async def list_proxies_command(ctx):
    """List all proxies with statistics"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    proxies = monitor.proxy_manager.list_proxies()
    
    if not proxies:
        embed = discord.Embed(
            title="📋 Proxy List",
            description="No proxies configured.",
            color=0x808080
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(title="📋 Proxy Statistics", color=0x00AAFF)
    
    active_proxies = [p for p in proxies if p['status'] == 'Active']
    failed_proxies = [p for p in proxies if p['status'] == 'Failed']
    
    if active_proxies:
        active_list = []
        for p in active_proxies[:10]:  # Limit to 10 for display
            success_rate = f"{p['success_rate']:.1f}%"
            response_time = f"{p['avg_response_time']:.2f}s"
            active_list.append(f"🟢 `{p['proxy']}` - {success_rate} - {response_time}")
        
        if len(active_proxies) > 10:
            active_list.append(f"... and {len(active_proxies) - 10} more")
        
        embed.add_field(name=f"Active Proxies ({len(active_proxies)})", value="\n".join(active_list), inline=False)
    
    if failed_proxies:
        failed_list = []
        for p in failed_proxies[:5]:  # Limit to 5 for display
            failed_list.append(f"🔴 `{p['proxy']}` - {p['success_rate']:.1f}%")
        
        if len(failed_proxies) > 5:
            failed_list.append(f"... and {len(failed_proxies) - 5} more")
        
        embed.add_field(name=f"Failed Proxies ({len(failed_proxies)})", value="\n".join(failed_list), inline=False)

    embed.set_footer(text=f"Total: {len(proxies)} proxies")
    await ctx.send(embed=embed)

@bot.command(name='testproxy')
async def test_proxy_command(ctx, *, proxy_url: str = None):
    """Test a proxy connection"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not proxy_url:
        await ctx.send("❌ **Usage:** `/testproxy <proxy_url>`", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 Testing Proxy",
        description=f"Testing proxy: `{proxy_url}`",
        color=0x4169E1
    )
    loading_msg = await ctx.send(embed=embed)

    # Test the proxy
    async with APIClient() as api_client:
        response = await api_client.test_proxy(proxy_url)
        
        if response.success:
            embed = discord.Embed(
                title="✅ Proxy Test Successful",
                color=0x00FF7F
            )
            embed.add_field(name="Proxy", value=f"`{proxy_url}`", inline=False)
            embed.add_field(name="Response Time", value=f"{response.response_time:.2f}s", inline=True)
            embed.add_field(name="External IP", value=f"`{response.data.get('external_ip', 'Unknown')}`", inline=True)
            embed.add_field(name="Status", value="🟢 Working", inline=True)
        else:
            embed = discord.Embed(
                title="❌ Proxy Test Failed",
                description=response.error or "Unknown error",
                color=0xFF0000
            )
            embed.add_field(name="Proxy", value=f"`{proxy_url}`", inline=False)

    await loading_msg.edit(embed=embed)

# Enhanced monitoring commands
@bot.command(name='ban')
async def ban_monitor_command(ctx, username: str = None):
    """Monitor an account for ban detection"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not username:
        await ctx.send("❌ **Usage:** `/ban <username>` or `.ban <username>`", ephemeral=True)
        return

    username = username.strip().replace('@', '')
    
    if username in monitor.monitoring_tasks:
        await ctx.send(f"⚠️ **Already monitoring @{username}**", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 Checking Account Status",
        description=f"Verifying current status of **@{username}**",
        color=0x4169E1
    )
    loading_msg = await ctx.send(embed=embed)

    # Check current account status
    async with APIClient() as api_client:
        user_data_response = await api_client.get_instagram_profile(username)
        current_status = user_data_response.data.get('st')

    if current_status == 'not_found':
        error_embed = discord.Embed(
            title="❌ Account Already Banned",
            description=f"**@{username}** is already banned/suspended!\nUse `/unban {username}` to monitor for recovery instead.",
            color=0xFF0000
        )
        await loading_msg.edit(embed=error_embed)
        return
    elif current_status != 'ok':
        error_embed = discord.Embed(
            title="❌ Cannot Monitor Account",
            description=f"**@{username}**: {user_data_response.error or 'Unknown error'}",
            color=0xFF6347
        )
        await loading_msg.edit(embed=error_embed)
        return

    embed = discord.Embed(
        title="🔍 Initializing Enhanced Monitor",
        description=f"Account is active - adding **@{username}** to monitoring queue",
        color=0x4169E1
    )
    await loading_msg.edit(embed=embed)

    async def send_func(embed=None, message=None):
        if embed:
            await ctx.send(embed=embed)
        else:
            await ctx.send(message)

    success = await monitor.start_monitoring(username, 'ban', send_func, current_status, ctx.author.id)

    if success:
        success_embed = discord.Embed(
            title="🟢 Enhanced Monitor Active",
            description=f"Now monitoring **@{username}** for bans\n⚡ Enhanced sequential monitoring with better error handling",
            color=0x00FF7F
        )
        success_embed.add_field(name="Queue Position", value=f"{len(monitor.monitor_queue)}", inline=True)
        success_embed.add_field(name="Total Monitoring", value=f"{len(monitor.monitoring_tasks)}", inline=True)
        success_embed.add_field(name="Proxy Count", value=f"{len(monitor.proxy_manager.proxies)}", inline=True)
        await loading_msg.edit(embed=success_embed)
    else:
        await loading_msg.edit(embed=discord.Embed(
            title="❌ Failed to Start Monitoring",
            description="Could not start monitoring session",
            color=0xFF0000
        ))

@bot.command(name='unban')
async def unban_monitor_command(ctx, username: str = None):
    """Monitor an account for unban detection"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not username:
        await ctx.send("❌ **Usage:** `/unban <username>` or `.unban <username>`", ephemeral=True)
        return

    username = username.strip().replace('@', '')
    
    if username in monitor.monitoring_tasks:
        await ctx.send(f"⚠️ **Already monitoring @{username}**", ephemeral=True)
        return

    embed = discord.Embed(
        title="🔍 Checking Account Status",
        description=f"Verifying current status of **@{username}**",
        color=0x4169E1
    )
    loading_msg = await ctx.send(embed=embed)

    # Check current account status
    async with APIClient() as api_client:
        user_data_response = await api_client.get_instagram_profile(username)
        current_status = user_data_response.data.get('st')

    if current_status == 'ok':
        error_embed = discord.Embed(
            title="❌ Account Already Active",
            description=f"**@{username}** is already active/unbanned!\nUse `/ban {username}` to monitor for bans instead.",
            color=0xFF0000
        )
        await loading_msg.edit(embed=error_embed)
        return
    elif current_status != 'not_found':
        error_embed = discord.Embed(
            title="❌ Cannot Monitor Account",
            description=f"**@{username}**: {user_data_response.error or 'Unknown error'}",
            color=0xFF6347
        )
        await loading_msg.edit(embed=error_embed)
        return

    embed = discord.Embed(
        title="🔍 Initializing Enhanced Monitor",
        description=f"Account is banned - adding **@{username}** to monitoring queue",
        color=0x4169E1
    )
    await loading_msg.edit(embed=embed)

    async def send_func(embed=None, message=None):
        if embed:
            await ctx.send(embed=embed)
        else:
            await ctx.send(message)

    success = await monitor.start_monitoring(username, 'unban', send_func, current_status, ctx.author.id)

    if success:
        success_embed = discord.Embed(
            title="🟢 Enhanced Monitor Active",
            description=f"Now monitoring **@{username}** for recovery\n⚡ Enhanced sequential monitoring with better error handling",
            color=0x00FF7F
        )
        success_embed.add_field(name="Queue Position", value=f"{len(monitor.monitor_queue)}", inline=True)
        success_embed.add_field(name="Total Monitoring", value=f"{len(monitor.monitoring_tasks)}", inline=True)
        success_embed.add_field(name="Proxy Count", value=f"{len(monitor.proxy_manager.proxies)}", inline=True)
        await loading_msg.edit(embed=success_embed)
    else:
        await loading_msg.edit(embed=discord.Embed(
            title="❌ Failed to Start Monitoring",
            description="Could not start monitoring session",
            color=0xFF0000
        ))

@bot.command(name='stop')
async def stop_monitor_command(ctx, username: str = None):
    """Stop monitoring an account or list active monitors"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if username:
        username = username.strip().replace('@', '')
        if monitor.stop_monitoring(username):
            embed = discord.Embed(
                title="⏹️ Monitor Stopped",
                description=f"Stopped monitoring **@{username}**",
                color=0xFF6347
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ **No active monitoring for @{username}**", ephemeral=True)
    else:
        active_monitors = list(monitor.monitoring_tasks.keys())
        if active_monitors:
            embed = discord.Embed(title="📊 Active Monitors", color=0x00AAFF)
            monitor_list = "\n".join([f"⚡ @{monitor_name}" for monitor_name in active_monitors])
            embed.add_field(name="Currently Monitoring:", value=monitor_list, inline=False)
            embed.add_field(name="Queue Size", value=f"{len(monitor.monitor_queue)}", inline=True)
            embed.add_field(name="Total Proxies", value=f"{len(monitor.proxy_manager.proxies)}", inline=True)
            embed.add_field(name="Active Proxies", value=f"{len(monitor.proxy_manager.proxies) - len(monitor.proxy_manager.failed_proxies)}", inline=True)
            await ctx.send(embed=embed)
        else:
            embed = discord.Embed(title="🔭 No Active Monitors", color=0x808080)
            await ctx.send(embed=embed)

@bot.command(name='insta')
async def insta_info_command(ctx, username: str = None):
    """Get instant Instagram profile information"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    if not username:
        await ctx.send("❌ **Usage:** `/insta <username>` or `.insta <username>`", ephemeral=True)
        return

    username = username.strip().replace('@', '')

    loading_embed = discord.Embed(
        title="🔍 Fetching Profile",
        description=f"Getting info for **@{username}**...",
        color=0x4169E1
    )
    loading_msg = await ctx.send(embed=loading_embed)

    # Try with proxy first, then without if it fails
    proxy_url = monitor.proxy_manager.get_next_proxy()
    
    async with APIClient() as api_client:
        user_data_response = await api_client.get_instagram_profile(username, proxy_url)
        
        if user_data_response.data.get('st') == 'proxy_error' and proxy_url:
            logger.info(f"Proxy failed for {username}, retrying without proxy")
            user_data_response = await api_client.get_instagram_profile(username)

    status = user_data_response.data.get('st')

    if status == 'ok':
        user_data = user_data_response.data
        embed = discord.Embed(
            title=f"📱 @{user_data.get('usr')}",
            color=0x8A2BE2,
            timestamp=datetime.now()
        )

        name = user_data.get('nm', 'N/A')
        if user_data.get('verified'): 
            name += " ✅"

        embed.add_field(name="👤 Full Name", value=name, inline=True)
        embed.add_field(name="🆔 User ID", value=f"`{user_data.get('id', 'N/A')}`", inline=True)
        embed.add_field(name="🎂 Account Age", value=monitor.calculate_account_age(user_data.get('id')), inline=True)
        embed.add_field(name="👥 Followers", value=f"{int(user_data.get('fw', '0')):,}" if user_data.get('fw', 'N/A').isdigit() else user_data.get('fw', 'N/A'), inline=True)
        embed.add_field(name="👤 Following", value=f"{int(user_data.get('fg', '0')):,}" if user_data.get('fg', 'N/A').isdigit() else user_data.get('fg', 'N/A'), inline=True)
        embed.add_field(name="📸 Posts", value=f"{int(user_data.get('ps', '0')):,}" if user_data.get('ps', 'N/A').isdigit() else user_data.get('ps', 'N/A'), inline=True)
        embed.add_field(name="🔓 Privacy", value="🔒 Private" if user_data.get('prv') else "🌍 Public", inline=True)
        embed.add_field(name="🔧 Method", value=f"{'Proxy' if proxy_url and user_data_response.data.get('st') != 'proxy_error' else 'Direct'}", inline=True)
        embed.add_field(name="⏰ Fetched", value=datetime.now().strftime('%H:%M:%S'), inline=True)

        embed.set_footer(text="Instagram Monitor • Enhanced API • Real-time Data", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Instagram_icon.png/600px-Instagram_icon.png")
        await loading_msg.edit(embed=embed)
    elif status == 'not_found':
        error_embed = discord.Embed(
            title="❌ Profile Not Found",
            description=f"**@{username}** not found or suspended",
            color=0xFF0000
        )
        await loading_msg.edit(embed=error_embed)
    else:
        error_embed = discord.Embed(
            title="⚠️ Error Occurred",
            description=user_data_response.error or 'Unknown error',
            color=0xFFA500
        )
        await loading_msg.edit(embed=error_embed)

# Enhanced user management commands
@bot.command(name='adduser')
async def add_user_command(ctx, user_id: int = None):
    """Add a user to the authorized list (owner only)"""
    if not is_discord_owner(ctx.author.id):
        await ctx.send("❌ Only the owner can add users.", ephemeral=True)
        return

    if not user_id:
        await ctx.send("❌ **Usage:** `/adduser <user_id>` or `.adduser <user_id>`", ephemeral=True)
        return

    try:
        if db.add_user(user_id, ctx.author.id):
            embed = discord.Embed(
                title="✅ User Authorized",
                description=f"User `{user_id}` can now use bot commands",
                color=0x00FF7F
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠️ User `{user_id}` is already authorized.", ephemeral=True)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}", ephemeral=True)

@bot.command(name='removeuser')
async def remove_user_command(ctx, user_id: int = None):
    """Remove a user from the authorized list (owner only)"""
    if not is_discord_owner(ctx.author.id):
        await ctx.send("❌ Only the owner can remove users.", ephemeral=True)
        return

    if not user_id:
        await ctx.send("❌ **Usage:** `/removeuser <user_id>` or `.removeuser <user_id>`", ephemeral=True)
        return

    try:
        if db.remove_user(user_id):
            embed = discord.Embed(
                title="🗑️ User Removed",
                description=f"User `{user_id}` has been removed from authorization",
                color=0xFF6347
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"⚠️ User `{user_id}` not found or cannot be removed (might be owner).", ephemeral=True)
    except Exception as e:
        await ctx.send(f"❌ Error: {e}", ephemeral=True)

@bot.command(name='listusers')
async def list_users_command(ctx):
    """List all authorized users (owner only)"""
    if not is_discord_owner(ctx.author.id):
        await ctx.send("❌ Only the owner can list users.", ephemeral=True)
        return

    users = db.list_users()
    
    if not users:
        embed = discord.Embed(
            title="👥 Authorized Users",
            description="No users found.",
            color=0x808080
        )
        await ctx.send(embed=embed)
        return

    embed = discord.Embed(title="👥 Authorized Users", color=0x00AAFF)
    
    user_list = []
    for user_id, added_by, added_at, last_used, is_active in users:
        owner_indicator = " 👑" if user_id == Config.DISCORD_OWNER_ID else ""
        status_indicator = " ✅" if is_active else " ❌"
        last_used_str = f" (Last used: {last_used.strftime('%Y-%m-%d %H:%M')})" if last_used else ""
        user_list.append(f"<@{user_id}>{owner_indicator}{status_indicator} (`{user_id}`){last_used_str}")
    
    # Split into chunks if too many users
    chunk_size = 10
    for i in range(0, len(user_list), chunk_size):
        chunk = user_list[i:i+chunk_size]
        field_name = "Users" if i == 0 else f"Users (continued)"
        embed.add_field(name=field_name, value="\n".join(chunk), inline=False)

    embed.set_footer(text=f"Total: {len(users)} authorized users")
    await ctx.send(embed=embed)

@bot.command(name='stats')
async def stats_command(ctx):
    """Show bot statistics"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    monitor_stats = monitor.get_monitoring_stats()
    db_stats = db.get_database_stats()
    
    embed = discord.Embed(
        title="📊 Bot Statistics",
        color=0x00AAFF,
        timestamp=datetime.now()
    )
    
    # Monitoring stats
    embed.add_field(
        name="🔍 Monitoring",
        value=f"Active: {monitor_stats['active_monitors']}\nQueue: {monitor_stats['queue_size']}\nBans Detected: {monitor_stats['bans_detected']}\nUnbans Detected: {monitor_stats['unbans_detected']}",
        inline=True
    )
    
    # API stats
    total_checks = monitor_stats['total_checks']
    success_rate = (monitor_stats['successful_checks'] / total_checks * 100) if total_checks > 0 else 0
    embed.add_field(
        name="🌐 API Performance",
        value=f"Total Checks: {total_checks:,}\nSuccess Rate: {success_rate:.1f}%\nProxy Errors: {monitor_stats['proxy_errors']}\nAPI Errors: {monitor_stats['api_errors']}",
        inline=True
    )
    
    # Proxy stats
    proxy_count = monitor_stats['proxy_count']
    active_proxies = proxy_count - monitor_stats['failed_proxies']
    embed.add_field(
        name="🔄 Proxies",
        value=f"Total: {proxy_count}\nActive: {active_proxies}\nFailed: {monitor_stats['failed_proxies']}",
        inline=True
    )
    
    # Database stats
    embed.add_field(
        name="💾 Database",
        value=f"Total Logs: {db_stats.total_logs:,}\nToday's Logs: {db_stats.logs_today:,}\nUsers: {db_stats.total_users}",
        inline=True
    )
    
    if db_stats.last_activity:
        embed.add_field(
            name="⏰ Last Activity",
            value=db_stats.last_activity.strftime('%Y-%m-%d %H:%M:%S'),
            inline=True
        )
    
    embed.set_footer(text="Enhanced Instagram Monitor Bot", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Instagram_icon.png/600px-Instagram_icon.png")
    await ctx.send(embed=embed)

@bot.command(name='commands')
async def list_commands(ctx):
    """Show all available commands"""
    if not is_discord_authorized(ctx.author.id):
        await ctx.send("❌ You are not authorized to use this bot.", ephemeral=True)
        return

    is_bot_owner = is_discord_owner(ctx.author.id)

    embed = discord.Embed(title="🤖 Enhanced Instagram Monitor Bot", color=0x8A2BE2)

    embed.add_field(
        name="📡 Enhanced Monitoring",
        value="• `/ban <username>` - Monitor for ban\n• `/unban <username>` - Monitor for recovery\n• `/stop <username>` - Stop monitor\n• `/stop` - List active monitors\n• `/stats` - Show bot statistics",
        inline=False
    )

    embed.add_field(
        name="🔍 Instant Info",
        value="• `/insta <username>` - Get profile info\n• `/commands` - Show commands",
        inline=False
    )

    embed.add_field(
        name="🌐 Enhanced Proxy Management",
        value="• `/addproxy <proxy_url>` - Add proxy\n• `/removeproxy <proxy_url>` - Remove proxy\n• `/listproxies` - List all proxies with stats\n• `/testproxy <proxy_url>` - Test proxy",
        inline=False
    )

    if is_bot_owner:
        embed.add_field(
            name="👑 Owner Commands",
            value="• `/adduser <user_id>` - Authorize user\n• `/removeuser <user_id>` - Remove user\n• `/listusers` - List authorized users",
            inline=False
        )

    embed.add_field(
        name="🔧 Enhanced Features",
        value=(
            "• Advanced error handling and retry logic\n"
            "• Proxy health monitoring and statistics\n"
            "• Enhanced logging and monitoring\n"
            "• Database connection pooling\n"
            "• Rate limiting and cooldown periods\n"
            f"• Official IG Graph API: {'ON' if Config.IG_GRAPH_API_ENABLED else 'OFF'} (falls back to legacy)\n"
            "• Real-time statistics and monitoring"
        ),
        inline=False
    )

    embed.set_footer(text="Enhanced Instagram monitoring with advanced features", icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Instagram_icon.png/600px-Instagram_icon.png")
    await ctx.send(embed=embed)

# Main function
async def main():
    """Main function to run the enhanced Discord bot"""
    logger.info("Starting Enhanced Instagram Monitor Bot...")
    
    try:
        await bot.start(Config.DISCORD_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to start Discord bot: {e}")
    finally:
        await monitor.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
