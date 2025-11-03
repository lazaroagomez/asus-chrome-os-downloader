import requests
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RecoveryImage:
    """Represents a Chrome OS recovery image"""
    codename: str
    brand_name: str
    platform: str
    form_factor: str
    is_aue: bool
    download_url: str
    version: str
    milestone: str
    file_size: Optional[int] = None
    md5_hash: Optional[str] = None
    sha1_hash: Optional[str] = None
    
    @property
    def support_status(self) -> str:
        return "Discontinued" if self.is_aue else "Supported"
    
    @property
    def filename(self) -> str:
        """Extract filename from download URL"""
        if self.download_url:
            filename = self.download_url.split('/')[-1]
            # Remove query parameters if present
            if '?' in filename:
                filename = filename.split('?')[0]
            return filename
        # Default to .bin extension if no URL (common for recovery images)
        return f"{self.codename}_{self.version}.bin"


class ChromeOSAPIClient:
    """Client for fetching Chrome OS recovery images from the API"""
    
    API_URL = "https://chromiumdash.appspot.com/cros/fetch_serving_builds?deviceCategory=ChromeOS"
    
    def __init__(self):
        self.cache: Optional[Dict] = None
        self.last_fetch: Optional[datetime] = None
    
    def fetch_builds(self, force_refresh: bool = False) -> Dict:
        """Fetch builds from API with caching"""
        if not force_refresh and self.cache and self.last_fetch:
            # Use cached data if available and not forcing refresh
            return self.cache
        
        try:
            response = requests.get(self.API_URL, timeout=30)
            response.raise_for_status()
            data = response.json()
            self.cache = data
            self.last_fetch = datetime.now()
            return data
        except requests.RequestException as e:
            raise Exception(f"Failed to fetch builds from API: {e}")
    
    def get_devices_by_manufacturer(self, manufacturer: str = "ASUS", 
                                     stable_only: bool = True) -> List[RecoveryImage]:
        """Filter devices by manufacturer and extract recovery images"""
        data = self.fetch_builds()
        builds = data.get('builds', {})
        devices = []
        
        for codename, details in builds.items():
            # Handle Structure 2: Parent board with models
            if 'models' in details:
                for model_codename, model_details in details.get('models', {}).items():
                    brand_names = model_details.get('brandNames', [])
                    if any(manufacturer.upper() in name.upper() for name in brand_names):
                        # Combine parent and model details
                        combined = self._combine_details(details, model_details)
                        display_codename = f"{codename}-{model_codename}"
                        
                        # Extract recovery images
                        images = self._extract_recovery_images(
                            display_codename, combined, stable_only
                        )
                        devices.extend(images)
            
            # Handle Structure 1: Standalone device
            else:
                brand_names = details.get('brandNames', [])
                if any(manufacturer.upper() in name.upper() for name in brand_names):
                    images = self._extract_recovery_images(
                        codename, details, stable_only
                    )
                    devices.extend(images)
        
        return devices
    
    def _combine_details(self, parent: Dict, model: Dict) -> Dict:
        """Combine parent and model details"""
        combined = parent.copy()
        if 'models' in combined:
            del combined['models']
        combined.update(model)
        return combined
    
    def _extract_recovery_images(self, codename: str, details: Dict, 
                                  stable_only: bool) -> List[RecoveryImage]:
        """Extract recovery images from device details"""
        images = []
        brand_names = details.get('brandNames', [])
        brand_name = brand_names[0] if brand_names else codename
        
        # Get platform and form factor
        platform = self._get_platform(details)
        form_factor = self._get_form_factor(details)
        is_aue = details.get('isAue', False)
        
        # Get version from servingStable if available
        serving_stable = details.get('servingStable', {})
        chrome_version = serving_stable.get('chromeVersion', '') if serving_stable else ''
        os_version = serving_stable.get('version', '') if serving_stable else ''
        
        # Extract stable recovery from pushRecoveries (latest milestone)
        push_recoveries = details.get('pushRecoveries', {})
        if push_recoveries and stable_only:
            # Get the latest milestone recovery
            valid_milestones = [k for k in push_recoveries.keys() if k.isdigit()]
            if valid_milestones:
                latest_milestone = max(valid_milestones, key=int)
                recovery_data = push_recoveries[latest_milestone]
                
                # Use servingStable version if available, otherwise use milestone
                version = chrome_version if chrome_version else f"M{latest_milestone}"
                
                image = self._create_image_from_recovery(
                    codename, brand_name, platform, form_factor,
                    is_aue, recovery_data, latest_milestone, version
                )
                if image:
                    images.append(image)
        
        return images
    
    def _get_platform(self, details: Dict) -> str:
        """Extract platform from device details"""
        # Check direct platform key
        if 'platform' in details:
            return details['platform']
        
        # Check in brandNameToFormattedDeviceMap
        formatted_map = details.get('brandNameToFormattedDeviceMap', {})
        if formatted_map:
            first_device = next(iter(formatted_map.values()))
            return first_device.get('platform', 'Unknown')
        
        return 'Unknown'
    
    def _get_form_factor(self, details: Dict) -> str:
        """Extract form factor from device details"""
        # Check direct formFactor key
        if 'formFactor' in details:
            return details['formFactor']
        
        # Check in brandNameToFormattedDeviceMap
        formatted_map = details.get('brandNameToFormattedDeviceMap', {})
        if formatted_map:
            first_device = next(iter(formatted_map.values()))
            return first_device.get('formFactor', 'Unknown')
        
        return 'Unknown'
    

    
    def _create_image_from_recovery(self, codename: str, brand_name: str,
                                     platform: str, form_factor: str,
                                     is_aue: bool, recovery_data, 
                                     milestone: str, version: str = '') -> Optional[RecoveryImage]:
        """Create RecoveryImage from pushRecoveries data"""
        # recovery_data is a string (URL)
        if isinstance(recovery_data, str):
            download_url = recovery_data
        else:
            # If it's a dict (future-proofing)
            download_url = recovery_data.get('url', '') if isinstance(recovery_data, dict) else ''
        
        if not download_url:
            return None
        
        # Use provided version or default to milestone
        if not version:
            version = f"M{milestone}"
        
        return RecoveryImage(
            codename=codename,
            brand_name=brand_name,
            platform=platform,
            form_factor=form_factor,
            is_aue=is_aue,
            download_url=download_url,
            version=version,
            milestone=milestone,
            file_size=None,
            md5_hash=None,
            sha1_hash=None
        )
