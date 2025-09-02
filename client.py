import asyncio
import websockets
import json
import argparse
import base64
import ssl
import aiohttp
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse

def rewrite_url(url_str, local_port):
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
        new_query = f"port={local_port}&path={b64_path}"

        # Construct a new relative URL from scratch
        # This will result in something like "?port=8000&path=L2Fib3V0Lmh0bWw="
        return f"?{new_query}"

    return url_str


async def handle_http_request(session, request_data, websocket):
    """
    Takes a JSON representation of an HTTP request, performs it, rewrites links if necessary,
    and sends the response back.
    """
    conn_id = request_data.get("conn_id")
    fetch_id = request_data.get("fetchId")

    try:
        method = request_data.get("method", "GET")
        headers = request_data.get("headers", {})
        path = request_data.get("path", "/")
        body_b64 = request_data.get("body")

        body_bytes = base64.b64decode(body_b64) if body_b64 else None

        local_host = websocket.local_host
        local_port = websocket.local_port
        url = f"http://{local_host}:{local_port}{path}"

        headers.pop('host', None)
        print(f"Proxying: {method} {path} for fetch_id {fetch_id[:8]}")

        async with session.request(
            method, url, headers=headers, data=body_bytes, allow_redirects=False
        ) as response:

            response_body = await response.read()
            response_headers = {key: value for key, value in response.headers.items()}
            content_type = response_headers.get('content-type', '').lower()

            if 'text/html' in content_type:
                print(f"Rewriting HTML links for fetch_id {fetch_id[:8]}")
                soup = BeautifulSoup(response_body, "lxml")

                tags_to_rewrite = {'a': 'href', 'link': 'href', 'img': 'src', 'script': 'src', 'iframe': 'src'}
                for tag_name, attr_name in tags_to_rewrite.items():
                    for tag in soup.find_all(tag_name, **{attr_name: True}):
                        tag[attr_name] = rewrite_url(tag[attr_name], local_port)

                response_body = soup.encode()

            response_body_b64 = base64.b64encode(response_body).decode('utf-8')

            response_data = {
                "type": "http_response", "fetchId": fetch_id, "status": response.status,
                "status_text": response.reason or "", "headers": response_headers, "body": response_body_b64
            }
            if websocket.open:
                await websocket.send(json.dumps(response_data))

    except Exception as e:
        print(f"Error handling HTTP request for fetch_id {fetch_id[:8]}: {e}")
        error_response = {
            "type": "http_response", "fetchId": fetch_id, "status": 502, "status_text": "Bad Gateway",
            "headers": {"Content-Type": "text/plain"}, "body": base64.b64encode(f"Proxy error: {e}".encode()).decode()
        }
        if websocket.open:
            await websocket.send(json.dumps(error_response))

async def handle_server_messages(websocket):
    # Use a persistent cookie jar to maintain sessions across requests
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async for message_str in websocket:
            try:
                message = json.loads(message_str)
                if message.get("type") == "http_request":
                    asyncio.create_task(handle_http_request(session, message, websocket))
            except Exception as e:
                print(f"Error processing message from server: {e}")

async def main(args):
    uri = f"wss://{args.host}:{args.port}/?type=agent&port={args.local_port}"
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations(args.certfile)

    while True:
        try:
            print(f"Connecting to secure relay server at {uri}...")
            async with websockets.connect(uri, ssl=ssl_context) as websocket:
                websocket.local_host = args.local_host
                websocket.local_port = args.local_port

                print("Connection established. Waiting for registration confirmation...")
                response = json.loads(await websocket.recv())

                if response.get("type") == "agent_registered":
                    print(f"Agent successfully registered for port {args.local_port}")
                    await handle_server_messages(websocket)
                else:
                    print(f"Failed to register agent: {response.get('message', 'Unknown error')}")
                    break
        except Exception as e:
            print(f"Connection to server failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Localhost to Internet HTTP Proxy Agent")
    parser.add_argument("--host", default="localhost", help="Relay server hostname (default: localhost)")
    parser.add_argument("--port", type=int, default=8765, help="Relay server port (default: 8765)")
    parser.add_argument("--local-host", default="localhost", help="Local server hostname (default: localhost)")
    parser.add_argument("--local-port", type=int, required=True, help="Local server port to proxy")
    parser.add_argument("--certfile", default="cert.pem", help="SSL certificate file (default: cert.pem)")
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nAgent shutting down.")
    except FileNotFoundError:
        print(f"\nError: Certificate file '{args.certfile}' not found.")
