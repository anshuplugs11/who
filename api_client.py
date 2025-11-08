"""
Enhanced API Client with improved error handling, rate limiting, and retry logic
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
        
        # Refill burst tokens
        if now - self.last_refill >= 60:  # Refill every minute
            self.burst_tokens = self.burst
            self.last_refill = now
            self.requests = []
        
        # Check burst limit
        if self.burst_tokens <= 0:
            await asyncio.sleep(1)
            return await self.acquire()
        
        # Check rate limit
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
    """Enhanced API client with retry logic and error handling"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(
            Config.RATE_LIMIT_REQUESTS_PER_MINUTE,
            Config.RATE_LIMIT_BURST
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
        
        # Check cooldown
        if self._is_in_cooldown():
            return APIResponse(
                success=False,
                data={},
                status_code=0,
                error="API in cooldown period due to consecutive errors"
            )
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # Small jitter to reduce burst patterns
        await asyncio.sleep(random.uniform(0.05, 0.2))

        start_time = time.time()
        proxy_config = self._get_proxy_config(proxy) if proxy else None
        
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
                        self.consecutive_errors = 0  # Reset on success
                        return APIResponse(
                            success=True,
                            data=data,
                            status_code=response.status,
                            proxy_used=proxy,
                            response_time=response_time
                        )
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON decode error: {e}")
                        return APIResponse(
                            success=False,
                            data={},
                            status_code=response.status,
                            error=f"Invalid JSON response: {str(e)}",
                            proxy_used=proxy,
                            response_time=response_time
                        )
                else:
                    error_msg = f"HTTP {response.status}"
                    if response.status == 429:  # Rate limited
                        error_msg += " - Rate limited"
                    elif response.status == 403:
                        error_msg += " - Forbidden"
                    elif response.status == 404:
                        error_msg += " - Not found"
                    
                    # If 403 and proxy in use, surface as proxy_error in data for higher-level handling
                    error_data = {}
                    if response.status == 403 and proxy:
                        error_data = {'st': 'proxy_error'}

                    return APIResponse(
                        success=False,
                        data=error_data,
                        status_code=response.status,
                        error=error_msg,
                        proxy_used=proxy,
                        response_time=response_time
                    )
        
        except asyncio.TimeoutError:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            # If a proxy was used, surface this as a proxy error so higher-level logic can retry without proxy
            timeout_data = {'st': 'proxy_error'} if proxy else {}
            return APIResponse(
                success=False,
                data=timeout_data,
                status_code=0,
                error="Request timeout",
                proxy_used=proxy,
                response_time=time.time() - start_time
            )
        
        except aiohttp.ClientError as e:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            # If a proxy was used, mark as proxy error so caller can retry without proxy
            client_error_data = {'st': 'proxy_error'} if proxy else {}
            return APIResponse(
                success=False,
                data=client_error_data,
                status_code=0,
                error=f"Client error: {str(e)}",
                proxy_used=proxy,
                response_time=time.time() - start_time
            )
        
        except Exception as e:
            self.consecutive_errors += 1
            self.last_error_time = datetime.now()
            logger.error(f"Unexpected error in API request: {e}")
            return APIResponse(
                success=False,
                data={},
                status_code=0,
                error=f"Unexpected error: {str(e)}",
                proxy_used=proxy,
                response_time=time.time() - start_time
            )
    
    def _get_proxy_config(self, proxy_url: str) -> Optional[str]:
        """Convert proxy URL to aiohttp format"""
        if not proxy_url:
            return None
        return proxy_url
    
    async def get_instagram_profile(self, username: str, proxy: Optional[str] = None) -> APIResponse:
        """Get Instagram profile information.
        If IG_GRAPH_API_ENABLED, try Graph API first, then fall back to legacy endpoint.
        """
        username = username.replace('@', '').strip().lower()
        
        # Try Graph API first if enabled
        if Config.IG_GRAPH_API_ENABLED and Config.IG_ACCESS_TOKEN:
            graph_resp = await self._get_instagram_profile_graph(username, proxy)
            if graph_resp and (graph_resp.success or graph_resp.status_code in (404, 400)):
                return graph_resp

        for attempt in range(Config.API_RETRY_ATTEMPTS):
            try:
                response = await self._make_request(
                    Config.INSTAGRAM_API_URL,
                    {'username': username},
                    proxy
                )
                
                if response.success:
                    return self._process_instagram_response(response, username)
                elif response.status_code == 404:
                    # Not found is a valid response, not an error
                    return APIResponse(
                        success=True,
                        data={'usr': username, 'st': 'not_found'},
                        status_code=404,
                        proxy_used=proxy,
                        response_time=response.response_time
                    )
                elif attempt < Config.API_RETRY_ATTEMPTS - 1:
                    # Retry on failure
                    delay = Config.API_RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"API request failed (attempt {attempt + 1}), retrying in {delay}s")
                    await asyncio.sleep(delay)
                    continue
                else:
                    # Final attempt failed
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
        """Query Instagram Graph API using business_discovery to fetch public profile by username."""
        try:
            if not Config.IG_BUSINESS_ACCOUNT_ID or not Config.IG_ACCESS_TOKEN:
                return None

            fields = ','.join(Config.IG_GRAPH_API_FIELDS)
            # business_discovery requires the business account id context
            url = f"{Config.IG_GRAPH_API_BASE}/{Config.IG_BUSINESS_ACCOUNT_ID}"
            params = {
                'fields': f"business_discovery.username({username}){{{fields}}}",
                'access_token': Config.IG_ACCESS_TOKEN
            }

            resp = await self._make_request(url, params, proxy)
            if not resp.success:
                # Graph API returns 400 for not found/permission issues. Map 400 with specific body to not_found when appropriate.
                data = resp.data or {}
                error_info = data.get('error') if isinstance(data, dict) else None
                if resp.status_code in (400, 404):
                    # Try to distinguish not found vs permissions
                    if error_info and isinstance(error_info, dict):
                        message = (error_info.get('message') or '').lower()
                        if 'no data found' in message or 'cannot find' in message or 'unsupported get request' in message:
                            return APIResponse(True, {'usr': username, 'st': 'not_found'}, resp.status_code, proxy_used=resp.proxy_used, response_time=resp.response_time)
                return resp

            # Parse business_discovery object
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
                'prv': False,  # Graph API exposes business/creator public data
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
                    response_time=response.response_time
                )
            
            profile = data.get('profile')
            if not profile:
                return APIResponse(
                    success=True,
                    data={'usr': username, 'st': 'not_found'},
                    status_code=response.status_code,
                    proxy_used=response.proxy_used,
                    response_time=response.response_time
                )
            
            # Normalize profile data
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
                response_time=response.response_time
            )
        
        except Exception as e:
            logger.error(f"Error processing Instagram response: {e}")
            return APIResponse(
                success=False,
                data={},
                status_code=response.status_code,
                error=f"Error processing response: {str(e)}",
                proxy_used=response.proxy_used,
                response_time=response.response_time
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
