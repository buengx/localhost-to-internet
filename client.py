import asyncio
import websockets
import json
import argparse
import base64

# {conn_id: (asyncio.StreamReader, asyncio.StreamWriter, asyncio.Task)}
TCP_SESSIONS = {}

async def forward_to_websocket(conn_id, reader, websocket):
    """Reads from a TCP socket and forwards data to the server via WebSocket."""
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break

            payload = base64.b64encode(data).decode('utf-8')

            await websocket.send(json.dumps({
                "type": "data",
                "conn_id": conn_id,
                "payload": payload
            }))
    except asyncio.CancelledError:
        pass # Normal cancellation
    except Exception as e:
        print(f"Error reading from TCP for {conn_id}: {e}")
    finally:
        print(f"Local TCP connection for {conn_id} closed.")
        # Notify the server to clean up the session from its end
        if websocket.open:
            await websocket.send(json.dumps({"type": "close_connection", "conn_id": conn_id}))
        if conn_id in TCP_SESSIONS:
            del TCP_SESSIONS[conn_id]


async def handle_server_messages(websocket, local_host, local_port):
    """Handles incoming messages from the server on the control WebSocket."""
    async for message_str in websocket:
        try:
            message = json.loads(message_str)
            msg_type = message.get("type")
            conn_id = message.get("conn_id")

            if not conn_id:
                continue

            if msg_type == "new_connection":
                print(f"Received request for new connection: {conn_id}")
                try:
                    reader, writer = await asyncio.open_connection(local_host, local_port)
                    task = asyncio.create_task(forward_to_websocket(conn_id, reader, websocket))
                    TCP_SESSIONS[conn_id] = (reader, writer, task)
                    print(f"TCP connection for {conn_id} established to {local_host}:{local_port}")
                except Exception as e:
                    print(f"Failed to connect to {local_host}:{local_port}: {e}")
                    await websocket.send(json.dumps({"type": "error", "conn_id": conn_id, "message": "Failed to connect to local service"}))

            elif msg_type == "data":
                if conn_id in TCP_SESSIONS:
                    _, writer, _ = TCP_SESSIONS[conn_id]
                    payload = message.get("payload", "")
                    try:
                        data = base64.b64decode(payload)
                        writer.write(data)
                        await writer.drain()
                    except (TypeError, ValueError) as e:
                        print(f"Base64 Decode Error for {conn_id}: {e}")
                else:
                    # This can happen if the close message is in flight
                    print(f"Ignoring data for closed or unknown session {conn_id}")

            elif msg_type == "close_connection":
                print(f"Server requested to close connection: {conn_id}")
                if conn_id in TCP_SESSIONS:
                    reader, writer, task = TCP_SESSIONS.pop(conn_id)
                    task.cancel()
                    if not writer.is_closing():
                        writer.close()
                        await writer.wait_closed()
        except json.JSONDecodeError:
            print(f"Could not decode message from server: {message_str}")
        except Exception as e:
            print(f"Error in message handler: {e}")


async def main(args):
    """Main function for the agent."""
    uri = f"ws://{args.host}:{args.port}"

    while True:
        try:
            print(f"Connecting to relay server at {uri}...")
            async with websockets.connect(uri) as websocket:
                print("Connection established. Registering...")
                await websocket.send(json.dumps({
                    "type": "register",
                    "port": args.local_port
                }))

                response_str = await websocket.recv()
                response = json.loads(response_str)

                if response.get("type") == "registered":
                    print(f"Agent successfully registered for port {args.local_port}")
                    await handle_server_messages(websocket, args.local_host, args.local_port)
                else:
                    print(f"Failed to register agent: {response.get('message')}")
                    break
        except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError) as e:
            print(f"Connection to server failed: {e}. Retrying in 5 seconds...")
        except Exception as e:
            print(f"An unexpected error occurred in main loop: {e}")

        # Cleanup any lingering tasks before retrying
        for conn_id, (reader, writer, task) in list(TCP_SESSIONS.items()):
            task.cancel()
            if not writer.is_closing():
                writer.close()
        TCP_SESSIONS.clear()

        await asyncio.sleep(5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Localhost to Internet Tunnel Agent")
    parser.add_argument("--host", type=str, default="localhost", help="Relay server host")
    parser.add_argument("--port", type=int, default=8765, help="Relay server port")
    parser.add_argument("--local-port", type=int, required=True, help="Local port to forward")
    parser.add_argument("--local-host", type=str, default="localhost", help="The destination host of the local service")
    args = parser.parse_args()

    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        print("\nAgent shutting down.")
