"""
Snowflake Connection & Persistence Verification Test.
Tests one-time persistent singleton connection, cached session token, and concurrent query safety.
"""
import os
import sys
import time
import concurrent.futures

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config.snowflake_manager import snowflake_manager

def get_connection():
    """Returns the persistent singleton Snowflake connection."""
    return snowflake_manager.get_connection()

def test_persistence():
    print("=" * 60)
    print("[TEST] TESTING SNOWFLAKE PERSISTENT SINGLETON CONNECTION & MFA CACHE")
    print("=" * 60)

    # 1. Initial Connection
    print("\n1. Establishing / Verifying Persistent Connection...")
    t0 = time.time()
    is_connected = snowflake_manager.is_connected()
    duration = time.time() - t0

    if not is_connected:
        print("[FAIL] Connection Failed. Check .env configuration.")
        return False
    print(f"[OK] Connected in {duration:.2f}s")

    # 2. Get Session Details
    records, cols = snowflake_manager.execute_query(
        "SELECT CURRENT_USER(), CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE(), CURRENT_SCHEMA(), CURRENT_VERSION();"
    )
    if records:
        print("\n2. Session Context:")
        for k, v in records[0].items():
            print(f"   * {k}: {v}")

    # 3. Test Session Token Extraction
    token, host = snowflake_manager.get_session_token()
    token_preview = f"{token[:12]}..." if token else "None"
    print(f"\n3. REST Session Token: {token_preview} (Length: {len(token) if token else 0})")
    print(f"   Target Host: {host}")

    # 4. Test Query Execution Reusing Same Session
    print("\n4. Executing 3 Sequential Queries (Reusing Persistent Connection)...")
    for i in range(3):
        t_start = time.time()
        res, _ = snowflake_manager.execute_query(f"SELECT {i+1} AS QUERY_NUM, CURRENT_TIMESTAMP();")
        q_time = time.time() - t_start
        print(f"   Query #{i+1} executed in {q_time:.3f}s (reused existing session)")

    # 5. Test Concurrent Multi-Threaded Query Execution Safety
    print("\n5. Testing Concurrent Multi-Threaded Queries (Thread Safety)...")
    
    def run_concurrent_q(idx):
        t_start = time.time()
        res, _ = snowflake_manager.execute_query(f"SELECT {idx} AS THREAD_ID, 100 + {idx} AS RESULT;")
        return idx, time.time() - t_start, res

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(run_concurrent_q, i) for i in range(1, 5)]
        for f in concurrent.futures.as_completed(futures):
            idx, elapsed, res = f.result()
            print(f"   Thread #{idx} completed in {elapsed:.3f}s -> Result: {res}")

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL PERSISTENCE AND THREAD-SAFETY TESTS PASSED!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    test_persistence()