import sys
import atexit
import signal
from PyQt6.QtWidgets import QApplication
from src.main_window import MainWindow


def main():
    """Main entry point for the application"""
    app = QApplication(sys.argv)
    app.setApplicationName("Chrome OS Recovery Manager")
    app.setOrganizationName("ChromeOSRecovery")
    
    # Set application style
    app.setStyle('Fusion')
    
    window = MainWindow()
    window.show()
    
    # No cleanup needed for httpx downloads
    
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
