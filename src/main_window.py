from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLabel, QComboBox,
    QLineEdit, QProgressBar, QFileDialog, QMessageBox, QGroupBox,
    QSpinBox, QCheckBox, QSplitter, QTextEdit, QTabWidget, QAbstractItemView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QMetaObject, Q_ARG
from PyQt6.QtGui import QIcon, QColor, QPalette
from typing import List, Optional
import os
import sys
from datetime import datetime

from .api_client import ChromeOSAPIClient, RecoveryImage
from .download_manager import HttpxDownloadManager, DownloadTask, DownloadStatus
from .config import Config



class DeviceLoadWorker(QThread):
    """Worker thread for loading devices from API"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, api_client: ChromeOSAPIClient, manufacturer: str):
        super().__init__()
        self.api_client = api_client
        self.manufacturer = manufacturer
    
    def run(self):
        try:
            devices = self.api_client.get_devices_by_manufacturer(
                self.manufacturer, stable_only=True
            )
            self.finished.emit(devices)
        except Exception as e:
            self.error.emit(str(e))





class MainWindow(QMainWindow):
    """Main application window"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chrome OS Recovery Image Manager")
        
        # Initialize components
        self.config = Config()

        self.api_client = ChromeOSAPIClient()
        
        self.download_manager = HttpxDownloadManager(
            max_concurrent_downloads=self.config.max_concurrent_downloads,
            max_download_speed=self.config.max_download_speed,
            completion_callback=self.on_download_completed
        )
        
        self.download_start_times: dict = {}
        

        
        # Set update callback - use thread-safe method
        self.download_manager.set_update_callback(self.on_download_update)
        
        # Data
        self.all_devices: List[RecoveryImage] = []
        self.filtered_devices: List[RecoveryImage] = []
        self.load_worker: Optional[DeviceLoadWorker] = None


        self.select_all_state = False

        
        # Apply theme
        self.apply_theme()
        
        # Setup UI
        self.init_ui()
        
        # Load window size with validation
        width = max(800, min(self.config.get('window_width', 1200), 3840))
        height = max(600, min(self.config.get('window_height', 800), 2160))
        self.resize(width, height)
        
        # Start loading devices
        if self.config.get('auto_check_updates', True):
            QTimer.singleShot(500, self.load_devices)
        

    
    def init_ui(self):
        """Initialize user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        


        # Top controls
        controls_group = self.create_controls_section()
        layout.addWidget(controls_group)
        
        # Splitter for device list and downloads
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Device table
        device_group = QGroupBox("Available Recovery Images")
        device_layout = QVBoxLayout()
        self.device_table = self.create_device_table()
        device_layout.addWidget(self.device_table)
        device_group.setLayout(device_layout)
        splitter.addWidget(device_group)
        
        # Download queue
        download_group = QGroupBox("Download Queue")
        download_layout = QVBoxLayout()
        self.download_table = self.create_download_table()
        download_layout.addWidget(self.download_table)
        
        # Download controls
        dl_controls = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.clicked.connect(self.pause_selected_download)
        self.resume_btn = QPushButton("Resume")
        self.resume_btn.clicked.connect(self.resume_selected_download)
        self.clear_completed_btn = QPushButton("Clear Completed")
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)
        
        dl_controls.addWidget(self.pause_btn)
        dl_controls.addWidget(self.resume_btn)
        dl_controls.addWidget(self.clear_completed_btn)
        dl_controls.addStretch()
        
        download_layout.addLayout(dl_controls)
        download_group.setLayout(download_layout)
        splitter.addWidget(download_group)
        
        layout.addWidget(splitter)
        
        # Status bar
        self.statusBar().showMessage("Ready")

        # Branding in status bar
        branding_label = QLabel("SQE Department - Albert")
        branding_label.setStyleSheet("font-size: 10px; color: #AAAAAA;")
        self.statusBar().addPermanentWidget(branding_label)
    
    def create_controls_section(self) -> QGroupBox:
        """Create controls section"""
        group = QGroupBox("Controls")
        layout = QVBoxLayout()
        
        # Row 1: Search and theme toggle
        row0 = QHBoxLayout()
        
        row0.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search devices...")
        self.search_box.textChanged.connect(self.apply_filters)
        row0.addWidget(self.search_box)
        

        
        layout.addLayout(row0)
        
        # Row 1: Refresh and filters
        row1 = QHBoxLayout()
        
        self.refresh_btn = QPushButton("Refresh Device List")
        self.refresh_btn.clicked.connect(self.load_devices)
        row1.addWidget(self.refresh_btn)
        
        row1.addWidget(QLabel("Manufacturer:"))
        self.manufacturer_combo = QComboBox()
        self.manufacturer_combo.addItems(["ASUS", "HP", "Acer", "Dell", "Lenovo", "Samsung"])
        self.manufacturer_combo.setCurrentText(self.config.manufacturer_filter)
        self.manufacturer_combo.currentTextChanged.connect(self.on_manufacturer_changed)
        row1.addWidget(self.manufacturer_combo)
        
        row1.addWidget(QLabel("Support Status:"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(["All", "Supported", "Discontinued"])
        self.status_combo.currentTextChanged.connect(self.apply_filters)
        row1.addWidget(self.status_combo)
        
        row1.addWidget(QLabel("Form Factor:"))
        self.form_factor_combo = QComboBox()
        self.form_factor_combo.addItem("All")
        self.form_factor_combo.currentTextChanged.connect(self.apply_filters)
        row1.addWidget(self.form_factor_combo)
        
        row1.addWidget(QLabel("Downloaded:"))
        self.downloaded_combo = QComboBox()
        self.downloaded_combo.addItems(["Show All", "Hide Downloaded", "Show Only Downloaded"])
        self.downloaded_combo.setCurrentText("Hide Downloaded")
        self.downloaded_combo.currentTextChanged.connect(self.apply_filters)
        row1.addWidget(self.downloaded_combo)
        
        row1.addStretch()
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_toggled)
        row1.addWidget(self.select_all_btn)

        download_selected_btn = QPushButton("Download Selected")
        download_selected_btn.clicked.connect(self.download_selected)
        row1.addWidget(download_selected_btn)
        

        
        layout.addLayout(row1)
        
        # Row 2: Download path and settings
        row2 = QHBoxLayout()
        
        row2.addWidget(QLabel("Download Path:"))
        self.path_edit = QLineEdit(self.config.download_path)
        self.path_edit.setReadOnly(True)
        row2.addWidget(self.path_edit)
        
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_download_path)
        row2.addWidget(browse_btn)
        
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self.show_settings)
        row2.addWidget(settings_btn)
        
        layout.addLayout(row2)
        
        group.setLayout(layout)
        return group
    
    def create_device_table(self) -> QTableWidget:
        """Create device table"""
        table = QTableWidget()
        table.setColumnCount(8)
        table.setHorizontalHeaderLabels([
            "Select", "Brand Name", "Codename", "Platform", "Form Factor",
            "Support Status", "Version", "Action"
        ])
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)


        
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        
        return table
    
    def create_download_table(self) -> QTableWidget:
        """Create download queue table"""
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Filename", "Status", "Progress", "Speed", "ETA", "Size"
        ])
        
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(False)
        
        return table
    
    def load_devices(self):
        """Load devices from API in background thread"""
        if self.load_worker and self.load_worker.isRunning():
            return
        
        self.refresh_btn.setEnabled(False)
        self.statusBar().showMessage("Loading devices from API...")
        
        manufacturer = self.manufacturer_combo.currentText()
        self.load_worker = DeviceLoadWorker(self.api_client, manufacturer)
        self.load_worker.finished.connect(self.on_devices_loaded)
        self.load_worker.error.connect(self.on_load_error)
        self.load_worker.start()
    
    def on_devices_loaded(self, devices: List[RecoveryImage]):
        """Handle devices loaded from API"""
        self.all_devices = devices

        
        # Update form factor filter
        form_factors = set()
        for device in devices:
            if device.form_factor:
                form_factors.add(device.form_factor)
        
        current = self.form_factor_combo.currentText()
        self.form_factor_combo.clear()
        self.form_factor_combo.addItem("All")
        self.form_factor_combo.addItems(sorted(form_factors))
        if current in form_factors or current == "All":
            self.form_factor_combo.setCurrentText(current)
        
        self.apply_filters()
        self.refresh_btn.setEnabled(True)
        self.statusBar().showMessage(f"Loaded {len(devices)} devices")
    
    def on_load_error(self, error: str):
        """Handle API load error"""

        QMessageBox.critical(self, "Error", f"Failed to load devices: {error}")
        self.refresh_btn.setEnabled(True)
        self.statusBar().showMessage("Error loading devices")
    
    def apply_filters(self):
        """Apply filters to device list"""
        status_filter = self.status_combo.currentText()
        form_factor_filter = self.form_factor_combo.currentText()
        downloaded_filter = self.downloaded_combo.currentText()
        search_text = self.search_box.text().lower()
        
        self.filtered_devices = []
        for device in self.all_devices:
            # Status filter
            if status_filter == "Supported" and device.is_aue:
                continue
            if status_filter == "Discontinued" and not device.is_aue:
                continue
            
            # Form factor filter
            if form_factor_filter != "All" and device.form_factor != form_factor_filter:
                continue
            
            # Search filter
            if search_text:
                searchable = f"{device.brand_name} {device.codename} {device.platform} {device.form_factor} {device.version}".lower()
                if search_text not in searchable:
                    continue
            
            # Downloaded filter - check if file exists
            if downloaded_filter != "Show All":
                support_folder = "Supported" if not device.is_aue else "Discontinued"
                form_factor_folder = self.sanitize_folder_name(device.form_factor)
                brand_folder = self.sanitize_folder_name(device.brand_name)
                file_path = os.path.join(
                    self.config.download_path,
                    support_folder,
                    form_factor_folder,
                    brand_folder,
                    device.filename
                )
                file_exists = os.path.exists(file_path)
                
                if downloaded_filter == "Hide Downloaded" and file_exists:
                    continue
                if downloaded_filter == "Show Only Downloaded" and not file_exists:
                    continue
            
            self.filtered_devices.append(device)
        
        self.populate_device_table()
    
    def populate_device_table(self):
        """Populate device table with filtered devices"""
        self.device_table.setRowCount(len(self.filtered_devices))
        
        for row, device in enumerate(self.filtered_devices):
            # Checkbox for batch selection
            checkbox = QCheckBox()
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            self.device_table.setCellWidget(row, 0, checkbox_widget)
            
            self.device_table.setItem(row, 1, QTableWidgetItem(device.brand_name))
            self.device_table.setItem(row, 2, QTableWidgetItem(device.codename))
            self.device_table.setItem(row, 3, QTableWidgetItem(device.platform))
            self.device_table.setItem(row, 4, QTableWidgetItem(device.form_factor))
            self.device_table.setItem(row, 5, QTableWidgetItem(device.support_status))
            self.device_table.setItem(row, 6, QTableWidgetItem(device.version))
            
            # Download button with dropdown for overwrite option
            button_widget = QWidget()
            button_layout = QHBoxLayout(button_widget)
            button_layout.setContentsMargins(2, 2, 2, 2)
            
            download_btn = QPushButton("Download")
            download_btn.clicked.connect(lambda checked, r=row: self.download_device(r))
            button_layout.addWidget(download_btn)
            
            overwrite_btn = QPushButton("Overwrite")
            overwrite_btn.clicked.connect(lambda checked, r=row: self.download_device(r, force_overwrite=True))
            button_layout.addWidget(overwrite_btn)
            
            self.device_table.setCellWidget(row, 7, button_widget)
    
    def sanitize_folder_name(self, name: str) -> str:
        """Sanitize a string for use as a folder name"""
        # Remove invalid characters for Windows paths
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        sanitized = name
        for char in invalid_chars:
            sanitized = sanitized.replace(char, '-')
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip(' .')
        # Limit length to avoid path issues
        return sanitized[:100]
    
    def download_device(self, row: int, force_overwrite: bool = False):
        """Add device to download queue"""
        if row >= len(self.filtered_devices):
            return
        
        device = self.filtered_devices[row]
        
        if not device.download_url:
            QMessageBox.warning(self, "Warning", "No download URL available for this device")
            return
        
        # Create folder structure: Support Status/Form Factor/Brand Name/
        support_folder = "Supported" if not device.is_aue else "Discontinued"
        form_factor_folder = self.sanitize_folder_name(device.form_factor)
        # Use sanitized brand name for folder
        brand_folder = self.sanitize_folder_name(device.brand_name)
        
        destination = os.path.join(
            self.config.download_path,
            support_folder,
            form_factor_folder,
            brand_folder
        )
        
        # Create download task
        task = DownloadTask(
            url=device.download_url,
            destination=destination,
            filename=device.filename,
            metadata={
                'device': device.brand_name,
                'codename': device.codename,
                'version': device.version
            }
        )
        
        # Check if already exists
        if task.exists() and not force_overwrite:
            reply = QMessageBox.question(
                self, "File Exists",
                f"File {device.filename} already exists. Download anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                return
            # If yes, delete the existing file
            try:
                os.remove(task.full_path)
            except:
                pass
        
        # Add to download manager
        success = self.download_manager.add_download(task)
        if success:
            # Track start time for completion logging
            import time
            self.download_start_times[task.filename] = time.time()

            self.update_download_table()
            self.statusBar().showMessage(f"Added {device.filename} to download queue")
        else:
            if task.status == DownloadStatus.COMPLETED:
                self.statusBar().showMessage(f"{device.filename} already downloaded")
            else:
                QMessageBox.critical(self, "Error", f"Failed to add download: {task.error_message}")
    
    def on_download_update(self):
        """Thread-safe callback for download updates"""
        # Schedule UI update on main thread
        QTimer.singleShot(0, self.update_download_table)
    
    def on_download_completed(self, task):
        """Callback when a download completes"""
        import time
        from datetime import datetime
        start_time = self.download_start_times.get(task.filename, time.time())
        duration = time.time() - start_time

        

        
        # Clean up start time tracking
        if task.filename in self.download_start_times:
            del self.download_start_times[task.filename]
    
    def update_download_table(self):
        """Update download table with current tasks"""
        tasks = self.download_manager.tasks
        self.download_table.setRowCount(len(tasks))
        
        for row, task in enumerate(tasks):
            self.download_table.setItem(row, 0, QTableWidgetItem(task.filename))
            self.download_table.setItem(row, 1, QTableWidgetItem(task.status.value))
            
            # Progress bar
            progress_bar = QProgressBar()
            progress_bar.setValue(int(task.progress))
            self.download_table.setCellWidget(row, 2, progress_bar)
            
            self.download_table.setItem(row, 3, QTableWidgetItem(self.format_speed(task.download_speed)))
            self.download_table.setItem(row, 4, QTableWidgetItem(self.format_eta(task.eta)))
            self.download_table.setItem(row, 5, QTableWidgetItem(self.format_size(task.total_size)))
    
    def format_speed(self, speed: int) -> str:
        """Format download speed"""
        if speed == 0:
            return "-"
        if speed < 1024:
            return f"{speed} B/s"
        elif speed < 1024 * 1024:
            return f"{speed / 1024:.1f} KB/s"
        else:
            return f"{speed / (1024 * 1024):.1f} MB/s"
    
    def format_eta(self, seconds: int) -> str:
        """Format ETA"""
        if seconds == 0:
            return "-"
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours}h {minutes}m"
    
    def get_selected_tasks(self) -> List[DownloadTask]:
        """Get selected tasks from the download table."""
        selected_rows = {item.row() for item in self.download_table.selectedItems()}
        return [self.download_manager.tasks[row] for row in sorted(selected_rows)]

    def format_size(self, size: int) -> str:
        """Format file size"""
        if size == 0:
            return "-"
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    
    def pause_selected_download(self):
        """Pause selected downloads"""
        tasks = self.get_selected_tasks()
        for task in tasks:
            self.download_manager.pause_download(task)
    
    def resume_selected_download(self):
        """Resume selected downloads"""
        tasks = self.get_selected_tasks()
        for task in tasks:
            self.download_manager.resume_download(task)
    



    

    
    def clear_completed_downloads(self):
        """Clear completed downloads from queue"""
        self.download_manager.cleanup_completed()
        self.update_download_table()
    
    def browse_download_path(self):
        """Browse for download directory"""
        path = QFileDialog.getExistingDirectory(
            self, "Select Download Directory",
            self.config.download_path
        )
        if path:
            self.config.download_path = path
            self.path_edit.setText(path)
    
    def on_manufacturer_changed(self, manufacturer: str):
        """Handle manufacturer filter change"""
        self.config.manufacturer_filter = manufacturer
        self.load_devices()
    
    def show_settings(self):
        """Show settings dialog"""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self.config, self)
        if dialog.exec():
            # Get existing tasks
            existing_tasks = self.download_manager.tasks

            # Reload download manager with new settings
            self.download_manager = HttpxDownloadManager(
                max_concurrent_downloads=self.config.max_concurrent_downloads,
                max_download_speed=self.config.max_download_speed,
                completion_callback=self.on_download_completed
            )
            self.download_manager.set_update_callback(self.on_download_update)

            # Re-add existing tasks
            for task in existing_tasks:
                self.download_manager.add_download(task)
            
            self.update_download_table()
    

    
    def apply_theme(self):
        """Apply dark theme"""
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setPalette(palette)
    
    def download_selected(self):
        """Download all selected devices"""
        selected_rows = []
        for row in range(self.device_table.rowCount()):
            checkbox_widget = self.device_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox and checkbox.isChecked():
                    selected_rows.append(row)
        
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select devices to download")
            return
        
        reply = QMessageBox.question(
            self, "Download Selected",
            f"Download {len(selected_rows)} selected devices?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            count = 0
            for row in selected_rows:
                device = self.filtered_devices[row]
                if device.download_url:
                    self.download_device(row, force_overwrite=False)
                    count += 1
            
            self.statusBar().showMessage(f"Added {count} downloads to queue")
    
    def download_all_filtered(self):
        """Download all filtered devices"""
        if not self.filtered_devices:
            QMessageBox.information(self, "No Devices", "No devices to download")
            return
        
        reply = QMessageBox.question(
            self, "Download All",
            f"Download all {len(self.filtered_devices)} filtered devices?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            count = 0
            for i in range(len(self.filtered_devices)):
                device = self.filtered_devices[i]
                if device.download_url:  # Only download if URL exists
                    self.download_device(i, force_overwrite=False)
                    count += 1
            
            self.statusBar().showMessage(f"Added {count} downloads to queue")

    def select_all_toggled(self):
        """Select or deselect all items in the device table."""
        self.select_all_state = not self.select_all_state
        for row in range(self.device_table.rowCount()):
            checkbox_widget = self.device_table.cellWidget(row, 0)
            if checkbox_widget:
                checkbox = checkbox_widget.findChild(QCheckBox)
                if checkbox:
                    checkbox.setChecked(self.select_all_state)
        self.select_all_btn.setText("Deselect All" if self.select_all_state else "Select All")
    

    
    def closeEvent(self, event):
        """Handle window close event"""
        # Save window size
        self.config.set('window_width', self.width())
        self.config.set('window_height', self.height())
        
        # No cleanup needed for httpx
        

        event.accept()
