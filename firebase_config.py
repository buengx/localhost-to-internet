"""
Firebase configuration and utilities for static site state management.
"""
import os
import json
import asyncio
from typing import Dict, Any, Optional
import aiohttp

class FirebaseStateManager:
    """
    Manages state storage for static sites using Firebase Realtime Database.
    """
    
    def __init__(self, firebase_url: str, auth_token: Optional[str] = None):
        """
        Initialize Firebase state manager.
        
        Args:
            firebase_url: Firebase Realtime Database URL
            auth_token: Optional Firebase auth token for authenticated access
        """
        self.firebase_url = firebase_url.rstrip('/')
        self.auth_token = auth_token
        
    async def get_state(self, site_id: str, key: str = None) -> Dict[str, Any]:
        """
        Retrieve state data for a static site.
        
        Args:
            site_id: Unique identifier for the static site
            key: Optional specific key to retrieve, if None returns all state
            
        Returns:
            Dictionary containing the state data
        """
        path = f"/static_sites/{site_id}"
        if key:
            path += f"/{key}"
        
        url = f"{self.firebase_url}{path}.json"
        if self.auth_token:
            url += f"?auth={self.auth_token}"
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data if data is not None else {}
                    elif response.status == 404:
                        return {}
                    else:
                        print(f"Firebase GET error: {response.status}")
                        return {}
            except Exception as e:
                print(f"Firebase GET exception: {e}")
                return {}
    
    async def set_state(self, site_id: str, key: str, value: Any) -> bool:
        """
        Set state data for a static site.
        
        Args:
            site_id: Unique identifier for the static site
            key: State key to set
            value: Value to store
            
        Returns:
            True if successful, False otherwise
        """
        path = f"/static_sites/{site_id}/{key}"
        url = f"{self.firebase_url}{path}.json"
        if self.auth_token:
            url += f"?auth={self.auth_token}"
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(url, json=value) as response:
                    return response.status in [200, 204]
            except Exception as e:
                print(f"Firebase SET exception: {e}")
                return False
    
    async def update_state(self, site_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update multiple state values for a static site.
        
        Args:
            site_id: Unique identifier for the static site
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if successful, False otherwise
        """
        path = f"/static_sites/{site_id}"
        url = f"{self.firebase_url}{path}.json"
        if self.auth_token:
            url += f"?auth={self.auth_token}"
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, json=updates) as response:
                    return response.status in [200, 204]
            except Exception as e:
                print(f"Firebase UPDATE exception: {e}")
                return False
    
    async def delete_state(self, site_id: str, key: str = None) -> bool:
        """
        Delete state data for a static site.
        
        Args:
            site_id: Unique identifier for the static site
            key: Optional specific key to delete, if None deletes all state
            
        Returns:
            True if successful, False otherwise
        """
        path = f"/static_sites/{site_id}"
        if key:
            path += f"/{key}"
            
        url = f"{self.firebase_url}{path}.json"
        if self.auth_token:
            url += f"?auth={self.auth_token}"
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.delete(url) as response:
                    return response.status in [200, 204]
            except Exception as e:
                print(f"Firebase DELETE exception: {e}")
                return False


def load_firebase_config() -> Optional[Dict[str, str]]:
    """
    Load Firebase configuration from environment variables or config file.
    
    Returns:
        Dictionary with Firebase configuration or None if not configured
    """
    # Try environment variables first
    firebase_url = os.getenv('FIREBASE_DATABASE_URL')
    auth_token = os.getenv('FIREBASE_AUTH_TOKEN')
    
    if firebase_url:
        return {
            'firebase_url': firebase_url,
            'auth_token': auth_token
        }
    
    # Try config file
    try:
        with open('firebase_config.json', 'r') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        pass
    
    return None


def is_static_content(content_type: str, response_headers: Dict[str, str], url_path: str) -> bool:
    """
    Determine if the content being served appears to be static.
    
    Args:
        content_type: Content-Type header value
        response_headers: Full response headers
        url_path: The URL path being accessed
        
    Returns:
        True if content appears to be static, False otherwise
    """
    # First check for dynamic indicators that would make any content dynamic
    if _has_dynamic_indicators(response_headers):
        return False
    
    # Static file extensions
    static_extensions = [
        '.html', '.htm', '.css', '.js', '.png', '.jpg', '.jpeg', 
        '.gif', '.svg', '.ico', '.pdf', '.txt', '.xml'
    ]
    
    # Check if URL ends with static extension
    for ext in static_extensions:
        if url_path.lower().endswith(ext):
            return True
    
    # Check content type for typical static content
    static_content_types = [
        'text/html', 'text/css', 'text/javascript', 'application/javascript',
        'image/', 'text/plain', 'text/xml', 'application/xml'
    ]
    
    content_type_lower = content_type.lower()
    for static_type in static_content_types:
        if static_type in content_type_lower:
            return True
    
    # Special case: JSON from API endpoints is typically dynamic
    if 'application/json' in content_type_lower and '/api/' in url_path.lower():
        return False
    elif 'application/json' in content_type_lower:
        return True  # JSON files served statically
    
    return False


def _has_dynamic_indicators(headers: Dict[str, str]) -> bool:
    """
    Check response headers for indicators of dynamic content.
    
    Args:
        headers: Response headers dictionary
        
    Returns:
        True if headers suggest dynamic content, False otherwise
    """
    # Headers that typically indicate dynamic content
    dynamic_indicators = [
        'set-cookie',  # Session cookies
        'x-powered-by',  # Framework headers
        'server'  # Some server headers indicate dynamic processing
    ]
    
    headers_lower = {k.lower(): v for k, v in headers.items()}
    
    for indicator in dynamic_indicators:
        if indicator in headers_lower:
            # Special case for server header - only some values indicate dynamic content
            if indicator == 'server':
                server_value = headers_lower[indicator].lower()
                dynamic_servers = ['php', 'apache', 'nginx', 'express', 'django', 'flask']
                if any(ds in server_value for ds in dynamic_servers):
                    return True
            else:
                return True
    
    return False


def generate_site_id(port: int, host: str = 'localhost') -> str:
    """
    Generate a unique site ID for Firebase storage.
    
    Args:
        port: The port number of the local service
        host: The hostname (default: localhost)
        
    Returns:
        Unique site identifier string
    """
    return f"{host}_{port}".replace('.', '_')