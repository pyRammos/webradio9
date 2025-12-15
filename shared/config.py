import configparser
import os
from pathlib import Path

class Config:
    def __init__(self):
        self.config = configparser.ConfigParser()
        self.config_path = Path(__file__).parent.parent / 'config' / 'settings.cfg'
        self.load()
    
    def load(self):
        if self.config_path.exists():
            self.config.read(self.config_path)
    
    def get(self, section, key, fallback=None):
        return self.config.get(section, key, fallback=fallback)
    
    def getint(self, section, key, fallback=0):
        return self.config.getint(section, key, fallback=fallback)
    
    def getboolean(self, section, key, fallback=False):
        return self.config.getboolean(section, key, fallback=fallback)

# Global config instance
config = Config()
