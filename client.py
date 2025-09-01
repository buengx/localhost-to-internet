import asyncio
import websockets
import json
import argparse
import base64
import ssl
import aiohttp

async def handle_http_request(session, conn_id, request_data, websocket, local_host, local_port):
    """
    Takes a JSON representation of an HTTP request, performs it, and sends the response back.
    """
    try:
        method = request_data.get("method", "GET")
        headers = request_data.get("headers", {})
        path = request_data.get("path", "/")
        body_b64 = request_data.get("body")

        body_bytes = base64.b64decode(body_b64) if body_b64 else None
        url = f"http://{local_host}:{local_port}{path}"

        # Important headers to remove/modify for a proxy
        headers.pop('host', None) # Let aiohttp set the correct host header

        print(f"Proxying: {method} {path} for conn_id {conn_id[:8]}")

        async with session.request(
            method, url, headers=headers, data=body_bytes, allow_redirects=False
        ) as response:
            response_body = await response.read()
            response_body_b64 = base64.b64encode(response_body).decode('utf-8')
            response_headers = {key: value for key, value in response.headers.items()}

            response_data = {
                "type": "http_response",
                "conn_id": conn_id,
                "status": response.status,
                "status_text": response.reason or "",
                "headers": response_headers,
                "body": response_body_b64
            }
            if websocket.open:
                await websocket.send(json.dumps(response_data))

    except Exception as e:
        print(f"Error handling HTTP request for {conn_id[:8]}: {e}")
        error_response = {
            "type": "http_response",
            "conn_id": conn_id,
            "status": 502,
            "status_text": "Bad Gateway",
            "headers": {"Content-Type": "text/plain"},
            "body": base64.b64encode(f"Proxy error: {e}".encode()).decode()
        }
        if websocket.open:
            await websocket.send(json.dumps(error_response))

async def handle_server_messages(websocket, local_host, local_port):
    """
    Listens for messages from the server and dispatches tasks.
    """
    async with aiohttp.ClientSession(cookie_jar=aiohttp.DummyCookieJar()) as session:
        async for message_str in websocket:
            try:
                message = json.loads(message_str)
                msg_type = message.get("type")

                if msg_type == "http_request":
                    asyncio.create_task(
                        handle_http_request(
                            session, message.get("conn_id"), message, websocket, local_host, local_port
                        )
                    )
            except Exception as e:
                print(f"Error processing message from server: {e}")

async def main(args):
    """Main function for the agent."""
    uri = f"wss://{args.host}:{args.port}/?type=agent&port={args.local_port}"
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.load_verify_locations(args.certfile)

    while True:
        try:
            print(f"Connecting to secure relay server at {uri}...")
            async with websockets.connect(uri, ssl=ssl_context) as websocket:
                print("Connection established. Waiting for registration confirmation...")
                response = json.loads(await websocket.recv())

                if response.get("type") == "agent_registered":
                    print(f"Agent successfully registered for port {args.local_port}")
                    await handle_server_messages(websocket, args.local_host, args.local_port)
                else:
                    print(f"Failed to register agent: {response.get('message', 'Unknown error')}")
                    break
        except Exception as e:
            print(f"Connection to server failed: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Localhost to Internet HTTP Proxy Agent")
    parser.add_argument("--host", type=str, default="localhost", help="Relay server host")
    parser.add_argument("--port", type=int, default=8765, help="Relay server port")
    parser.add_argument("--local-port", type=int, required=True, help="Local port of the service to forward")
    parser.add_argument("--local-host", type=str, default="localhost", help="Host of the service to forward")
    parser.add_argument("--certfile", type=str, default="cert.pem", help="Path to the server's SSL certificate file")
    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nAgent shutting down.")
    except FileNotFoundError:
        print(f"\nError: Certificate file '{args.certfile}' not found.")
