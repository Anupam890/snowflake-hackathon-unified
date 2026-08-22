"""
Snowflake Connection Smoke Test.
Uses the persistent singleton SnowflakeManager.
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.snowflake_manager import snowflake_manager

def get_connection():
    """Returns the persistent singleton Snowflake connection."""
    return snowflake_manager.get_connection()

if __name__ == "__main__":
    print("Testing persistent Snowflake connection setup...")
    if snowflake_manager.is_connected():
        print(f"Connected to Snowflake successfully!")
        records, cols = snowflake_manager.execute_query("SELECT CURRENT_VERSION(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA();")
        if records:
            print("Session Details:", records[0])
    else:
        print("Failed to connect. Please check your .env configuration.")