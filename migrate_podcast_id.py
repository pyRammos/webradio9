#!/usr/bin/env python3
"""
Migration script to add podcast_id column to recordings table
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from shared.models import get_db
from sqlalchemy import text

def migrate():
    """Add podcast_id column to recordings table"""
    try:
        db = next(get_db())
        
        # Check if column already exists
        result = db.execute(text("SHOW COLUMNS FROM recordings LIKE 'podcast_id'"))
        if result.fetchone():
            print("Column podcast_id already exists in recordings table")
            return
        
        # Add the column
        db.execute(text("ALTER TABLE recordings ADD COLUMN podcast_id INT NULL"))
        
        # Add foreign key constraint
        db.execute(text("""
            ALTER TABLE recordings 
            ADD CONSTRAINT fk_recordings_podcast_id 
            FOREIGN KEY (podcast_id) REFERENCES podcasts(id) 
            ON DELETE SET NULL
        """))
        
        db.commit()
        print("Successfully added podcast_id column to recordings table")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()

if __name__ == '__main__':
    migrate()
