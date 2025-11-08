"""
Enhanced Database Manager with connection pooling and better error handling
"""
import sqlite3
import json
import logging
import threading
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from contextlib import contextmanager
from dataclasses import dataclass

from config import Config

logger = logging.getLogger(__name__)

@dataclass
class DatabaseStats:
    """Database statistics"""
    total_logs: int
    total_users: int
    logs_today: int
    last_activity: Optional[datetime]

class EnhancedDatabaseManager:
    """Enhanced database manager with connection pooling and better error handling"""
    
    def __init__(self, db_name: str = None):
        self.db_name = db_name or Config.DATABASE_NAME
        self._local = threading.local()
        self._lock = threading.RLock()
        self._stats_cache = {}
        self._stats_cache_time = 0
        self._stats_cache_ttl = 60  # Cache for 1 minute
        
        # Initialize database
        self._init_database()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(
                self.db_name,
                check_same_thread=False,
                timeout=Config.DATABASE_TIMEOUT
            )
            self._local.connection.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            self._local.connection.execute("PRAGMA journal_mode=WAL")
            # Set busy timeout
            self._local.connection.execute("PRAGMA busy_timeout=30000")
        
        return self._local.connection
    
    def _close_connection(self):
        """Close thread-local connection"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = None
        try:
            conn = self._get_connection()
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.commit()
    
    def _init_database(self):
        """Initialize database with proper schema and indexes"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Logs table with better indexing
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitor_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    platform TEXT NOT NULL DEFAULT 'discord',
                    user_data TEXT,
                    proxy_used TEXT,
                    response_time REAL,
                    error_message TEXT
                )
            ''')
            
            # Authorized users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS authorized_users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    added_by INTEGER NOT NULL,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Proxy management table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS proxy_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    proxy_url TEXT NOT NULL UNIQUE,
                    success_count INTEGER DEFAULT 0,
                    failure_count INTEGER DEFAULT 0,
                    last_success TIMESTAMP,
                    last_failure TIMESTAMP,
                    avg_response_time REAL DEFAULT 0,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Monitoring sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS monitoring_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    monitor_type TEXT NOT NULL,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    check_count INTEGER DEFAULT 0,
                    user_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES authorized_users (user_id)
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_username ON monitor_logs(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON monitor_logs(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_logs_action ON monitor_logs(action)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON authorized_users(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_username ON monitoring_sessions(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_sessions_status ON monitoring_sessions(status)')
            
            # Add the owner as the first authorized user
            cursor.execute('''
                INSERT OR IGNORE INTO authorized_users (user_id, added_by, last_used)
                VALUES (?, ?, ?)
            ''', (Config.DISCORD_OWNER_ID, Config.DISCORD_OWNER_ID, datetime.now()))
            
            conn.commit()
    
    def is_user_authorized(self, user_id: int) -> bool:
        """Check if a user ID is authorized"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT 1 FROM authorized_users WHERE user_id = ? AND is_active = 1',
                    (user_id,)
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking user authorization: {e}")
            return False
    
    def add_user(self, user_id: int, added_by: int) -> bool:
        """Add a new authorized user"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO authorized_users (user_id, added_by) VALUES (?, ?)',
                    (user_id, added_by)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding user: {e}")
            return False
    
    def remove_user(self, user_id: int) -> bool:
        """Remove an authorized user (soft delete)"""
        if user_id == Config.DISCORD_OWNER_ID:
            return False
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE authorized_users SET is_active = 0 WHERE user_id = ?',
                    (user_id,)
                )
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing user: {e}")
            return False
    
    def update_user_last_used(self, user_id: int):
        """Update user's last used timestamp"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE authorized_users SET last_used = ? WHERE user_id = ?',
                    (datetime.now(), user_id)
                )
        except Exception as e:
            logger.error(f"Error updating user last used: {e}")
    
    def list_users(self) -> List[Tuple[int, int, datetime, Optional[datetime], bool]]:
        """List all authorized users with additional info"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, added_by, added_at, last_used, is_active
                    FROM authorized_users
                    ORDER BY added_at DESC
                ''')
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error listing users: {e}")
            return []
    
    def log_event(self, username: str, action: str, status: str, 
                  user_data: Dict[str, Any] = None, proxy_used: str = None,
                  response_time: float = 0.0, error_message: str = None):
        """Log an event to the database with enhanced data"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO monitor_logs 
                    (username, action, status, platform, user_data, proxy_used, response_time, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    username, action, status, 'discord',
                    json.dumps(user_data or {}), proxy_used,
                    response_time, error_message
                ))
        except Exception as e:
            logger.error(f"Database logging error: {e}")
    
    def start_monitoring_session(self, username: str, monitor_type: str, user_id: int) -> int:
        """Start a new monitoring session"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO monitoring_sessions (username, monitor_type, user_id)
                    VALUES (?, ?, ?)
                ''', (username, monitor_type, user_id))
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error starting monitoring session: {e}")
            return 0
    
    def end_monitoring_session(self, session_id: int, status: str = 'completed'):
        """End a monitoring session"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE monitoring_sessions 
                    SET ended_at = ?, status = ?
                    WHERE id = ?
                ''', (datetime.now(), status, session_id))
        except Exception as e:
            logger.error(f"Error ending monitoring session: {e}")
    
    def update_session_check_count(self, session_id: int, check_count: int):
        """Update session check count"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE monitoring_sessions 
                    SET check_count = ?
                    WHERE id = ?
                ''', (check_count, session_id))
        except Exception as e:
            logger.error(f"Error updating session check count: {e}")
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active monitoring sessions"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT id, username, monitor_type, started_at, check_count, user_id
                    FROM monitoring_sessions
                    WHERE status = 'active'
                    ORDER BY started_at DESC
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting active sessions: {e}")
            return []
    
    def update_proxy_stats(self, proxy_url: str, success: bool, response_time: float = 0.0):
        """Update proxy statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                if success:
                    cursor.execute('''
                        INSERT INTO proxy_stats (proxy_url, success_count, last_success, avg_response_time)
                        VALUES (?, 1, ?, ?)
                        ON CONFLICT(proxy_url) DO UPDATE SET
                            success_count = success_count + 1,
                            last_success = ?,
                            avg_response_time = (avg_response_time * success_count + ?) / (success_count + 1)
                    ''', (proxy_url, datetime.now(), response_time, datetime.now(), response_time))
                else:
                    cursor.execute('''
                        INSERT INTO proxy_stats (proxy_url, failure_count, last_failure)
                        VALUES (?, 1, ?)
                        ON CONFLICT(proxy_url) DO UPDATE SET
                            failure_count = failure_count + 1,
                            last_failure = ?
                    ''', (proxy_url, datetime.now(), datetime.now()))
        except Exception as e:
            logger.error(f"Error updating proxy stats: {e}")
    
    def get_proxy_stats(self) -> List[Dict[str, Any]]:
        """Get proxy statistics"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT proxy_url, success_count, failure_count, 
                           last_success, last_failure, avg_response_time, is_active
                    FROM proxy_stats
                    ORDER BY (success_count - failure_count) DESC
                ''')
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting proxy stats: {e}")
            return []
    
    def get_database_stats(self) -> DatabaseStats:
        """Get database statistics with caching"""
        now = time.time()
        if now - self._stats_cache_time < self._stats_cache_ttl:
            return self._stats_cache.get('stats', DatabaseStats(0, 0, 0, None))
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Total logs
                cursor.execute('SELECT COUNT(*) FROM monitor_logs')
                total_logs = cursor.fetchone()[0]
                
                # Total users
                cursor.execute('SELECT COUNT(*) FROM authorized_users WHERE is_active = 1')
                total_users = cursor.fetchone()[0]
                
                # Logs today
                today = datetime.now().date()
                cursor.execute('''
                    SELECT COUNT(*) FROM monitor_logs 
                    WHERE DATE(timestamp) = ?
                ''', (today,))
                logs_today = cursor.fetchone()[0]
                
                # Last activity
                cursor.execute('''
                    SELECT MAX(timestamp) FROM monitor_logs
                ''')
                last_activity = cursor.fetchone()[0]
                if last_activity:
                    last_activity = datetime.fromisoformat(last_activity)
                
                stats = DatabaseStats(total_logs, total_users, logs_today, last_activity)
                self._stats_cache['stats'] = stats
                self._stats_cache_time = now
                
                return stats
        except Exception as e:
            logger.error(f"Error getting database stats: {e}")
            return DatabaseStats(0, 0, 0, None)
    
    def cleanup_old_logs(self, days: int = 30):
        """Clean up old logs to prevent database bloat"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cutoff_date = datetime.now().timestamp() - (days * 24 * 60 * 60)
                cursor.execute('''
                    DELETE FROM monitor_logs 
                    WHERE timestamp < ?
                ''', (cutoff_date,))
                deleted_count = cursor.rowcount
                logger.info(f"Cleaned up {deleted_count} old log entries")
                return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up old logs: {e}")
            return 0
    
    def close(self):
        """Close all database connections"""
        self._close_connection()
