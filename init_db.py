#!/usr/bin/env python3
"""
Database initialization script for WebRadio9
Drops existing tables and creates new ones based on current models
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from shared.models import Base, engine, create_tables
from shared.logging import setup_logger

logger = setup_logger('init_db')

def init_database():
    """Drop all tables and recreate them"""
    try:
        logger.info("Dropping existing tables...")
        Base.metadata.drop_all(bind=engine)
        
        logger.info("Creating new tables...")
        create_tables()
        
        logger.info("Database initialized successfully!")
        
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_database()
