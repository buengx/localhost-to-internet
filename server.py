import asyncio
import websockets
import json
import uuid
import ssl
from urllib.parse import urlparse, parse_qs

AGENTS = {}
SESSIONS = {}
WEBSOCKET_TO_CONN_ID = {}

async def cleanup_session(conn_id, reason=""):
    print(f"Cleaning up session {conn_id[:8]}. Reason: {reason}")
    session = SESSIONS.pop(conn_id, None)
    if session:
        browser_ws = session.get('browser')
        agent_ws = session.get('agent')

        if browser_ws and browser_ws in WEBSOCKET_TO_CONN_ID:
            del WEBSOCKET_TO_CONN_ID[browser_ws]
            if browser_ws.open:
                await browser_ws.close(1000, f"Connection closed: {reason}")

        if agent_ws and agent_ws.open:
             await agent_ws.send(json.dumps({"type": "close_connection", "conn_id": conn_id}))

async def handler(websocket, path):
    is_agent = False
    registered_port = None

    try:
        query_params = parse_qs(urlparse(path).query)
        client_type = query_params.get('type', [None])[0]
        port_str = query_params.get('port', [None])[0]

        if not port_str:
            await websocket.close(1003, "Port must be specified.")
            return

        port = int(port_str)

        if client_type == 'agent':
            if port in AGENTS:
                await websocket.send(json.dumps({"type": "error", "message": f"Port {port} already served."}))
                await websocket.close()
                return

            AGENTS[port] = websocket
            is_agent = True
            registered_port = port
            print(f"Agent registered for port {port}")
            await websocket.send(json.dumps({"type": "agent_registered", "port": port}))

        else:
            path_param = query_params.get('path', ['/'])[0]
            if port not in AGENTS:
                await websocket.send(json.dumps({"type": "error", "message": f"No agent for port {port}."}))
                await websocket.close()
                return

            agent_ws = AGENTS[port]
            conn_id = str(uuid.uuid4())

            SESSIONS[conn_id] = {"browser": websocket, "agent": agent_ws}
            WEBSOCKET_TO_CONN_ID[websocket] = conn_id

            # The new HTTP proxy model doesn't strictly need new_connection,
            # but it's useful for the agent to know a browser has connected.
            # We'll leave it for potential future use or debugging.
            await agent_ws.send(json.dumps({
                "type": "new_connection", "conn_id": conn_id, "path": path_param
            }))
            await websocket.send(json.dumps({"type": "connection_ready", "conn_id": conn_id}))
            print(f"Session {conn_id[:8]} created for port {port} with path {path_param}")

        # Generic message relay loop
        async for message_str in websocket:
            try:
                message = json.loads(message_str)
                conn_id = message.get("conn_id")

                if not conn_id or conn_id not in SESSIONS:
                    continue

                session = SESSIONS[conn_id]

                if websocket == session.get("browser"):
                    recipient_ws = session.get("agent")
                else: # It's from the agent
                    recipient_ws = session.get("browser")

                if recipient_ws and recipient_ws.open:
                    await recipient_ws.send(message_str)
            except json.JSONDecodeError:
                print(f"Received non-JSON message, ignoring: {message_str[:100]}")


    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception as e:
        print(f"An error occurred in handler: {e}")
    finally:
        if is_agent:
            if registered_port is not None and AGENTS.get(registered_port) == websocket:
                del AGENTS[registered_port]
                print(f"Agent for port {registered_port} deregistered.")
                sessions_to_clean = [sid for sid, s in SESSIONS.items() if s.get('agent') == websocket]
                for sid in sessions_to_clean:
                    await cleanup_session(sid, "Agent disconnected")
        else:
            conn_id = WEBSOCKET_TO_CONN_ID.get(websocket)
            if conn_id:
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
