-- WebRadio9 Database Initialization
CREATE DATABASE IF NOT EXISTS webradio9;
USE webradio9;

-- Grant privileges to webradio user
GRANT ALL PRIVILEGES ON webradio9.* TO 'webradio'@'%';
FLUSH PRIVILEGES;

-- Create tables (will be created by the application on first run)
-- This file ensures the database and user are properly set up
