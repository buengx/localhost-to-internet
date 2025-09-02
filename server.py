import asyncio
import websockets
import json
import uuid
import ssl
import aiohttp
import base64
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

SESSIONS = {}
WEBSOCKET_TO_CONN_ID = {}

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

            # Rewrite HTML links to go through the proxy
            if 'text/html' in content_type:
                print(f"Rewriting HTML links for fetch_id {fetch_id[:8]}")
                soup = BeautifulSoup(response_body, "lxml")

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
            
            if websocket.open:
                await websocket.send(json.dumps(response_data))

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
        if websocket.open:
            await websocket.send(json.dumps(error_response))

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
            if browser_ws.open:
                await browser_ws.close(1000, f"Connection closed: {reason}")

async def handler(websocket):
    # Get the path from the WebSocket request
    path = websocket.request.path if hasattr(websocket, 'request') else '/'
    
    try:
        query_params = parse_qs(urlparse(path).query)
        port_str = query_params.get('port', [None])[0]
        path_param = query_params.get('path', ['/'])[0]

        if not port_str:
            await websocket.close(1003, "Port must be specified.")
            return

        port = int(port_str)

        # Check if the localhost service is available
        print(f"Checking availability of localhost:{port}")
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
                    # Handle HTTP request directly
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

async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain("cert.pem", keyfile="key.pem")
    except FileNotFoundError:
        print("Error: cert.pem or key.pem not found.")
        print("Please generate them by running: openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'")
        return

    print("Starting secure relay server on wss://localhost:8765")
    async with websockets.serve(handler, "localhost", 8765, ssl=ssl_context):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer shutting down.")
