import asyncio

async def handle_echo(reader, writer):
    addr = writer.get_extra_info('peername')
    print(f"New connection from {addr}")

    while True:
        data = await reader.read(1024)
        if not data:
            break

        message = data.decode()
        print(f"Received {message!r} from {addr!r}")

        print(f"Sending: {message!r}")
        writer.write(data)
        await writer.drain()

    print(f"Closing connection from {addr}")
    writer.close()
    await writer.wait_closed()

async def main():
    server = await asyncio.start_server(
        handle_echo, '127.0.0.1', 8000)

    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')

    async with server:
        await server.serve_forever()

if __name__ == '__main__':
    print("Starting echo server on port 8000")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Echo server shut down.")
