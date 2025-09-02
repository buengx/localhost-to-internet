# localhost-to-internet

A secure proxy system that allows you to expose your localhost servers to the internet through a relay server. Perfect for sharing local development environments, APIs, or applications with others.

## How it works

1. **Relay Server**: A WebSocket server that acts as a secure relay between browsers and local agents
2. **Python Agent**: Runs on your local machine and connects to your localhost services
3. **Web Interface**: A simple webpage that connects users to your localhost through the relay

## Quick Start

### 1. Start the Relay Server

```bash
python3 server.py
```

The server will start on `wss://localhost:8765` and requires SSL certificates (`cert.pem` and `key.pem`).

### 2. Run the Python Agent

```bash
python3 client.py --local-port 3000
```

This connects your localhost:3000 to the relay server.

### 3. Access via Web Interface

Open the web interface in your browser:
- **Homepage**: Visit the webpage without parameters to see a form where you can enter localhost addresses
- **Direct Access**: Use URL parameters like `?port=3000&path=L2FwaS90ZXN0` (where path is base64-encoded)

## Usage Examples

### Homepage Interface
Visit the webpage without parameters to see a user-friendly form:
- Enter addresses like `localhost:3000`, `localhost:8080/api`, or `127.0.0.1:5000/dashboard`
- The form will automatically construct the proper proxy URL

### Direct URL Parameters
- `?port=3000&path=Lw==` - Access port 3000, root path (/)
- `?port=8080&path=L2FwaQ==` - Access port 8080, /api path
- `?port=5000&path=L2Rhc2hib2FyZA==` - Access port 5000, /dashboard path

## Dependencies

```bash
pip3 install aiohttp websockets beautifulsoup4 lxml
```

## SSL Certificate Setup

Generate self-signed certificates for the relay server:

```bash
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj '/CN=localhost'
```

## Architecture

- **WebSocket Relay**: Secure communication between browsers and agents
- **HTTP Proxy**: Agents handle HTTP requests to localhost and return responses
- **Link Rewriting**: Automatic rewriting of HTML links to work through the proxy
- **Base64 Encoding**: Paths are base64-encoded in URLs for safe transport