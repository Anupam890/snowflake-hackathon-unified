import os
import sys
import time
import threading
from typing import Optional, List, Dict, Any, Tuple
from dotenv import dotenv_values

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import snowflake.connector

class SnowflakeManager:
    """
    Thread-Safe Singleton Persistent Connection Manager for Snowflake.
    Establishes connection once, caches MFA token securely in Windows Credential Manager,
    and reuses the active session persistently across all application queries and REST calls.
    """
    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(SnowflakeManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, '_initialized', False):
            return
        
        env_file_path = os.path.join(PROJECT_ROOT, '.env')
        self.env = {k.strip(): v.strip() for k, v in dotenv_values(env_file_path).items()} if os.path.exists(env_file_path) else {}
        self._conn: Optional[snowflake.connector.SnowflakeConnection] = None
        self._token: Optional[str] = None
        self._host: Optional[str] = None
        self._version: Optional[str] = None
        self._lock = threading.RLock()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._stop_heartbeat = threading.Event()
        self._initialized = True

    def connect(self) -> bool:
        """
        Establishes the one-time persistent connection to Snowflake with MFA caching.
        Thread-safe and reuses cached MFA tokens via Windows Credential Manager.
        """
        with self._lock:
            # If already connected and alive, return True immediately
            if self._conn is not None and not self._conn.is_closed():
                try:
                    cur = self._conn.cursor()
                    cur.execute("SELECT 1;")
                    cur.fetchone()
                    cur.close()
                    return True
                except Exception:
                    pass

            try:
                account = self.env.get("SNOWFLAKE_ACCOUNT", "").strip()
                user = self.env.get("SNOWFLAKE_USERNAME", "").strip()
                password = self.env.get("SNOWFLAKE_PASSWORD", "").strip()
                warehouse = self.env.get("SNOWFLAKE_WAREHOUSE", "").strip()
                database = self.env.get("SNOWFLAKE_DB", "").strip()
                schema = self.env.get("SNOWFLAKE_SH", "").strip()
                role = self.env.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN").strip()
                self._host = self.env.get("SNOWFLAKE_HOST_URL", f"{account}.snowflakecomputing.com").strip()

                if not (account and user and password):
                    print("[SnowflakeManager] Warning: Credentials incomplete in .env")
                    return False

                print(f"[SnowflakeManager] Initializing persistent connection to account: {account} (User: {user})...")
                
                # Connect with MFA token caching and keep-alive enabled
                self._conn = snowflake.connector.connect(
                    user=user,
                    password=password,
                    account=account,
                    warehouse=warehouse,
                    database=database,
                    schema=schema,
                    role=role,
                    authenticator="username_password_mfa",
                    client_store_temporary_credential=True,
                    client_request_mfa_token=True,
                    client_session_keep_alive=True,
                    session_parameters={
                        "CLIENT_TELEMETRY_ENABLED": False,
                        "QUERY_TIMEOUT_IN_SECONDS": 90
                    }
                )

                # Test connection & cache version
                cur = self._conn.cursor()
                cur.execute("SELECT CURRENT_VERSION()")
                self._version = cur.fetchone()[0]
                cur.close()

                # Cache REST session token for Cortex REST API calls
                if hasattr(self._conn, "rest") and hasattr(self._conn.rest, "token"):
                    self._token = self._conn.rest.token

                print(f"[SnowflakeManager] Persistent connection active (Snowflake v{self._version})")
                
                # Start background heartbeat to keep session alive
                self._start_heartbeat()
                return True

            except Exception as e:
                print(f"[SnowflakeManager] Connection failed: {e}")
                self._conn = None
                return False

    def is_connected(self) -> bool:
        """
        Thread-safe check to verify if the persistent connection is alive.
        Only attempts reconnection if the connection is truly broken.
        """
        with self._lock:
            if self._conn is None or self._conn.is_closed():
                return self.connect()
            try:
                cur = self._conn.cursor()
                cur.execute("SELECT 1;")
                cur.fetchone()
                cur.close()
                return True
            except Exception as e:
                print(f"[SnowflakeManager] Session check encountered error: {e}. Reconnecting...")
                return self.connect()

    def get_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Returns the persistent Snowflake connection, connecting if not already active."""
        with self._lock:
            if not self.is_connected():
                raise ConnectionError("Unable to establish persistent Snowflake connection.")
            return self._conn

    def get_session_token(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Returns the active REST session token and host URL from the persistent connection.
        Avoids redundant reconnects by extracting the live token from the active connection.
        """
        with self._lock:
            if not self.is_connected():
                self.connect()
            
            if self._conn and hasattr(self._conn, "rest") and hasattr(self._conn.rest, "token"):
                self._token = self._conn.rest.token
            
            return self._token, self._host

    def execute_query(self, sql: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[List[str]]]:
        """
        Executes a SQL query using the persistent connection with thread synchronization.
        Returns JSON-safe rows and column names.
        """
        with self._lock:
            try:
                conn = self.get_connection()
                cur = conn.cursor()
                cur.execute(sql)
                
                cols = [c[0] for c in cur.description] if cur.description else []
                raw_rows = cur.fetchall()
                cur.close()

                records = []
                for r in raw_rows:
                    row_dict = {}
                    for col_name, val in zip(cols, r):
                        if val is None:
                            row_dict[col_name] = None
                        elif hasattr(val, 'isoformat'):
                            row_dict[col_name] = val.isoformat()
                        elif isinstance(val, (int, float, str, bool)):
                            row_dict[col_name] = val
                        else:
                            try:
                                row_dict[col_name] = float(val)
                            except Exception:
                                row_dict[col_name] = str(val)
                    records.append(row_dict)
                return records, cols

            except Exception as e:
                print(f"[SnowflakeManager] Query execution error: {e}")
                return None, None

    def _start_heartbeat(self):
        """Starts a background daemon thread that periodically pings Snowflake to keep session alive."""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._stop_heartbeat.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True, name="SnowflakeHeartbeat")
        self._heartbeat_thread.start()

    def _heartbeat_loop(self):
        """Pings Snowflake every 10 minutes to maintain persistent active session state."""
        while not self._stop_heartbeat.wait(600):  # 10 minutes interval
            with self._lock:
                if self._conn and not self._conn.is_closed():
                    try:
                        cur = self._conn.cursor()
                        cur.execute("SELECT 1;")
                        cur.fetchone()
                        cur.close()
                    except Exception as e:
                        print(f"[SnowflakeManager Heartbeat] Ping warning: {e}")

    def close(self):
        """Closes the persistent connection cleanly."""
        with self._lock:
            self._stop_heartbeat.set()
            if self._conn and not self._conn.is_closed():
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None
                print("[SnowflakeManager] Persistent connection closed.")


# Global singleton instance
snowflake_manager = SnowflakeManager()
