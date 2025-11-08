"""
Enhanced API Client with improved error handling, rate limiting, and multiple URL support
"""
import asyncio
import aiohttp
import time
import random
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import json

from config import Config

logger = logging.getLogger(__name__)

@dataclass
class APIResponse:
    """Structured API response"""
    success: bool
    data: Dict[str, Any]
    status_code: int
    error: Optional[str] = None
    proxy_used: Optional[str] = None
    response_time: float = 0.0
    api_url: Optional[str] = None

class APIURLManager:
    """Manages multiple API URLs with health tracking and rotation"""
    
    def __init__(self, urls: List[str], strategy: str = 'health_based'):
        self.urls = urls if urls else [Config.INSTAGRAM_API_URL]
        self.strategy = strategy
        self.current_index = 0
        self.url_stats = {url: {
            'success_count': 0,
            'failure_count': 0,
            'total_response_time': 0.0,
            'avg_response_time': 0.0,
            'last_success': None,
            'last_failure': None,
            'consecutive_failures': 0,
            'is_active': True
        } for url in self.urls}
    
    def get_next_url(self) -> str:
        """Get next URL based on rotation strategy"""
        if self.strategy == 'round_robin':
            return self._round_robin()
        elif self.strategy == 'random':
            return self._random_selection()
        elif self.strategy == 'health_based':
            return self._health_based_selection()
        else:
            return self.urls[0]
    
    def _round_robin(self) -> str:
        """Simple round-robin selection"""
        active_urls = [url for url in self.urls if self.url_stats[url]['is_active']]
        if not active_urls:
            # Reset all URLs if none are active
            for url in self.urls:
                self.url_stats[url]['is_active'] = True
            active_urls = self.urls
        
        if self.current_index >= len(active_urls):
            self.current_index = 0
        
        url = active_urls[self.current_index]
        self.current_index = (self.current_index + 1) % len(active_urls)
        return url
    
    def _random_selection(self) -> str:
        """Random selection from active URLs"""
        active_urls = [url for url in self.urls if self.url_stats[url]['is_active']]
        if not active_urls:
            for url in self.urls:
                self.url_stats[url]['is_active'] = True
            active_urls = self.urls
        
        return random.choice(active_urls)
    
    def _health_based_selection(self) -> str:
        """Select URL based on health score (success rate and response time)"""
        active_urls = [url for url in self.urls if self.url_stats[url]['is_active']]
        if not active_urls:
            for url in self.urls:
                self.url_stats[url]['is_active'] = True
            active_urls = self.urls
        
        def calculate_score(url):
            stats = self.url_stats[url]
            success = stats['success_count']
            failure = stats['failure_count']
            total = success + failure
            
            if total == 0:
                return 0.5  # Neutral score for untested URLs
            
            success_rate = success / total
            avg_time = stats['avg_response_time']
            
            # Penalize for consecutive failures
            consecutive_penalty = min(stats['consecutive_failures'] * 0.1, 0.5)
            
            # Score: 70% success rate, 20% response time, 10% consecutive failures
            score = (success_rate * 0.7) - (min(avg_time / 10.0, 0.2)) - consecutive_penalty
            return max(0, score)
        
        # Sort by score and return best
        scored_urls = [(url, calculate_score(url)) for url in active_urls]
        scored_urls.sort(key=lambda x: x[1], reverse=True)
        
        return scored_urls[0][0]
    
    def mark_success(self, url: str, response_time: float):
        """Mark URL as successful"""
        if url in self.url_stats:
            stats = self.url_stats[url]
            stats['success_count'] += 1
            stats['consecutive_failures'] = 0
            stats['last_success'] = datetime.now()
            stats['is_active'] = True
            
            # Update average response time
            total = stats['success_count']
            stats['total_response_time'] += response_time
            stats['avg_response_time'] = stats['total_response_time'] / total
    
    def mark_failure(self, url: str):
        """Mark URL as failed"""
        if url in self.url_stats:
            stats = self.url_stats[url]
            stats['failure_count'] += 1
            stats['consecutive_failures'] += 1
            stats['last_failure'] = datetime.now()
            
            # Deactivate after 3 consecutive failures
            if stats['consecutive_failures'] >= 3:
                stats['is_active'] = False
                logger.warning(f"API URL {url} deactivated after 3 consecutive failures")
    
    def get_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all URLs"""
        result = []
        for url in self.urls:
            stats = self.url_stats[url]
            success = stats['success_count']
            failure = stats['failure_count']
            total = success + failure
            success_rate = (success / total * 100) if total > 0 else 0
            
            result.append({
                'url': url,
                'success_count': success,
                'failure_count': failure,
                'success_rate': success_rate,
                'avg_response_time': stats['avg_response_time'],
                'consecutive_failures': stats['consecutive_failures'],
                'is_active': stats['is_active'],
                'last_success': stats['last_success'],
                'last_failure': stats['last_failure']
            })
        
        return sorted(result, key=lambda x: x['success_rate'], reverse=True)

class RateLimiter:
    """Rate limiter to prevent API abuse"""
    
    def __init__(self, requests_per_minute: int = 30, burst: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst = burst
        self.requests = []
        self.burst_tokens = burst
        self.last_refill = time.time()
    
    async def acquire(self):
        """Acquire permission to make a request"""
        now = time.time()
        
        if now - self.last_refill >= 60:
            self.burst_tokens = self.burst
            self.last_refill = now
            self.requests = []
        
        if self.burst_tokens <= 0:
            await asyncio.sleep(1)
            return await self.acquire()
        
        minute_ago = now - 60
        self.requests = [req_time for req_time in self.requests if req_time > minute_ago]
        
        if len(self.requests) >= self.requests_per_minute:
            sleep_time = 60 - (now - self.requests[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
                return await self.acquire()
        
        self.requests.append(now)
        self.burst_tokens -= 1

class APIClient:
    """Enhanced API client with retry logic and multiple URL support"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(
            Config.RATE_LIMIT_REQUESTS_PER_MINUTE,
            Config.RATE_LIMIT_BURST
        )
        self.url_manager = APIURLManager(
            Config.INSTAGRAM_API_URLS,
            Config.API_URL_ROTATION_STRATEGY
        )
        self.session: Optional[aiohttp.ClientSession] = None
        self.consecutive_errors = 0
        self.last_error_time = None
        self.user_agent_index = 0
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self._create_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self._close_session()
    
    async def _create_session(self):
        """Create aiohttp session with proper configuration"""
        timeout = aiohttp.ClientTimeout(total=Config.API_TIMEOUT)
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=30,
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'User-Agent': self._get_user_agent(),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9'
            }
        )
    
    async def _close_session(self):
        """Close aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    def _get_user_agent(self) -> str:
        """Get rotating user agent"""
        user_agent = Config.USER_AGENTS[self.user_agent_index]
        self.user_agent_index = (self.user_agent_index + 1) % len(Config.USER_AGENTS)
        return user_agent
    
    def _is_in_cooldown(self) -> bool:
        """Check if we're in error cooldown period"""
        if self.consecutive_errors < Config.MAX_CONSECUTIVE_ERRORS:
            return False
        
        if self.last_error_time is None:
            return False
        
        return (datetime.now() - self.last_error_time).total_seconds() < Config.ERROR_COOLDOWN
    
    async def _make_request(self, url: str, params: Dict[str, Any], 
                          proxy: Optional[str] = None) -> APIResponse:
        """Make HTTP request with proper error handling"""
        if not self.session:
            await self._create_session()
        
        if self._is_in_cooldown():
            return APIResponse(
                success=False,
                data={},
                status_code=0,
                error="API in cooldown period due to consecutive errors",
                api_url=url
            )
        
        await self.rate_limiter.acquire()
        await asyncio.sleep(random.uniform(0.05, 0.2))

        start_time = time.time()
        
        try:
            async with self.session.get(
                url,
                params=params,
                proxy=proxy,
                headers={
                    'User-Agent': self._get_user_agent(),
                    'Accept': 'application/json, text/plain, */*',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
            ) as response:
                response_time = time.time() - start_time
                
                if response.status == 200:
                    try:
                        data = await response.json()
                        self.consecutive_errors = 0
                        return APIResponse(
                            success=True,
                            data=data,
                            status_code=response.status,
                            proxy_used=proxy,
                            response_time=response_time,
                            api_url=url
                        )
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error from {url}: {e}")
                        return APIResponse(
                            success=False,
                            data={},
                            status_code=response.status,
                            error=f"Invalid JSON response: {str(e)}",
                            proxy_used=proxy,
                            response_time=response_time,
                            api_url=url
                        )
                else:
                    error_msg = f"HTTP {response.status}"
                    if response.status == 429:
                        error_msg += " - Rate limited"
                    elif response.status == 403:
                        error_msg += " - Forbidden"
                    elif response.status == 404:
                        error_msg += " - Not found"
                    
                    error_data = {}
                    if response.status == 403 and proxy:
                        error_data = {'st': 'proxy_error'}

                    return APIResponse(
                        success=False,
                        data=error_data,
                        status_code=response.status,
                        error=error_msg,
                        proxy_used=proxy,
                        response_time=response_time,
                        api_url=url
                    )
        
        except asyncio.TimeoutError:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            timeout_data = {'st': 'proxy_error'} if proxy else {}
            return APIResponse(
                success=False,
                data=timeout_data,
                status_code=0,
                error="Request timeout",
                proxy_used=proxy,
                response_time=time.time() - start_time,
                api_url=url
            )
        
        except aiohttp.ClientError as e:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            client_error_data = {'st': 'proxy_error'} if proxy else {}
            return APIResponse(
                success=False,
                data=client_error_data,
                status_code=0,
                error=f"Client error: {str(e)}",
                proxy_used=proxy,
                response_time=time.time() - start_time,
                api_url=url
            )
        
        except Exception as e:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            logger.error(f"Unexpected error in API request to {url}: {e}")
            return APIResponse(
                success=False,
                data={},
                status_code=0,
                error=f"Unexpected error: {str(e)}",
                proxy_used=proxy,
                response_time=time.time() - start_time,
                api_url=url
            )
    
    async def get_instagram_profile(self, username: str, proxy: Optional[str] = None) -> APIResponse:
        """Get Instagram profile information with URL rotation"""
        username = username.replace('@', '').strip().lower()
        
        # Try Graph API first if enabled
        if Config.IG_GRAPH_API_ENABLED and Config.IG_ACCESS_TOKEN:
            graph_resp = await self._get_instagram_profile_graph(username, proxy)
            if graph_resp and (graph_resp.success or graph_resp.status_code in (404, 400)):
                return graph_resp

        # Try multiple URLs with rotation
        for attempt in range(Config.API_RETRY_ATTEMPTS):
            try:
                # Get next URL based on rotation strategy
                api_url = self.url_manager.get_next_url()
                
                response = await self._make_request(
                    api_url,
                    {'username': username},
                    proxy
                )
                
                # Update URL stats
                if response.success:
                    self.url_manager.mark_success(api_url, response.response_time)
                    return self._process_instagram_response(response, username)
                else:
                    self.url_manager.mark_failure(api_url)
                
                if response.status_code == 404:
                    return APIResponse(
                        success=True,
                        data={'usr': username, 'st': 'not_found'},
                        status_code=404,
                        proxy_used=proxy,
                        response_time=response.response_time,
                        api_url=api_url
                    )
                elif attempt < Config.API_RETRY_ATTEMPTS - 1:
                    delay = Config.API_RETRY_DELAY * (2 ** attempt)
                    logger.warning(f"API request to {api_url} failed (attempt {attempt + 1}), trying next URL in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    return response
            
            except Exception as e:
                logger.error(f"Error in get_instagram_profile attempt {attempt + 1}: {e}")
                if attempt < Config.API_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(Config.API_RETRY_DELAY)
                else:
                    return APIResponse(
                        success=False,
                        data={},
                        status_code=0,
                        error=f"All retry attempts failed: {str(e)}",
                        proxy_used=proxy
                    )
        
        return APIResponse(
            success=False,
            data={},
            status_code=0,
            error="Max retry attempts exceeded",
            proxy_used=proxy
        )
    
    async def _get_instagram_profile_graph(self, username: str, proxy: Optional[str]) -> Optional[APIResponse]:
        """Query Instagram Graph API using business_discovery"""
        try:
            if not Config.IG_BUSINESS_ACCOUNT_ID or not Config.IG_ACCESS_TOKEN:
                return None

            fields = ','.join(Config.IG_GRAPH_API_FIELDS)
            url = f"{Config.IG_GRAPH_API_BASE}/{Config.IG_BUSINESS_ACCOUNT_ID}"
            params = {
                'fields': f"business_discovery.username({username}){{{fields}}}",
                'access_token': Config.IG_ACCESS_TOKEN
            }

            resp = await self._make_request(url, params, proxy)
            if not resp.success:
                data = resp.data or {}
                error_info = data.get('error') if isinstance(data, dict) else None
                if resp.status_code in (400, 404):
                    if error_info and isinstance(error_info, dict):
                        message = (error_info.get('message') or '').lower()
                        if 'no data found' in message or 'cannot find' in message or 'unsupported get request' in message:
                            return APIResponse(True, {'usr': username, 'st': 'not_found'}, resp.status_code, proxy_used=resp.proxy_used, response_time=resp.response_time)
                return resp

            bd = (resp.data or {}).get('business_discovery') if isinstance(resp.data, dict) else None
            if not bd:
                return APIResponse(True, {'usr': username, 'st': 'not_found'}, 404, proxy_used=resp.proxy_used, response_time=resp.response_time)

            normalized = {
                'usr': bd.get('username', username),
                'nm': bd.get('name') or 'N/A',
                'id': str(bd.get('id', 'N/A')),
                'fw': str(bd.get('followers_count', 'N/A')),
                'fg': str(bd.get('follows_count', 'N/A')),
                'ps': str(bd.get('media_count', 'N/A')),
                'prv': False,
                'verified': bool(bd.get('is_verified', False)),
                'bio': self._truncate_bio(bd.get('biography', 'N/A')) if isinstance(bd.get('biography', 'N/A'), str) else 'N/A',
                'st': 'ok'
            }

            return APIResponse(True, normalized, 200, proxy_used=resp.proxy_used, response_time=resp.response_time)
        except Exception as e:
            logger.error(f"Graph API error for {username}: {e}")
            return APIResponse(False, {}, 0, error=f"Graph API error: {str(e)}", proxy_used=proxy)

    def _process_instagram_response(self, response: APIResponse, username: str) -> APIResponse:
        """Process Instagram API response and normalize data"""
        try:
            data = response.data
            
            if data.get('status') != 'ok':
                return APIResponse(
                    success=True,
                    data={'usr': username, 'st': 'not_found', 'error': 'User not found or API error'},
                    status_code=response.status_code,
                    proxy_used=response.proxy_used,
                    response_time=response.response_time,
                    api_url=response.api_url
                )
            
            profile = data.get('profile')
            if not profile:
                return APIResponse(
                    success=True,
                    data={'usr': username, 'st': 'not_found'},
                    status_code=response.status_code,
                    proxy_used=response.proxy_used,
                    response_time=response.response_time,
                    api_url=response.api_url
                )
            
            normalized_data = {
                'usr': profile.get('username', username),
                'nm': profile.get('full_name', 'N/A') or 'N/A',
                'id': str(profile.get('id', 'N/A')),
                'fw': str(profile.get('followers', 'N/A')),
                'fg': str(profile.get('following', 'N/A')),
                'ps': str(profile.get('posts', 'N/A')),
                'prv': profile.get('is_private', False),
                'verified': profile.get('is_verified', False),
                'bio': self._truncate_bio(profile.get('biography', 'N/A')),
                'st': 'ok',
                'account_creation_year': profile.get('account_creation_year', 'Unknown')
            }
            
            return APIResponse(
                success=True,
                data=normalized_data,
                status_code=response.status_code,
                proxy_used=response.proxy_used,
                response_time=response.response_time,
                api_url=response.api_url
            )
        
        except Exception as e:
            logger.error(f"Error processing Instagram response: {e}")
            return APIResponse(
                success=False,
                data={},
                status_code=response.status_code,
                error=f"Error processing response: {str(e)}",
                proxy_used=response.proxy_used,
                response_time=response.response_time,
                api_url=response.api_url
            )
    
    def _truncate_bio(self, bio: str, max_length: int = 100) -> str:
        """Truncate bio to max length"""
        if not bio or bio == 'N/A':
            return 'N/A'
        
        if len(bio) <= max_length:
            return bio
        
        return bio[:max_length] + '...'
    
    async def test_proxy(self, proxy_url: str) -> APIResponse:
        """Test proxy connectivity"""
        try:
            response = await self._make_request(
                Config.PROXY_TEST_URL,
                {},
                proxy_url
            )
            
            if response.success and 'origin' in response.data:
                return APIResponse(
                    success=True,
                    data={
                        'proxy': proxy_url,
                        'external_ip': response.data.get('origin'),
                        'response_time': response.response_time
                    },
                    status_code=response.status_code,
                    proxy_used=proxy_url,
                    response_time=response.response_time
                )
            else:
                return APIResponse(
                    success=False,
                    data={},
                    status_code=response.status_code,
                    error=response.error or "Proxy test failed",
                    proxy_used=proxy_url,
                    response_time=response.response_time
                )
        
        except Exception as e:
            return APIResponse(
                success=False,
                data={},
                status_code=0,
                error=f"Proxy test error: {str(e)}",
                proxy_used=proxy_url
            )
    
    def get_url_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all API URLs"""
        return self.url_manager.get_stats()
