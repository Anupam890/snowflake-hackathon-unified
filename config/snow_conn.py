import snowflake.connector
import os

# Establish connection
conn = snowflake.connector.connect(
user=os.getenv("SNOWFLAKE_USERNAME"),
password=os.getenv("SNOWFLAKE_PASSWORD"),
account=os.getenv("SNOWFLAKE_ACCOUNT"),
warehouse=os.getenv("SNOWFLAKE_WAREHOUSE"),
database=od.getenv("SNOWFLAKE_DB"),
schema=os.getenv("SNOWFLAKE_SH"),
session_parameters={
"CLIENT_TELEMETRY_ENABLED": False # Optional: disable telemetry
})

# Create a cursor and execute a query
cur = conn.cursor()
try:
    cur.execute("SELECT CURRENT_VERSION()")
    result = cur.fetchone()
    print(f"Snowflake version: {result[0]}")
finally:
    cur.close()
    conn.close()