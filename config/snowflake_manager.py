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
    Singleton Persistent Connection Manager for Snowflake.
    Establishes connection once and reuses it across all application queries.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
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
        self._token_expiry: float = 0
        self._host: Optional[str] = None
        self._version: Optional[str] = None
        self._initialized = True
        
        # Connect once on initialization
        self.connect()

    def connect(self) -> bool:
        """Establishes the one-time connection to Snowflake."""
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

            print(f"[SnowflakeManager] Initializing persistent connection to account: {account}...")
            self._conn = snowflake.connector.connect(
                user=user,
                password=password,
                account=account,
                warehouse=warehouse,
                database=database,
                schema=schema,
                role=role,
                client_session_keep_alive=True,
                session_parameters={
                    "CLIENT_TELEMETRY_ENABLED": False,
                    "QUERY_TIMEOUT_IN_SECONDS": 60
                }
            )

            # Test connection & cache version
            cur = self._conn.cursor()
            cur.execute("SELECT CURRENT_VERSION()")
            self._version = cur.fetchone()[0]
            cur.close()

            # Cache REST session token
            self._token = self._conn.rest.token
            self._token_expiry = time.time() + 1800
            
            print(f"[SnowflakeManager] Connected successfully (Snowflake v{self._version})")
            return True

        except Exception as e:
            print(f"[SnowflakeManager] Connection failed: {e}")
            self._conn = None
            return False

    def is_connected(self) -> bool:
        """Verifies if the persistent connection is alive, reconnecting if needed."""
        if self._conn is None or self._conn.is_closed():
            return self.connect()
        try:
            cur = self._conn.cursor()
            cur.execute("SELECT 1;")
            cur.fetchone()
            cur.close()
            return True
        except Exception:
            return self.connect()

    def get_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Returns the persistent Snowflake connection."""
        if not self.is_connected():
            raise ConnectionError("Unable to establish Snowflake connection.")
        return self._conn

    def get_session_token(self) -> Tuple[str, str]:
        """Returns the active REST session token and host URL."""
        if not self._token or time.time() > self._token_expiry or not self.is_connected():
            self.connect()
        return self._token, self._host

    def execute_query(self, sql: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[List[str]]]:
        """Executes a SQL query using the persistent connection and returns JSON-safe rows."""
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

    def close(self):
        """Closes the persistent connection."""
        if self._conn and not self._conn.is_closed():
            self._conn.close()
            print("[SnowflakeManager] Persistent connection closed.")


# Global singleton instance
snowflake_manager = SnowflakeManager()
