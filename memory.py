import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict

DB_PATH = "backend_guardian_memory.db"

def init_memory_db():
    """Initializes the persistent memory table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS debug_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_problem TEXT NOT NULL,
            affected_files TEXT NOT NULL,
            root_cause TEXT NOT NULL,
            proposed_fix TEXT NOT NULL,
            test_status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_session_memory(
    user_problem: str,
    affected_files: List[str],
    root_cause: str,
    proposed_fix: str,
    test_status: str
):
    """Saves a verified debugging session to database."""
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO debug_history (user_problem, affected_files, root_cause, proposed_fix, test_status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        user_problem,
        json.dumps(affected_files),
        root_cause,
        proposed_fix,
        test_status,
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    conn.close()

def lookup_similar_cases(keywords: str) -> List[Dict]:
    """Finds past successful resolutions matching problem keywords."""
    init_memory_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    query = f"%{keywords}%"
    cursor.execute("""
        SELECT id, user_problem, root_cause, proposed_fix, test_status, created_at
        FROM debug_history
        WHERE test_status = 'PASSED' AND (user_problem LIKE ? OR root_cause LIKE ?)
        ORDER BY id DESC
        LIMIT 2
    """, (query, query))
    
    rows = cursor.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "problem": r[1],
            "root_cause": r[2],
            "proposed_fix": r[3],
            "status": r[4],
            "date": r[5]
        })
    return results

if __name__ == "__main__":
    init_memory_db()
    print("Memory database initialized successfully.")