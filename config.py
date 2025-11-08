"""
Configuration file for Instagram Monitor Bot
"""
import os
from typing import List, Dict, Any

class Config:
    """Configuration class for the Instagram Monitor Bot"""
    
    # Discord Configuration
    DISCORD_BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN', '')
    DISCORD_OWNER_ID = int(os.getenv('DISCORD_OWNER_ID', '1393139526154584166'))
    DISCORD_COMMAND_PREFIXES = ['/', '.']
    
    # API Configuration
    INSTAGRAM_API_URL = "http://54.242.82.67:5000/api/ig-profile.php"
    API_TIMEOUT = 15
    API_RETRY_ATTEMPTS = 3
    API_RETRY_DELAY = 2  # seconds
    API_RATE_LIMIT_DELAY = 1  # seconds between requests

    # Official Instagram Graph API (optional)
    IG_GRAPH_API_ENABLED = os.getenv('IG_GRAPH_API_ENABLED', 'false').lower() == 'true'
    IG_APP_ID = os.getenv('IG_APP_ID', '')
    IG_APP_SECRET = os.getenv('IG_APP_SECRET', '')
    IG_ACCESS_TOKEN = os.getenv('IG_ACCESS_TOKEN', '')  # Long-lived User Access Token tied to an Instagram Business/Creator account
    IG_BUSINESS_ACCOUNT_ID = os.getenv('IG_BUSINESS_ACCOUNT_ID', '')  # Connected Instagram Business/Creator user id for business_discovery
    IG_GRAPH_API_BASE = os.getenv('IG_GRAPH_API_BASE', 'https://graph.facebook.com/v18.0')
    IG_GRAPH_API_FIELDS = os.getenv('IG_GRAPH_API_FIELDS', 'id,username,name,followers_count,follows_count,media_count,account_type,profile_picture_url,is_verified').split(',')
    IG_GRAPH_API_RPM = int(os.getenv('IG_GRAPH_API_RPM', '30'))  # soft cap; respect FB rate limits
    
    # Database Configuration
    DATABASE_NAME = 'monitor_logs.db'
    DATABASE_TIMEOUT = 30
    
    # Monitoring Configuration
    MONITOR_CHECK_INTERVAL = (60, 120)  # Random range in seconds
    MONITOR_ACCOUNT_DELAY = (10, 20)    # Delay between account checks
    MAX_CONCURRENT_MONITORS = 50
    MONITOR_TIMEOUT = 300  # 5 minutes timeout for individual checks
    
    # Proxy Configuration
    PROXY_TIMEOUT = 10
    PROXY_TEST_URL = "https://httpbin.org/ip"
    MAX_PROXY_FAILURES = 3
    PROXY_RETRY_DELAY = 30  # seconds
    
    # Logging Configuration
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    LOG_FILE = 'bot.log'
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS_PER_MINUTE = int(os.getenv('RATE_LIMIT_REQUESTS_PER_MINUTE', '30'))
    RATE_LIMIT_BURST = 10
    
    # Error Handling
    MAX_CONSECUTIVE_ERRORS = 5
    ERROR_COOLDOWN = 300  # 5 minutes
    
    # GIF URLs for alerts
    BAN_GIF_URLS = [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMnBsZHZuMWZvYnFtN2kwaG9mNDB6ZXpvYWhrc20yempwNHpiZnpwYyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Sb7WSbjHFNIL6/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjgxdHp1ZTV4YmlrZWdpYndrYThiZzR3aDhqb3Q5bDV3aTNvM2lwaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/euMGM3uD3NHva/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjgxdHp1ZTV4YmlrZWdpYndrYThiZzR3aDhqb3Q5bDV3aTNvM2lwaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/Diym3aZO1dHzO/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjgxdHp1ZTV4YmlrZWdpYndrYThiZzR3aDhqb3Q5bDV3aTNvM2lwaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/UqhTuhIu2458Y/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjgxdHp1ZTV4YmlrZWdpYndrYThiZzR3aDhqb3Q5bDV3aTNvM2lwaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/5yBQraVyL7N28/giphy.gif",
    ]
    
    UNBAN_GIF_URLS = [
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ejM4eGVvMXQ5MGZpMG52NG8wNm1iZHhiY24zeDB3dDAzenh5ZXh0cSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/dpXcqV8htWx4A/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3ejM4eGVvMXQ5MGZpMG52NG8wNm1iZHhiY24zeDB3dDAzenh5ZXh0cSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/9jYtQ2fmBFYkM/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMjgxdHp1ZTV4YmlrZWdpYndrYThiZzR3aDhqb3Q5bDV3aTNvM2lwaSZlcD12MV9naWZzX3NlYXJjaCZjdD1n/CX4qeENSjFiKI/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3c3Q0YW16MmNzM3c0b2dwdXQybnZta3Jxc3NmdGdjNjNseHl4ZDRnNiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/La9mIgaoqh6q4/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3aG44ZTE1dGVpaW8zeHN2amZ1cmdxcXR3amFodWpvdWI4eXN5cHpzZiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/NpzbHKL0u04yk/giphy.gif",
        "https://media.giphy.com/media/v1.Y2lkPWVjZjA1ZTQ3aG44ZTE1dGVpaW8zeHN2amZ1cmdxcXR3amFodWpvdWI4eXN5cHpzZiZlcD12MV9naWZzX3NlYXJjaCZjdD1n/sUP52mudix9Zu/giphy.gif",
    ]
    
    # Fun ban/unban messages
    BAN_MESSAGES = [
        "💀 Account has vanished into the void!",
        "🚫 Another one bites the dust!",
        "⚡ Thanos snapped... and they're gone!",
        "🌪️ Swept away by the ban hammer!",
        "🔥 Account burned to ashes!",
        "❄️ Frozen in digital ice!",
        "🌙 Disappeared into the shadow realm!",
    ]
    
    UNBAN_MESSAGES = [
        "🎉 Back from the digital afterlife!",
        "🌅 Rising like a phoenix from the ashes!",
        "✨ Miraculous recovery detected!",
        "🎊 The prodigal account returns!",
        "🌟 Back and better than ever!",
        "🚀 Houston, we have liftoff!",
        "🦅 Soaring back to freedom!",
    ]
    
    # User Agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.63 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    ]
