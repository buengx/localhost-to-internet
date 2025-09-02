import asyncio
import websockets
from websockets import Response
import json
import uuid
import ssl
import aiohttp
import base64
import os
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from firebase_config import (
    FirebaseStateManager, load_firebase_config, 
    is_static_content, generate_site_id
)

SESSIONS = {}
WEBSOCKET_TO_CONN_ID = {}
FIREBASE_MANAGER = None

def rewrite_url(url_str, port):
    """
    Rewrites a URL to point back to the proxy, if it's relative or a localhost URL.
    """
    if not url_str or url_str.startswith('data:'):
        return url_str

    parsed = urlparse(url_str)

    # Check if the URL is a candidate for rewriting
    is_localhost = parsed.netloc and parsed.netloc.startswith('localhost')
    is_relative = not parsed.netloc and parsed.path

    if is_localhost or is_relative:
        # Use the path from the original URL
        original_path = parsed.path

        # Base64 encode the path to be used in the new query string
        b64_path = base64.urlsafe_b64encode(original_path.encode()).decode()

        # The new URL for the browser to fetch will be relative to the current page,
        # containing only the proxy query parameters.
        new_query = f"port={port}&path={b64_path}"

        # Construct a new relative URL from scratch
        # This will result in something like "?port=8000&path=L2Fib3V0Lmh0bWw="
        return f"?{new_query}"

    return url_str

async def handle_http_request(session, request_data, websocket, localhost_port):
    """
    Takes a JSON representation of an HTTP request, performs it against localhost,
    and sends the response back through the WebSocket.
    """
    conn_id = request_data.get("conn_id")
    fetch_id = request_data.get("fetchId")

    try:
        method = request_data.get("method", "GET")
        headers = request_data.get("headers", {})
        path = request_data.get("path", "/")
        body_b64 = request_data.get("body")

        body_bytes = base64.b64decode(body_b64) if body_b64 else None

        url = f"http://localhost:{localhost_port}{path}"

        # Remove host header to avoid conflicts
        headers.pop('host', None)
        print(f"Proxying: {method} {path} to localhost:{localhost_port} for fetch_id {fetch_id[:8]}")

        async with session.request(
            method, url, headers=headers, data=body_bytes, allow_redirects=False
        ) as response:

            response_body = await response.read()
            response_headers = {key: value for key, value in response.headers.items()}
            content_type = response_headers.get('content-type', '').lower()

            # Check if this is static content and Firebase is available
            is_static = is_static_content(content_type, response_headers, path)
            if is_static and FIREBASE_MANAGER:
                site_id = generate_site_id(localhost_port)
                print(f"Detected static content for site {site_id}, Firebase state management available")
                # Add Firebase state management metadata to response headers
                response_headers['X-Static-Site-ID'] = site_id
                response_headers['X-Firebase-State-Available'] = 'true'

            # Rewrite HTML links to go through the proxy
            if 'text/html' in content_type:
                print(f"Rewriting HTML links for fetch_id {fetch_id[:8]}")
                soup = BeautifulSoup(response_body, "lxml")

                # If this is a static site with Firebase, inject state management script
                if is_static and FIREBASE_MANAGER:
                    inject_firebase_state_script(soup, generate_site_id(localhost_port))

                tags_to_rewrite = {'a': 'href', 'link': 'href', 'img': 'src', 'script': 'src', 'iframe': 'src'}
                for tag_name, attr_name in tags_to_rewrite.items():
                    for tag in soup.find_all(tag_name, **{attr_name: True}):
                        tag[attr_name] = rewrite_url(tag[attr_name], localhost_port)

                response_body = soup.encode()

            response_body_b64 = base64.b64encode(response_body).decode('utf-8')

            response_data = {
                "type": "http_response", 
                "fetchId": fetch_id, 
                "status": response.status,
                "status_text": response.reason or "", 
                "headers": response_headers, 
                "body": response_body_b64
            }
            
            try:
                await websocket.send(json.dumps(response_data))
            except Exception as e:
                print(f"Failed to send response: {e}")

    except Exception as e:
        print(f"Error handling HTTP request for fetch_id {fetch_id[:8]}: {e}")
        error_response = {
            "type": "http_response", 
            "fetchId": fetch_id, 
            "status": 502, 
            "status_text": "Bad Gateway",
            "headers": {"Content-Type": "text/plain"}, 
            "body": base64.b64encode(f"Proxy error: {e}".encode()).decode()
        }
        try:
            await websocket.send(json.dumps(error_response))
        except Exception as e:
            print(f"Failed to send error response: {e}")

def inject_firebase_state_script(soup, site_id):
    """
    Inject Firebase state management script into HTML content for static sites.
    
    Args:
        soup: BeautifulSoup object of the HTML content
        site_id: Unique identifier for the static site
    """
    # Create Firebase state management script
    firebase_script = soup.new_tag('script')
    firebase_script.string = f"""
// Firebase State Management for Static Sites
window.FirebaseState = {{
    siteId: '{site_id}',
    
    async get(key) {{
        try {{
            const response = await fetch(`/_firebase_state/${{this.siteId}}/${{key || ''}}`, {{
                method: 'GET',
                headers: {{ 'X-Firebase-Request': 'true' }}
            }});
            if (response.ok) {{
                return await response.json();
            }}
            return null;
        }} catch (e) {{
            console.error('Firebase State GET error:', e);
            return null;
        }}
    }},
    
    async set(key, value) {{
        try {{
            const response = await fetch(`/_firebase_state/${{this.siteId}}/${{key}}`, {{
                method: 'PUT',
                headers: {{
                    'Content-Type': 'application/json',
                    'X-Firebase-Request': 'true'
                }},
                body: JSON.stringify(value)
            }});
            return response.ok;
        }} catch (e) {{
            console.error('Firebase State SET error:', e);
            return false;
        }}
    }},
    
    async update(updates) {{
        try {{
            const response = await fetch(`/_firebase_state/${{this.siteId}}`, {{
                method: 'PATCH',
                headers: {{
                    'Content-Type': 'application/json',
                    'X-Firebase-Request': 'true'
                }},
                body: JSON.stringify(updates)
            }});
            return response.ok;
        }} catch (e) {{
            console.error('Firebase State UPDATE error:', e);
            return false;
        }}
    }},
    
    async delete(key) {{
        try {{
            const response = await fetch(`/_firebase_state/${{this.siteId}}/${{key || ''}}`, {{
                method: 'DELETE',
                headers: {{ 'X-Firebase-Request': 'true' }}
            }});
            return response.ok;
        }} catch (e) {{
            console.error('Firebase State DELETE error:', e);
            return false;
        }}
    }}
}};

console.log('Firebase State Management loaded for site:', '{site_id}');
"""
    
    # Insert script before closing head tag, or create head if it doesn't exist
    head = soup.find('head')
    if not head:
        head = soup.new_tag('head')
        if soup.html:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)
    
    head.append(firebase_script)

async def handle_firebase_state_request(path, method, headers, body):
    """
    Handle Firebase state management API requests.
    
    Args:
        path: Request path (expected format: /_firebase_state/site_id/key)
        method: HTTP method
        headers: Request headers
        body: Request body
        
    Returns:
        Tuple of (status_code, response_headers, response_body)
    """
    if not FIREBASE_MANAGER:
        return (503, {"Content-Type": "text/plain"}, "Firebase not configured")
    
    # Parse path: /_firebase_state/site_id/key
    path_parts = path.strip('/').split('/')
    if len(path_parts) < 2 or path_parts[0] != '_firebase_state':
        return (400, {"Content-Type": "text/plain"}, "Invalid Firebase state path")
    
    site_id = path_parts[1]
    key = path_parts[2] if len(path_parts) > 2 else None
    
    try:
        if method == 'GET':
            data = await FIREBASE_MANAGER.get_state(site_id, key)
            return (200, {"Content-Type": "application/json"}, json.dumps(data))
        
        elif method == 'PUT':
            if not key:
                return (400, {"Content-Type": "text/plain"}, "Key required for PUT")
            
            try:
                value = json.loads(body) if body else None
            except json.JSONDecodeError:
                return (400, {"Content-Type": "text/plain"}, "Invalid JSON body")
            
            success = await FIREBASE_MANAGER.set_state(site_id, key, value)
            if success:
                return (200, {"Content-Type": "text/plain"}, "OK")
            else:
                return (500, {"Content-Type": "text/plain"}, "Firebase error")
        
        elif method == 'PATCH':
            try:
                updates = json.loads(body) if body else {{}}
            except json.JSONDecodeError:
                return (400, {"Content-Type": "text/plain"}, "Invalid JSON body")
            
            success = await FIREBASE_MANAGER.update_state(site_id, updates)
            if success:
                return (200, {"Content-Type": "text/plain"}, "OK")
            else:
                return (500, {"Content-Type": "text/plain"}, "Firebase error")
        
        elif method == 'DELETE':
            success = await FIREBASE_MANAGER.delete_state(site_id, key)
            if success:
                return (200, {"Content-Type": "text/plain"}, "OK")
            else:
                return (500, {"Content-Type": "text/plain"}, "Firebase error")
        
        else:
            return (405, {"Content-Type": "text/plain"}, "Method not allowed")
    
    except Exception as e:
        print(f"Firebase state request error: {e}")
        return (500, {"Content-Type": "text/plain"}, f"Internal error: {e}")

async def check_localhost_availability(port, path="/"):
    """
    Check if a localhost service is available on the given port.
    Returns True if available, False otherwise.
    """
    try:
        url = f"http://localhost:{port}{path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as response:
                return True
    except Exception as e:
        print(f"Localhost check failed for port {port}: {e}")
        return False

async def cleanup_session(conn_id, reason=""):
    print(f"Cleaning up session {conn_id[:8]}. Reason: {reason}")
    session = SESSIONS.pop(conn_id, None)
    if session:
        browser_ws = session.get('browser')
        
        if browser_ws and browser_ws in WEBSOCKET_TO_CONN_ID:
            del WEBSOCKET_TO_CONN_ID[browser_ws]
            try:
                await browser_ws.close(1000, f"Connection closed: {reason}")
            except Exception as e:
                print(f"Error closing WebSocket: {e}")

async def handler(websocket):
    # Get the path from the WebSocket request
    path = websocket.request.path if hasattr(websocket, 'request') else '/'
    
    try:
        query_params = parse_qs(urlparse(path).query)
        port_str = query_params.get('port', [None])[0]
        path_param_b64 = query_params.get('path', ['L2'])[0]  # 'L2' is base64 for '/'

        if not port_str:
            await websocket.close(1003, "Port must be specified.")
            return

        port = int(port_str)

        # Decode the base64 path
        try:
            path_param = base64.urlsafe_b64decode(path_param_b64).decode('utf-8')
        except Exception as e:
            print(f"Failed to decode path parameter '{path_param_b64}': {e}")
            path_param = '/'

        # Check if the localhost service is available
        print(f"Checking availability of localhost:{port}{path_param}")
        if not await check_localhost_availability(port, path_param):
            await websocket.send(json.dumps({
                "type": "error", 
                "message": f"No service available on localhost:{port}. Please ensure your local server is running.",
                "status": 404
            }))
            await websocket.close(1000, "Service not available")
            return

        # Create a new session for this browser connection
        conn_id = str(uuid.uuid4())
        
        # Create persistent cookie jar for this session
        cookie_jar = aiohttp.CookieJar(unsafe=True)
        session = aiohttp.ClientSession(cookie_jar=cookie_jar)
        
        SESSIONS[conn_id] = {
            "browser": websocket, 
            "port": port, 
            "session": session
        }
        WEBSOCKET_TO_CONN_ID[websocket] = conn_id

        print(f"Session {conn_id[:8]} created for localhost:{port}")
        await websocket.send(json.dumps({
            "type": "connection_ready", 
            "conn_id": conn_id,
            "status": 200
        }))

        # Handle incoming messages from the browser
        async for message_str in websocket:
            try:
                message = json.loads(message_str)
                
                if message.get("type") == "http_request":
                    # Check if this is a Firebase state management request
                    request_path = message.get("path", "/")
                    if request_path.startswith("/_firebase_state/"):
                        method = message.get("method", "GET")
                        headers = message.get("headers", {})
                        body_b64 = message.get("body")
                        body = base64.b64decode(body_b64).decode('utf-8') if body_b64 else None
                        
                        # Handle Firebase state request
                        status_code, response_headers, response_body = await handle_firebase_state_request(
                            request_path, method, headers, body
                        )
                        
                        # Send response back through WebSocket
                        response_data = {
                            "type": "http_response",
                            "fetchId": message.get("fetchId"),
                            "status": status_code,
                            "status_text": "OK" if status_code < 400 else "Error",
                            "headers": response_headers,
                            "body": base64.b64encode(response_body.encode()).decode('utf-8')
                        }
                        await websocket.send(json.dumps(response_data))
                    else:
                        # Handle normal HTTP request
                        session_data = SESSIONS.get(conn_id)
                        if session_data:
                            asyncio.create_task(handle_http_request(
                                session_data["session"], 
                                message, 
                                websocket, 
                                port
                            ))
                        
            except json.JSONDecodeError:
                print(f"Received non-JSON message, ignoring: {message_str[:100]}")
            except Exception as e:
                print(f"Error processing message: {e}")

    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"An error occurred in handler: {e}")
    finally:
        # Clean up the session
        conn_id = WEBSOCKET_TO_CONN_ID.get(websocket)
        if conn_id:
            session_data = SESSIONS.get(conn_id)
            if session_data and session_data.get("session"):
                await session_data["session"].close()
            await cleanup_session(conn_id, "Browser disconnected")

async def serve_static_file(path, start_response):
    """Serve static files (index.html, script.js) for HTTP requests"""
    # Remove leading slash and handle empty path
    if path == "/" or path == "":
        path = "index.html"
    elif path.startswith("/"):
        path = path[1:]
    
    # Security check - only allow specific files
    allowed_files = ["index.html", "script.js"]
    if path not in allowed_files:
        return ("404 Not Found", "text/plain", "File not found")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        if path.endswith(".html"):
            content_type = "text/html"
        elif path.endswith(".js"):
            content_type = "application/javascript"
        else:
            content_type = "text/plain"
            
        return ("200 OK", content_type, content)
    except FileNotFoundError:
        return ("404 Not Found", "text/plain", "File not found")

async def process_request(connection, request):
    """Process incoming requests - serve static files for HTTP, delegate WebSocket to handler"""
    # Check if this is a WebSocket upgrade request by looking at headers
    connection_header = request.headers.get("connection", "").lower()
    upgrade_header = request.headers.get("upgrade", "").lower()
    
    if "upgrade" in connection_header and upgrade_header == "websocket":
        # This is a WebSocket request, let the WebSocket server handle it
        return None
    
    # This is an HTTP request, serve static files
    status, content_type, content = await serve_static_file(request.path, None)
    
    # Return a proper Response object
    if status == "200 OK":
        status_code = 200
        reason_phrase = "OK"
    else:
        status_code = 404
        reason_phrase = "Not Found"
        
    from websockets.datastructures import Headers
    headers = Headers()
    headers["Content-Type"] = content_type
    headers["Content-Length"] = str(len(content.encode("utf-8")))
    
    return Response(status_code, reason_phrase, headers, content.encode("utf-8"))

async def main():
    global FIREBASE_MANAGER
    
    # Initialize Firebase if configured
    firebase_config = load_firebase_config()
    if firebase_config:
        try:
            FIREBASE_MANAGER = FirebaseStateManager(
                firebase_config['firebase_url'],
                firebase_config.get('auth_token')
            )
            print(f"Firebase state management initialized: {firebase_config['firebase_url']}")
        except Exception as e:
            print(f"Warning: Firebase initialization failed: {e}")
            print("Continuing without Firebase state management...")
    else:
        print("Firebase not configured. Static sites will not have state persistence.")
        print("To enable Firebase, set FIREBASE_DATABASE_URL environment variable or create firebase_config.json")
    
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain("cert.pem", keyfile="key.pem")
    except FileNotFoundError:
        print("Error: cert.pem or key.pem not found.")
        print("Please generate them by running: openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'")
        return

    print("Starting secure relay server on wss://localhost:8765")
    print("Web interface available at https://localhost:8765/")
    
    # Use process_request to handle both HTTP and WebSocket requests
    async with websockets.serve(
        handler, 
        "localhost", 
        8765, 
        ssl=ssl_context,
        process_request=process_request
    ):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down.")
