#!/usr/bin/env python3
"""
Test script to demonstrate Firebase state management for static sites.
This creates a simple static HTML page that uses the Firebase state functionality.
"""

import os
import shutil
from pathlib import Path

def create_test_static_site():
    """Create a simple static site for testing Firebase integration."""
    
    # Create test directory
    test_dir = Path("/tmp/test_static_site")
    if test_dir.exists():
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    
    # Create a simple HTML page that uses Firebase state
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Firebase State Test</title>
    <style>
        body { 
            font-family: sans-serif; 
            max-width: 600px; 
            margin: 50px auto; 
            padding: 20px; 
        }
        .state-display {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 8px;
            margin: 10px 0;
        }
        button {
            background: #007cba;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            margin: 5px;
        }
        button:hover {
            background: #005a8b;
        }
        input, textarea {
            width: 100%;
            padding: 8px;
            margin: 5px 0;
            border: 1px solid #ccc;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <h1>Firebase State Management Test</h1>
    <p>This static page demonstrates Firebase state persistence through the localhost-to-internet proxy.</p>
    
    <div class="state-display">
        <h3>Current State:</h3>
        <pre id="stateDisplay">No state loaded yet...</pre>
    </div>
    
    <div>
        <h3>Set State:</h3>
        <input type="text" id="keyInput" placeholder="Key (e.g., user_name)">
        <input type="text" id="valueInput" placeholder="Value (e.g., John Doe)">
        <button onclick="setState()">Set State</button>
    </div>
    
    <div>
        <h3>Actions:</h3>
        <button onclick="loadState()">Refresh State</button>
        <button onclick="incrementCounter()">Increment Counter</button>
        <button onclick="clearState()">Clear All State</button>
    </div>
    
    <div>
        <h3>Visit Counter:</h3>
        <div id="visitCounter">Loading...</div>
    </div>

    <script>
        // Wait for Firebase state to be available
        window.addEventListener('load', async function() {
            if (typeof FirebaseState !== 'undefined') {
                console.log('Firebase State is available!');
                await loadState();
                await incrementVisitCounter();
            } else {
                console.log('Firebase State not available - this may be because Firebase is not configured or this is not being served through the proxy');
                document.getElementById('stateDisplay').textContent = 'Firebase State not available. Make sure you are accessing this through the localhost-to-internet proxy with Firebase configured.';
            }
        });
        
        async function loadState() {
            if (typeof FirebaseState === 'undefined') {
                alert('Firebase State not available');
                return;
            }
            
            try {
                const state = await FirebaseState.get();
                document.getElementById('stateDisplay').textContent = JSON.stringify(state, null, 2);
            } catch (error) {
                console.error('Error loading state:', error);
                document.getElementById('stateDisplay').textContent = 'Error loading state: ' + error.message;
            }
        }
        
        async function setState() {
            if (typeof FirebaseState === 'undefined') {
                alert('Firebase State not available');
                return;
            }
            
            const key = document.getElementById('keyInput').value;
            const value = document.getElementById('valueInput').value;
            
            if (!key || !value) {
                alert('Please enter both key and value');
                return;
            }
            
            try {
                await FirebaseState.set(key, value);
                document.getElementById('keyInput').value = '';
                document.getElementById('valueInput').value = '';
                await loadState();
                alert('State saved successfully!');
            } catch (error) {
                console.error('Error setting state:', error);
                alert('Error setting state: ' + error.message);
            }
        }
        
        async function incrementCounter() {
            if (typeof FirebaseState === 'undefined') {
                alert('Firebase State not available');
                return;
            }
            
            try {
                const currentState = await FirebaseState.get();
                const currentCount = currentState.counter || 0;
                await FirebaseState.set('counter', currentCount + 1);
                await loadState();
            } catch (error) {
                console.error('Error incrementing counter:', error);
            }
        }
        
        async function incrementVisitCounter() {
            if (typeof FirebaseState === 'undefined') {
                document.getElementById('visitCounter').textContent = 'Firebase not available';
                return;
            }
            
            try {
                const currentState = await FirebaseState.get();
                const visits = (currentState.visit_count || 0) + 1;
                await FirebaseState.set('visit_count', visits);
                document.getElementById('visitCounter').textContent = `This page has been visited ${visits} time(s)`;
            } catch (error) {
                console.error('Error updating visit counter:', error);
                document.getElementById('visitCounter').textContent = 'Error updating visit counter';
            }
        }
        
        async function clearState() {
            if (typeof FirebaseState === 'undefined') {
                alert('Firebase State not available');
                return;
            }
            
            if (confirm('Are you sure you want to clear all state?')) {
                try {
                    await FirebaseState.delete();
                    await loadState();
                    document.getElementById('visitCounter').textContent = 'Visit counter reset';
                    alert('State cleared successfully!');
                } catch (error) {
                    console.error('Error clearing state:', error);
                    alert('Error clearing state: ' + error.message);
                }
            }
        }
    </script>
</body>
</html>"""
    
    # Write the HTML file
    with open(test_dir / "index.html", "w") as f:
        f.write(html_content)
    
    # Create a simple HTTP server script
    server_script = """#!/usr/bin/env python3
import http.server
import socketserver
import os

os.chdir('/tmp/test_static_site')

PORT = 3000
Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"Static site server running at http://localhost:{PORT}/")
    print("Access it through the proxy at: https://localhost:8765/?port=3000&path=Lw==")
    httpd.serve_forever()
"""
    
    with open(test_dir / "serve.py", "w") as f:
        f.write(server_script)
    
    os.chmod(test_dir / "serve.py", 0o755)
    
    print(f"Test static site created in {test_dir}")
    print(f"To test:")
    print(f"1. Run: python3 {test_dir}/serve.py")
    print(f"2. Run the proxy server: python3 server.py")
    print(f"3. Configure Firebase (optional)")
    print(f"4. Access: https://localhost:8765/?port=3000&path=Lw==")
    
    return test_dir

if __name__ == "__main__":
    create_test_static_site()