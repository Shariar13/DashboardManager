import sqlite3
from datetime import datetime

DB_PATH = '/app/data/ctf_manager.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT UNIQUE NOT NULL,
        team_code TEXT UNIQUE NOT NULL,
        team_ip INTEGER UNIQUE NOT NULL,
        vpn_generated INTEGER DEFAULT 0,
        vpn_file_path TEXT,
        challenges_running INTEGER DEFAULT 0,
        network_created INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS containers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_id INTEGER,
        container_name TEXT,
        container_id TEXT,
        challenge_type TEXT,
        ip_address TEXT,
        port INTEGER,
        status TEXT,
        FOREIGN KEY(team_id) REFERENCES teams(id)
    )''')
    
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn