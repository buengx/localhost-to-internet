#!/usr/bin/env python3
"""
Unit tests for Firebase integration in the localhost-to-internet proxy.
"""

import unittest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add the current directory to the path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from firebase_config import (
    FirebaseStateManager, is_static_content, 
    generate_site_id, _has_dynamic_indicators
)

class TestStaticContentDetection(unittest.TestCase):
    """Test the static content detection functionality."""
    
    def test_static_html_detection(self):
        """Test detection of static HTML files."""
        # Static HTML file
        self.assertTrue(is_static_content(
            'text/html', 
            {'Server': 'SimpleHTTP/0.6 Python/3.12.3'}, 
            '/index.html'
        ))
        
        # Static HTML with clean headers
        self.assertTrue(is_static_content(
            'text/html', 
            {'Content-Type': 'text/html'}, 
            '/about.html'
        ))
    
    def test_dynamic_content_detection(self):
        """Test detection of dynamic content."""
        # HTML with session cookie (dynamic)
        self.assertFalse(is_static_content(
            'text/html',
            {'Set-Cookie': 'sessionid=abc123'},
            '/dashboard.html'
        ))
        
        # HTML with framework header (dynamic)
        self.assertFalse(is_static_content(
            'text/html',
            {'X-Powered-By': 'Express'},
            '/app.html'
        ))
        
        # API endpoint (dynamic)
        self.assertFalse(is_static_content(
            'application/json',
            {'X-Powered-By': 'Express'},
            '/api/users'
        ))
        
        # JSON API without framework header (still dynamic due to path)
        self.assertFalse(is_static_content(
            'application/json',
            {},
            '/api/data'
        ))
    
    def test_static_assets_detection(self):
        """Test detection of static assets."""
        # CSS file
        self.assertTrue(is_static_content(
            'text/css',
            {},
            '/styles.css'
        ))
        
        # JavaScript file
        self.assertTrue(is_static_content(
            'application/javascript',
            {},
            '/script.js'
        ))
        
        # Image file
        self.assertTrue(is_static_content(
            'image/png',
            {},
            '/logo.png'
        ))
        
        # Static JSON data file
        self.assertTrue(is_static_content(
            'application/json',
            {},
            '/data.json'
        ))
    
    def test_dynamic_indicators(self):
        """Test the dynamic content indicators function."""
        # Session cookies indicate dynamic content
        self.assertTrue(_has_dynamic_indicators({
            'Set-Cookie': 'sessionid=123'
        }))
        
        # Framework headers indicate dynamic content
        self.assertTrue(_has_dynamic_indicators({
            'X-Powered-By': 'Express'
        }))
        
        # Some server headers indicate dynamic content
        self.assertTrue(_has_dynamic_indicators({
            'Server': 'nginx/1.18.0'
        }))
        
        # Static server headers don't indicate dynamic content
        self.assertFalse(_has_dynamic_indicators({
            'Server': 'SimpleHTTP/0.6 Python/3.12.3'
        }))
        
        # Clean headers don't indicate dynamic content
        self.assertFalse(_has_dynamic_indicators({
            'Content-Type': 'text/html',
            'Content-Length': '1024'
        }))

class TestSiteIdGeneration(unittest.TestCase):
    """Test site ID generation for Firebase storage."""
    
    def test_basic_site_id(self):
        """Test basic site ID generation."""
        site_id = generate_site_id(3000)
        self.assertEqual(site_id, 'localhost_3000')
    
    def test_custom_host_site_id(self):
        """Test site ID generation with custom host."""
        site_id = generate_site_id(8080, '127.0.0.1')
        self.assertEqual(site_id, '127_0_0_1_8080')

class TestFirebaseStateManager(unittest.TestCase):
    """Test the Firebase state management functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.firebase_url = "https://test-project-default-rtdb.firebaseio.com"
        self.manager = FirebaseStateManager(self.firebase_url)
    
    @patch('aiohttp.ClientSession')
    async def test_get_state_success(self, mock_session_class):
        """Test successful state retrieval."""
        # Mock the response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={'key1': 'value1', 'key2': 'value2'})
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Test get_state
        result = await self.manager.get_state('test_site')
        
        self.assertEqual(result, {'key1': 'value1', 'key2': 'value2'})
        mock_session.get.assert_called_once()
    
    @patch('aiohttp.ClientSession')
    async def test_get_state_not_found(self, mock_session_class):
        """Test state retrieval when data doesn't exist."""
        # Mock 404 response
        mock_response = AsyncMock()
        mock_response.status = 404
        
        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Test get_state
        result = await self.manager.get_state('nonexistent_site')
        
        self.assertEqual(result, {})
    
    @patch('aiohttp.ClientSession')
    async def test_set_state_success(self, mock_session_class):
        """Test successful state setting."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.put.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Test set_state
        result = await self.manager.set_state('test_site', 'test_key', 'test_value')
        
        self.assertTrue(result)
        mock_session.put.assert_called_once()
    
    @patch('aiohttp.ClientSession')
    async def test_update_state_success(self, mock_session_class):
        """Test successful state update."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.patch.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Test update_state
        updates = {'key1': 'new_value1', 'key2': 'new_value2'}
        result = await self.manager.update_state('test_site', updates)
        
        self.assertTrue(result)
        mock_session.patch.assert_called_once()
    
    @patch('aiohttp.ClientSession')
    async def test_delete_state_success(self, mock_session_class):
        """Test successful state deletion."""
        # Mock successful response
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.delete.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Test delete_state
        result = await self.manager.delete_state('test_site', 'test_key')
        
        self.assertTrue(result)
        mock_session.delete.assert_called_once()

def run_async_test(test_func):
    """Helper to run async test functions."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(test_func())
    finally:
        loop.close()

if __name__ == '__main__':
    # Run async tests
    firebase_tests = TestFirebaseStateManager()
    firebase_tests.setUp()
    
    print("Running Firebase state manager tests...")
    
    # Test each async method
    async_tests = [
        firebase_tests.test_get_state_success,
        firebase_tests.test_get_state_not_found,
        firebase_tests.test_set_state_success,
        firebase_tests.test_update_state_success,
        firebase_tests.test_delete_state_success
    ]
    
    for test in async_tests:
        try:
            run_async_test(test)
            print(f"✓ {test.__name__}")
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
    
    # Run sync tests
    print("\nRunning synchronous tests...")
    unittest.main(argv=[''], exit=False, verbosity=2)