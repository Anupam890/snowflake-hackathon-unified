import os
import sys
import time
import threading
from typing import Optional, List, Dict, Any, Tuple
from dotenv import dotenv_values

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

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
        self._current_user: Optional[str] = self.env.get("SNOWFLAKE_USERNAME", "UNIFIEDAI")
        self._current_role: Optional[str] = self.env.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN")
        self._current_warehouse: Optional[str] = self.env.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH")
        self._current_database: Optional[str] = self.env.get("SNOWFLAKE_DB", "INSURANCE_MGMT_SYSTEM")
        self._current_schema: Optional[str] = self.env.get("SNOWFLAKE_SH", "HACKATHON_SH")
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

                # Test connection & cache version and session context
                cur = self._conn.cursor()
                cur.execute("SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_VERSION();")
                row = cur.fetchone()
                if row:
                    self._current_user = row[0] or user
                    self._current_role = row[1] or role
                    self._current_warehouse = row[2] or warehouse
                    self._current_database = row[3] or database
                    self._current_schema = row[4] or schema
                    self._version = row[5]
                cur.close()

                # Cache REST session token for Cortex REST API calls
                if hasattr(self._conn, "rest") and hasattr(self._conn.rest, "token"):
                    self._token = self._conn.rest.token

                print(f"[SnowflakeManager] Persistent connection active (User: {self._current_user}, Role: {self._current_role}, Snowflake v{self._version})")
                
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

    def get_session_context(self) -> Dict[str, Any]:
        """Returns the cached Snowflake session context information."""
        with self._lock:
            is_ok = self.is_connected()
            return {
                "connected": is_ok,
                "user": self._current_user or self.env.get("SNOWFLAKE_USERNAME", "UNIFIEDAI"),
                "role": self._current_role or self.env.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
                "warehouse": self._current_warehouse or self.env.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
                "database": self._current_database or self.env.get("SNOWFLAKE_DB", "INSURANCE_MGMT_SYSTEM"),
                "schema": self._current_schema or self.env.get("SNOWFLAKE_SH", "HACKATHON_SH"),
                "version": self._version,
                "account": self.env.get("SNOWFLAKE_ACCOUNT", ""),
                "host": self._host
            }

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
        """Pings Snowflake every 5 minutes to maintain persistent active session state and prevent Duo re-auth."""
        while not self._stop_heartbeat.wait(300):  # 5 minutes interval
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


def get_snowflake_manager() -> SnowflakeManager:
    """Returns the persistent SnowflakeManager singleton."""
    return snowflake_manager


def get_st_cached_snowflake_manager() -> SnowflakeManager:
    """
    Streamlit cache_resource wrapper. Guarantees that across all Streamlit
    script reruns, page switches, and user interactions, the exact same
    Snowflake session and connection object is reused without triggering Duo MFA.
    """
    try:
        import streamlit as st
        @st.cache_resource(show_spinner=False)
        def _get_manager():
            mgr = SnowflakeManager()
            mgr.connect()
            return mgr
        return _get_manager()
    except Exception:
        return snowflake_manager
