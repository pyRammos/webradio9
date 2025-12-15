#!/usr/bin/env python3
"""
Migration script to add recurrence_end column to recordings table
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from shared.models import get_db
from sqlalchemy import text

def migrate():
    """Add recurrence_end column to recordings table"""
    try:
        db = next(get_db())
        
        # Check if column already exists
        result = db.execute(text("SHOW COLUMNS FROM recordings LIKE 'recurrence_end'"))
        if result.fetchone():
            print("Column recurrence_end already exists in recordings table")
            return
        
        # Add the column
        db.execute(text("ALTER TABLE recordings ADD COLUMN recurrence_end DATETIME NULL"))
        
        db.commit()
        print("Successfully added recurrence_end column to recordings table")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        db.rollback()

if __name__ == '__main__':
    migrate()
