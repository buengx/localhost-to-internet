import asyncio
import websockets
import json
import uuid

# {port: agent_websocket}
AGENTS = {}
# {conn_id: {'browser': browser_websocket, 'agent': agent_websocket}}
SESSIONS = {}
# {websocket: conn_id}
WEBSOCKET_TO_CONN_ID = {}

async def cleanup_session(conn_id, reason=""):
    """Gracefully cleans up a session."""
    print(f"Cleaning up session {conn_id}. Reason: {reason}")
    session = SESSIONS.pop(conn_id, None)
    if session:
        browser_ws = session.get('browser')
        agent_ws = session.get('agent')

        if browser_ws and browser_ws in WEBSOCKET_TO_CONN_ID:
            del WEBSOCKET_TO_CONN_ID[browser_ws]
            if browser_ws.open:
                await browser_ws.send(json.dumps({"type": "terminated", "reason": f"Connection closed: {reason}"}))
                await browser_ws.close()

        # We don't remove the agent from WEBSOCKET_TO_CONN_ID because one agent can have multiple sessions
        # But we do notify the agent to close the specific TCP connection.
        if agent_ws and agent_ws.open:
             await agent_ws.send(json.dumps({"type": "close_connection", "conn_id": conn_id}))

async def handler(websocket, path):
    """
    Manages connections from agents and browsers.
    """
    # This handler can now manage multiple types of clients on the same endpoint
    # It will determine the type based on the initial message received.
    # We will also track which websocket is an agent for cleanup purposes.
    is_agent = False
    registered_port = None

    try:
        # The first message determines the client type and intent
        message_str = await websocket.recv()
        message = json.loads(message_str)
        msg_type = message.get("type")

        if msg_type == "register": # Agent registers itself
            port = message.get("port")
            if not isinstance(port, int):
                await websocket.close(1003, "Port must be an integer.")
                return

            if port in AGENTS:
                await websocket.send(json.dumps({"type": "error", "message": f"Port {port} is already being served."}))
                await websocket.close()
                return

            AGENTS[port] = websocket
            is_agent = True
            registered_port = port
            print(f"Agent registered for port {port}")
            await websocket.send(json.dumps({"type": "registered", "port": port}))

        elif msg_type == "request_connection": # Browser requests a connection
            port = message.get("port")
            if not isinstance(port, int):
                await websocket.close(1003, "Port must be an integer.")
                return

            if port not in AGENTS:
                await websocket.send(json.dumps({"type": "error", "message": f"No agent is serving port {port}."}))
                await websocket.close()
                return

            agent_ws = AGENTS[port]
            conn_id = str(uuid.uuid4())

            SESSIONS[conn_id] = {"browser": websocket, "agent": agent_ws}
            WEBSOCKET_TO_CONN_ID[websocket] = conn_id

            await agent_ws.send(json.dumps({"type": "new_connection", "conn_id": conn_id}))
            await websocket.send(json.dumps({"type": "connection_ready", "conn_id": conn_id}))
            print(f"Session {conn_id} created for port {port}")

        else:
            await websocket.close(1003, "Unsupported message type")
            return

        # Main message loop for data relaying
        async for message_str in websocket:
            message = json.loads(message_str)
            msg_type = message.get("type")

            if msg_type != "data":
                continue

            current_conn_id = message.get("conn_id")
            if not current_conn_id or current_conn_id not in SESSIONS:
                continue

            session = SESSIONS[current_conn_id]
            payload = message.get("payload")

            if websocket == session["browser"]:
                recipient_ws = session["agent"]
                # Agent needs to know which connection the data belongs to
                await recipient_ws.send(json.dumps({"type": "data", "conn_id": current_conn_id, "payload": payload}))
            elif websocket == session["agent"]:
                recipient_ws = session["browser"]
                # Browser doesn't need the conn_id in the payload, it just receives the data
                await recipient_ws.send(json.dumps({"type": "data", "payload": payload}))

    except websockets.exceptions.ConnectionClosed as e:
        print(f"Connection closed: {websocket.remote_address} ({e})")
    except Exception as e:
        print(f"An error occurred in handler: {e}")
    finally:
        if is_agent:
            if registered_port and registered_port in AGENTS:
                del AGENTS[registered_port]
                print(f"Agent for port {registered_port} deregistered.")
                # Clean up all sessions associated with this disconnected agent
                sessions_to_clean = [sid for sid, s in SESSIONS.items() if s['agent'] == websocket]
                for sid in sessions_to_clean:
                    await cleanup_session(sid, "Agent disconnected")
        else:
            # This was a browser client
            conn_id = WEBSOCKET_TO_CONN_ID.get(websocket)
            if conn_id:
                await cleanup_session(conn_id, "Browser disconnected")


async def main():
    print("Starting smart relay server on ws://localhost:8765")
    async with websockets.serve(handler, "localhost", 8765):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server shutting down.")
