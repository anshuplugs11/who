"""
Enhanced Instagram Monitor with better error handling and monitoring capabilities
"""
import asyncio
import random
import logging
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
import time
import discord

from api_client import APIClient, APIResponse
from enhanced_database import EnhancedDatabaseManager
from config import Config

logger = logging.getLogger(__name__)

@dataclass
class MonitorData:
    """Data structure for monitoring information"""
    username: str
    monitor_type: str
    send_func: Callable
    start_time: datetime
    is_banned_state: bool
    check_count: int = 0
    last_known_data: Optional[Dict[str, Any]] = None
    session_id: int = 0
    consecutive_errors: int = 0
    last_check_time: Optional[datetime] = None

class EnhancedProxyManager:
    """Enhanced proxy manager with statistics and health monitoring"""
    
    def __init__(self, db_manager: EnhancedDatabaseManager):
        self.proxies = []
        self.current_proxy_index = 0
        self.failed_proxies = set()
        self.db_manager = db_manager
        self.proxy_stats = {}
        self._load_proxy_stats()
    
    def _load_proxy_stats(self):
        """Load proxy statistics from database"""
        try:
            stats = self.db_manager.get_proxy_stats()
            for stat in stats:
                self.proxy_stats[stat['proxy_url']] = stat
        except Exception as e:
            logger.error(f"Error loading proxy stats: {e}")
    
    def add_proxy(self, proxy_url: str) -> bool:
        """Add a proxy to the list"""
        if proxy_url not in self.proxies:
            self.proxies.append(proxy_url)
            self.proxy_stats[proxy_url] = {
                'success_count': 0,
                'failure_count': 0,
                'avg_response_time': 0.0,
                'is_active': True
            }
            return True
        return False
    
    def remove_proxy(self, proxy_url: str) -> bool:
        """Remove a proxy from the list"""
        if proxy_url in self.proxies:
            self.proxies.remove(proxy_url)
            if proxy_url in self.failed_proxies:
                self.failed_proxies.remove(proxy_url)
            if proxy_url in self.proxy_stats:
                del self.proxy_stats[proxy_url]
            return True
        return False
    
    def get_next_proxy(self) -> Optional[str]:
        """Get the next working proxy in rotation with health-based selection"""
        if not self.proxies:
            return None
        
        # Filter out failed proxies
        working_proxies = [p for p in self.proxies if p not in self.failed_proxies]
        if not working_proxies:
            # Reset failed proxies if all are failed
            self.failed_proxies.clear()
            working_proxies = self.proxies
        
        # Sort by success rate and response time
        def proxy_score(proxy):
            stats = self.proxy_stats.get(proxy, {})
            success_count = stats.get('success_count', 0)
            failure_count = stats.get('failure_count', 0)
            total_requests = success_count + failure_count
            
            if total_requests == 0:
                return 0.5  # Neutral score for untested proxies
            
            success_rate = success_count / total_requests
            avg_response_time = stats.get('avg_response_time', 1.0)
            
            # Higher score for better success rate and lower response time
            return success_rate - (avg_response_time / 10.0)
        
        working_proxies.sort(key=proxy_score, reverse=True)
        
        if self.current_proxy_index >= len(working_proxies):
            self.current_proxy_index = 0
        
        proxy = working_proxies[self.current_proxy_index]
        self.current_proxy_index += 1
        return proxy
    
    def mark_proxy_failed(self, proxy_url: str):
        """Mark a proxy as failed"""
        self.failed_proxies.add(proxy_url)
        self.db_manager.update_proxy_stats(proxy_url, False)
    
    def mark_proxy_success(self, proxy_url: str, response_time: float):
        """Mark a proxy as successful"""
        if proxy_url in self.failed_proxies:
            self.failed_proxies.remove(proxy_url)
        self.db_manager.update_proxy_stats(proxy_url, True, response_time)
    
    def list_proxies(self) -> List[Dict[str, Any]]:
        """List all proxies with their status and statistics"""
        result = []
        for proxy in self.proxies:
            stats = self.proxy_stats.get(proxy, {})
            is_failed = proxy in self.failed_proxies
            
            result.append({
                'proxy': proxy,
                'status': 'Failed' if is_failed else 'Active',
                'success_count': stats.get('success_count', 0),
                'failure_count': stats.get('failure_count', 0),
                'avg_response_time': stats.get('avg_response_time', 0.0),
                'success_rate': self._calculate_success_rate(stats)
            })
        
        return sorted(result, key=lambda x: x['success_rate'], reverse=True)
    
    def _calculate_success_rate(self, stats: Dict[str, Any]) -> float:
        """Calculate success rate for a proxy"""
        success_count = stats.get('success_count', 0)
        failure_count = stats.get('failure_count', 0)
        total = success_count + failure_count
        
        if total == 0:
            return 0.0
        
        return (success_count / total) * 100

class EnhancedInstagramMonitor:
    """Enhanced Instagram monitor with better error handling and statistics"""
    
    def __init__(self, db_manager: EnhancedDatabaseManager):
        self.monitoring_tasks = {}
        self.db_manager = db_manager
        self.proxy_manager = EnhancedProxyManager(db_manager)
        self.sequential_monitor_task = None
        self.monitor_queue = []
        self.is_sequential_running = False
        self.api_client = None
        self.stats = {
            'total_checks': 0,
            'successful_checks': 0,
            'failed_checks': 0,
            'bans_detected': 0,
            'unbans_detected': 0,
            'proxy_errors': 0,
            'api_errors': 0
        }
    
    async def _get_api_client(self) -> APIClient:
        """Get or create API client"""
        if self.api_client is None:
            self.api_client = APIClient()
            await self.api_client._create_session()
        return self.api_client
    
    async def _close_api_client(self):
        """Close API client"""
        if self.api_client:
            await self.api_client._close_session()
            self.api_client = None
    
    def calculate_account_age(self, user_id: str) -> str:
        """Calculate approximate account creation year based on user ID"""
        try:
            if not isinstance(user_id, (int, str)) or str(user_id) == 'N/A':
                return 'Unknown'

            user_id = int(str(user_id).replace(',', ''))

            ranges = [
                (1278889, 2010),
                (17750000, 2011),
                (279760000, 2012),
                (900990000, 2013),
                (1629010000, 2014),
                (2369359761, 2015),
                (4239516754, 2016),
                (6345108209, 2017),
                (10016232395, 2018),
                (27238602159, 2019),
                (43464475395, 2020),
                (50289297647, 2021),
                (57464707082, 2022),
                (63313426938, 2023),
                (70000000000, 2024)
            ]

            for upper, year in ranges:
                if user_id <= upper:
                    current_year = datetime.now().year
                    age = current_year - year
                    if age == 0:
                        return f"Created in {year}"
                    elif age == 1:
                        return f"1 year old ({year})"
                    else:
                        return f"{age} years old ({year})"

            return f"Created in 2024"
        except Exception:
            return 'Unknown'
    
    async def sequential_monitor_loop(self):
        """Enhanced sequential monitoring loop with better error handling"""
        logger.info("Starting enhanced sequential monitor loop")
        
        while self.is_sequential_running:
            try:
                if not self.monitor_queue:
                    await asyncio.sleep(30)
                    continue

                # Process each account in the queue
                for monitor_data in self.monitor_queue.copy():
                    try:
                        await self._process_monitor_data(monitor_data)
                    except Exception as e:
                        logger.error(f"Error processing monitor data for {monitor_data.username}: {e}")
                        monitor_data.consecutive_errors += 1
                        
                        # Remove from queue if too many consecutive errors
                        if monitor_data.consecutive_errors >= Config.MAX_CONSECUTIVE_ERRORS:
                            logger.warning(f"Removing {monitor_data.username} due to consecutive errors")
                            self.monitor_queue.remove(monitor_data)
                            if monitor_data.username in self.monitoring_tasks:
                                del self.monitoring_tasks[monitor_data.username]

                # Wait before next round of checks
                await asyncio.sleep(random.uniform(*Config.MONITOR_CHECK_INTERVAL))

            except Exception as e:
                logger.error(f"Sequential monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _process_monitor_data(self, monitor_data: MonitorData):
        """Process a single monitor data entry"""
        username = monitor_data.username
        monitor_type = monitor_data.type
        send_func = monitor_data.send_func
        start_time = monitor_data.start_time
        is_banned_state = monitor_data.is_banned_state
        check_count = monitor_data.check_count
        last_known_data = monitor_data.last_known_data

        # Get proxy for this check
        proxy_url = self.proxy_manager.get_next_proxy()
        
        # Check account status
        api_client = await self._get_api_client()
        user_data_response = await api_client.get_instagram_profile(username, proxy_url)
        
        # Update statistics
        self.stats['total_checks'] += 1
        if user_data_response.success:
            self.stats['successful_checks'] += 1
            if proxy_url:
                self.proxy_manager.mark_proxy_success(proxy_url, user_data_response.response_time)
        else:
            self.stats['failed_checks'] += 1
            if user_data_response.status_code == 403 and proxy_url:
                # Treat 403 via proxy as proxy failure and retry next loop
                self.stats['proxy_errors'] += 1
                self.proxy_manager.mark_proxy_failed(proxy_url)
            elif user_data_response.error and 'proxy' in (user_data_response.error or '').lower():
                self.stats['proxy_errors'] += 1
                if proxy_url:
                    self.proxy_manager.mark_proxy_failed(proxy_url)
            else:
                self.stats['api_errors'] += 1
        
        # Update check count
        monitor_data.check_count = check_count + 1
        monitor_data.last_check_time = datetime.now()
        
        # Log the event
        self.db_manager.log_event(
            username, f'{monitor_type}_check', 
            user_data_response.data.get('st', 'error'),
            user_data_response.data, proxy_url,
            user_data_response.response_time,
            user_data_response.error
        )
        
        # Update session check count
        if monitor_data.session_id:
            self.db_manager.update_session_check_count(monitor_data.session_id, monitor_data.check_count)
        
        # Handle proxy errors
        if (user_data_response.status_code == 403 or user_data_response.data.get('st') == 'proxy_error') and proxy_url:
            logger.warning(f"Proxy failed for {username}, trying without proxy")
            user_data_response = await api_client.get_instagram_profile(username)
            if user_data_response.success:
                self.stats['successful_checks'] += 1
                self.stats['proxy_errors'] -= 1  # Adjust count since we recovered

        # Store last known good data
        if user_data_response.data.get('st') == 'ok':
            monitor_data.last_known_data = user_data_response.data
            monitor_data.consecutive_errors = 0  # Reset error count on success

        current_status = user_data_response.data.get('st')
        currently_banned = (current_status == 'not_found')

        # State change detection
        if currently_banned and not is_banned_state:
            monitor_data.is_banned_state = True
            if monitor_type == 'ban':
                self.stats['bans_detected'] += 1
                detection_time = datetime.now()
                elapsed_time = detection_time - start_time
                await self.send_ban_alert(username, last_known_data or user_data_response.data, 
                                        send_func, monitor_data.check_count, elapsed_time, 
                                        start_time, detection_time)
                # Remove from queue
                self.monitor_queue.remove(monitor_data)
                if monitor_data.session_id:
                    self.db_manager.end_monitoring_session(monitor_data.session_id, 'completed')
                return

        elif not currently_banned and is_banned_state:
            monitor_data.is_banned_state = False
            if monitor_type == 'unban':
                self.stats['unbans_detected'] += 1
                detection_time = datetime.now()
                elapsed_time = detection_time - start_time
                await self.send_unban_alert(username, user_data_response.data, send_func, 
                                          monitor_data.check_count, elapsed_time, start_time, detection_time)
                # Remove from queue
                self.monitor_queue.remove(monitor_data)
                if monitor_data.session_id:
                    self.db_manager.end_monitoring_session(monitor_data.session_id, 'completed')
                return

        # Add delay between account checks to avoid API rate limiting
        await asyncio.sleep(random.uniform(*Config.MONITOR_ACCOUNT_DELAY))

    async def start_monitoring(self, username: str, monitor_type: str, send_func: Callable, 
                             current_status: str, user_id: int) -> bool:
        """Add account to sequential monitoring queue with enhanced tracking"""
        if not self.is_sequential_running:
            self.is_sequential_running = True
            self.sequential_monitor_task = asyncio.create_task(self.sequential_monitor_loop())

        # Start monitoring session in database
        session_id = self.db_manager.start_monitoring_session(username, monitor_type, user_id)
        
        monitor_data = MonitorData(
            username=username,
            monitor_type=monitor_type,
            send_func=send_func,
            start_time=datetime.now(),
            is_banned_state=(monitor_type == 'unban'),
            session_id=session_id
        )

        self.monitor_queue.append(monitor_data)
        self.monitoring_tasks[username] = monitor_data
        
        logger.info(f"Started monitoring {username} for {monitor_type} (session: {session_id})")
        return True

    def stop_monitoring(self, username: str) -> bool:
        """Remove account from monitoring queue"""
        if username in self.monitoring_tasks:
            monitor_data = self.monitoring_tasks[username]
            if monitor_data in self.monitor_queue:
                self.monitor_queue.remove(monitor_data)
            
            # End monitoring session
            if monitor_data.session_id:
                self.db_manager.end_monitoring_session(monitor_data.session_id, 'stopped')
            
            del self.monitoring_tasks[username]
            logger.info(f"Stopped monitoring {username}")
            return True
        return False

    async def send_ban_alert(self, username: str, user_data: dict, send_func: Callable, 
                           check_count: int, elapsed_time, start_time, detection_time):
        """Send enhanced ban alert with better formatting"""
        ban_gif = random.choice(Config.BAN_GIF_URLS)
        ban_message = random.choice(Config.BAN_MESSAGES)

        embed = discord.Embed(
            title="🚫 ACCOUNT TERMINATED",
            description=f"{ban_message}\n**@{username}** {random.choice(['💨', '💀', '⚡', '🌪️', '🔥'])}",
            color=0xFF0000,
            timestamp=datetime.now()
        )

        if user_data and user_data.get('st') == 'ok':
            name = user_data.get('nm', 'Unknown')
            if user_data.get('verified'): 
                name += " ✅"

            embed.add_field(name="👤 Profile Name", value=f"```{name}```", inline=True)
            embed.add_field(name="🆔 User ID", value=f"```{user_data.get('id', 'N/A')}```", inline=True)
            embed.add_field(name="🎂 Account Age", value=f"```{self.calculate_account_age(user_data.get('id'))}```", inline=True)

            followers = f"{int(user_data.get('fw', '0')):,}" if user_data.get('fw', 'N/A').isdigit() else user_data.get('fw', 'N/A')
            following = f"{int(user_data.get('fg', '0')):,}" if user_data.get('fg', 'N/A').isdigit() else user_data.get('fg', 'N/A')
            posts = f"{int(user_data.get('ps', '0')):,}" if user_data.get('ps', 'N/A').isdigit() else user_data.get('ps', 'N/A')

            embed.add_field(name="👥 Followers", value=f"```{followers}```", inline=True)
            embed.add_field(name="👤 Following", value=f"```{following}```", inline=True)
            embed.add_field(name="📸 Posts", value=f"```{posts}```", inline=True)

            privacy_emoji = "🔒" if user_data.get('prv') else "🌍"
            embed.add_field(name="🔓 Privacy", value=f"{privacy_emoji} {'Private' if user_data.get('prv') else 'Public'}", inline=True)

        total_seconds = int(elapsed_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed.add_field(name="⏱️ Execution Time", value=f"```{hours:02d}h {minutes:02d}m {seconds:02d}s```", inline=True)
        embed.add_field(name="🔍 API Calls", value=f"```{check_count:,}```", inline=True)

        embed.set_thumbnail(url="https://i.imgur.com/VRzJ6Ct.png")
        embed.set_image(url=ban_gif)
        embed.set_footer(
            text=f"Instagram Monitor • Enhanced Sequential • Terminated at {detection_time.strftime('%I:%M:%S %p')}", 
            icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Instagram_icon.png/600px-Instagram_icon.png"
        )

        await send_func(embed=embed)
        self.db_manager.log_event(username, 'banned', 'banned', user_data)

    async def send_unban_alert(self, username: str, user_data: dict, send_func: Callable, 
                             check_count: int, elapsed_time, start_time, detection_time):
        """Send enhanced unban alert with better formatting"""
        unban_gif = random.choice(Config.UNBAN_GIF_URLS)
        unban_message = random.choice(Config.UNBAN_MESSAGES)

        embed = discord.Embed(
            title="🌟 MIRACULOUS RECOVERY",
            description=f"{unban_message}\n**@{username}** {random.choice(['🎉', '✨', '🚀', '🌅', '🦅'])}",
            color=0x00FF00,
            timestamp=datetime.now()
        )

        if user_data and user_data.get('st') == 'ok':
            name = user_data.get('nm', 'Unknown')
            if user_data.get('verified'): 
                name += " ✅"

            embed.add_field(name="👤 Profile Name", value=f"```{name}```", inline=True)
            embed.add_field(name="🆔 User ID", value=f"```{user_data.get('id', 'N/A')}```", inline=True)
            embed.add_field(name="🎂 Account Age", value=f"```{self.calculate_account_age(user_data.get('id'))}```", inline=True)

            followers = f"{int(user_data.get('fw', '0')):,}" if user_data.get('fw', 'N/A').isdigit() else user_data.get('fw', 'N/A')
            following = f"{int(user_data.get('fg', '0')):,}" if user_data.get('fg', 'N/A').isdigit() else user_data.get('fg', 'N/A')
            posts = f"{int(user_data.get('ps', '0')):,}" if user_data.get('ps', 'N/A').isdigit() else user_data.get('ps', 'N/A')

            embed.add_field(name="👥 Followers", value=f"```{followers}```", inline=True)
            embed.add_field(name="👤 Following", value=f"```{following}```", inline=True)
            embed.add_field(name="📸 Posts", value=f"```{posts}```", inline=True)

            privacy_emoji = "🔒" if user_data.get('prv') else "🌍"
            embed.add_field(name="🔓 Privacy", value=f"{privacy_emoji} {'Private' if user_data.get('prv') else 'Public'}", inline=True)

        total_seconds = int(elapsed_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        embed.add_field(name="⏱️ Recovery Time", value=f"```{hours:02d}h {minutes:02d}m {seconds:02d}s```", inline=True)
        embed.add_field(name="🔍 API Calls", value=f"```{check_count:,}```", inline=True)

        embed.set_thumbnail(url="https://i.imgur.com/8YMvVvr.png")
        embed.set_image(url=unban_gif)
        embed.set_footer(
            text=f"Instagram Monitor • Enhanced Sequential • Recovered at {detection_time.strftime('%I:%M:%S %p')}", 
            icon_url="https://upload.wikimedia.org/wikipedia/commons/thumb/a/a5/Instagram_icon.png/600px-Instagram_icon.png"
        )

        await send_func(embed=embed)
        self.db_manager.log_event(username, 'unbanned', 'recovered', user_data)

    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics"""
        return {
            **self.stats,
            'active_monitors': len(self.monitoring_tasks),
            'queue_size': len(self.monitor_queue),
            'proxy_count': len(self.proxy_manager.proxies),
            'failed_proxies': len(self.proxy_manager.failed_proxies)
        }

    async def cleanup(self):
        """Cleanup resources"""
        self.is_sequential_running = False
        if self.sequential_monitor_task:
            self.sequential_monitor_task.cancel()
        await self._close_api_client()
        self.db_manager.close()
