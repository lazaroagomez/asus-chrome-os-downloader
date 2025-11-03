from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QSpinBox, QCheckBox, QPushButton, QLabel, QGroupBox
)
from PyQt6.QtCore import Qt

from .config import Config


class SettingsDialog(QDialog):
    """Settings dialog for application configuration"""
    
    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.init_ui()
    
    def init_ui(self):
        """Initialize UI"""
        layout = QVBoxLayout(self)
        
        # Download settings group
        download_group = QGroupBox("Download Settings")
        download_layout = QFormLayout()
        
        # Max concurrent downloads
        self.concurrent_spin = QSpinBox()
        self.concurrent_spin.setRange(1, 10)
        self.concurrent_spin.setValue(self.config.max_concurrent_downloads)
        download_layout.addRow("Max Concurrent Downloads:", self.concurrent_spin)
        
        # Download speed limit
        self.speed_limit_spin = QSpinBox()
        self.speed_limit_spin.setRange(0, 100000)
        self.speed_limit_spin.setSuffix(" KB/s")
        self.speed_limit_spin.setSpecialValueText("Unlimited")
        if self.config.max_download_speed:
            self.speed_limit_spin.setValue(self.config.max_download_speed)
        else:
            self.speed_limit_spin.setValue(0)
        download_layout.addRow("Download Speed Limit:", self.speed_limit_spin)
        
        download_group.setLayout(download_layout)
        layout.addWidget(download_group)
        
        # General settings group
        general_group = QGroupBox("General Settings")
        general_layout = QFormLayout()
        
        # Auto check for updates
        self.auto_check_checkbox = QCheckBox()
        self.auto_check_checkbox.setChecked(self.config.get('auto_check_updates', True))
        general_layout.addRow("Auto-check for new versions:", self.auto_check_checkbox)
        
        general_group.setLayout(general_layout)
        layout.addWidget(general_group)
        
        # Info label
        info_label = QLabel(
            "Note: Changes to download settings will apply to new downloads.\n"
            "Active downloads will continue with previous settings."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        button_layout.addWidget(save_btn)
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def save_settings(self):
        """Save settings and close dialog"""
        self.config.max_concurrent_downloads = self.concurrent_spin.value()
        
        speed_limit = self.speed_limit_spin.value()
        self.config.max_download_speed = speed_limit if speed_limit > 0 else None
        
        self.config.set('auto_check_updates', self.auto_check_checkbox.isChecked())
        
        self.accept()
