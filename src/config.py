import json
import os
from pathlib import Path
from typing import Optional


class Config:
    """Manages application configuration"""
    
    DEFAULT_CONFIG = {
        'download_path': str(Path.home() / 'Downloads' / 'ChromeOS_Recovery'),
        'max_concurrent_downloads': 1,
        'max_download_speed': None,  # None = unlimited
        'manufacturer_filter': 'ASUS',
        'auto_check_updates': True,
        'window_width': 1200,
        'window_height': 800,
    }
    
    def __init__(self, config_file: str = 'config.json'):
        self.config_file = config_file
        self.settings = self.DEFAULT_CONFIG.copy()
        self.load()
    
    def load(self):
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Error loading config: {e}")
    
    def save(self):
        """Save configuration to file"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def get(self, key: str, default=None):
        """Get configuration value"""
        return self.settings.get(key, default)
    
    def set(self, key: str, value):
        """Set configuration value"""
        self.settings[key] = value
        self.save()
    
    @property
    def download_path(self) -> str:
        return self.settings['download_path']
    
    @download_path.setter
    def download_path(self, value: str):
        self.set('download_path', value)
    
    @property
    def max_concurrent_downloads(self) -> int:
        return self.settings['max_concurrent_downloads']
    
    @max_concurrent_downloads.setter
    def max_concurrent_downloads(self, value: int):
        self.set('max_concurrent_downloads', value)
    
    @property
    def max_download_speed(self) -> Optional[int]:
        return self.settings['max_download_speed']
    
    @max_download_speed.setter
    def max_download_speed(self, value: Optional[int]):
        self.set('max_download_speed', value)
    
    @property
    def manufacturer_filter(self) -> str:
        return self.settings['manufacturer_filter']
    
    @manufacturer_filter.setter
    def manufacturer_filter(self, value: str):
        self.set('manufacturer_filter', value)
