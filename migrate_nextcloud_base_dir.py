#!/usr/bin/env python3
"""
Migration script to add nextcloud_base_dir column to recordings table
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from shared.models import get_db
from sqlalchemy import text

def migrate():
    """Add nextcloud_base_dir column to recordings table"""
    try:
        db = next(get_db())
        
        # Check if column already exists
        result = db.execute(text("SHOW COLUMNS FROM recordings LIKE 'nextcloud_base_dir'"))
        if result.fetchone():
            print("Column nextcloud_base_dir already exists in recordings table")
            return
        
        # Add the column
        db.execute(text("ALTER TABLE recordings ADD COLUMN nextcloud_base_dir VARCHAR(255) DEFAULT '/Recordings'"))
        
        db.commit()
        print("Successfully added nextcloud_base_dir column to recordings table")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()

if __name__ == '__main__':
    migrate()
