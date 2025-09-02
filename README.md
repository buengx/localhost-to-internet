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

## Firebase State Management for Static Sites

The proxy now includes Firebase Realtime Database integration to provide persistent state storage for static sites. This is particularly useful when proxying static websites that need to store user data, preferences, or application state.

### Firebase Configuration

1. **Environment Variables** (recommended):
```bash
export FIREBASE_DATABASE_URL=https://your-project-id-default-rtdb.firebaseio.com
export FIREBASE_AUTH_TOKEN=your-auth-token  # Optional for public databases
```

2. **Configuration File**:
Copy `firebase_config.json.example` to `firebase_config.json` and update with your Firebase details:
```json
{
  "firebase_url": "https://your-project-id-default-rtdb.firebaseio.com",
  "auth_token": "your-auth-token",
  "enable_for_static": true,
  "auto_detect_static": true
}
```

### Using Firebase State in Static Sites

When the proxy detects static content and Firebase is configured, it automatically injects a `FirebaseState` JavaScript object:

```javascript
// Get state data
const userData = await FirebaseState.get('user_preferences');

// Set state data
await FirebaseState.set('user_preferences', { theme: 'dark', language: 'en' });

// Update multiple values
await FirebaseState.update({
  last_visit: new Date().toISOString(),
  page_views: userData.page_views + 1
});

// Delete state data
await FirebaseState.delete('temporary_data');
```

### Static Site Detection

The proxy automatically detects static content based on:
- File extensions (.html, .css, .js, .png, etc.)
- Content-Type headers
- Absence of dynamic server indicators (cookies, framework headers)

### Benefits

- **Persistent Storage**: Data survives browser restarts and proxy restarts
- **Cross-Device Sync**: Share state across different devices/browsers
- **No Backend Required**: Static sites gain database functionality without modification
- **Automatic Integration**: No manual setup required in static site code

## Architecture

- **WebSocket Relay**: Secure communication between browsers and agents
- **HTTP Proxy**: Agents handle HTTP requests to localhost and return responses
- **Link Rewriting**: Automatic rewriting of HTML links to work through the proxy
- **Base64 Encoding**: Paths are base64-encoded in URLs for safe transport
- **Firebase Integration**: Automatic state management for static sites using Firebase Realtime Database
- **Static Content Detection**: Intelligent detection of static vs dynamic content for appropriate Firebase integration