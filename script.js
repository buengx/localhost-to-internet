window.addEventListener('load', () => {
    const params = new URLSearchParams(window.location.search);
    const port = params.get('port');
    const b64path = params.get('path');

    if (!port || !b64path) {
        showHomepage();
        return;
    }

    try {
        const decodedPath = atob(b64path);
        connectAndFetch(port, decodedPath);
    } catch (e) {
        document.body.innerHTML = '<h1>Error</h1><p>Invalid Base64 path in URL.</p>';
        console.error("Base64 Decode Error:", e);
    }
});

function showHomepage() {
    document.title = 'Localhost to Internet Proxy';
    document.body.innerHTML = `
        <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: sans-serif;">
            <h1>Localhost to Internet Proxy</h1>
            <p>Enter the localhost address you want to access through the proxy:</p>
            
            <form id="proxyForm" style="margin: 20px 0;">
                <div style="margin-bottom: 15px;">
                    <label for="localAddress" style="display: block; margin-bottom: 5px; font-weight: bold;">
                        Localhost Address:
                    </label>
                    <input 
                        type="text" 
                        id="localAddress" 
                        placeholder="localhost:3000/api/endpoint" 
                        style="width: 100%; padding: 10px; border: 1px solid #ccc; border-radius: 4px; font-size: 16px;"
                        required
                    />
                    <small style="color: #666; margin-top: 5px; display: block;">
                        Examples: localhost:3000, localhost:8080/api, 127.0.0.1:5000/dashboard
                    </small>
                </div>
                
                <button 
                    type="submit" 
                    style="background: #007cba; color: white; padding: 12px 24px; border: none; border-radius: 4px; font-size: 16px; cursor: pointer;"
                >
                    Connect via Proxy
                </button>
            </form>
            
            <div style="margin-top: 30px; padding: 15px; background: #f5f5f5; border-radius: 4px;">
                <h3 style="margin-top: 0;">How it works:</h3>
                <ol style="margin: 10px 0; padding-left: 20px;">
                    <li>Enter your localhost address (with port and optional path)</li>
                    <li>The proxy will connect to your local server through a secure relay</li>
                    <li>You can share the resulting URL to give others access to your localhost</li>
                </ol>
            </div>
        </div>
    `;
    
    document.getElementById('proxyForm').addEventListener('submit', handleFormSubmit);
}

function handleFormSubmit(e) {
    e.preventDefault();
    
    const localAddress = document.getElementById('localAddress').value.trim();
    if (!localAddress) {
        alert('Please enter a localhost address');
        return;
    }
    
    // Parse the localhost address
    const match = localAddress.match(/^(?:https?:\/\/)?([^\/]+)(.*)$/);
    if (!match) {
        alert('Invalid address format. Please use format like: localhost:3000/path');
        return;
    }
    
    const hostPort = match[1];
    const path = match[2] || '/';
    
    // Extract port from host:port
    const portMatch = hostPort.match(/:(\d+)$/);
    if (!portMatch) {
        alert('Please specify a port number (e.g., localhost:3000)');
        return;
    }
    
    const port = portMatch[1];
    
    // Base64 encode the path (standard base64 for atob compatibility)
    const b64path = btoa(path);
    
    // Construct the new URL
    const newUrl = `${window.location.origin}${window.location.pathname}?port=${port}&path=${b64path}`;
    
    // Navigate to the proxy URL
    window.location.href = newUrl;
}

function connectAndFetch(port, path) {
    const ws_uri = `wss://${window.location.hostname || 'localhost'}:8765/?port=${port}`;
    const socket = new WebSocket(ws_uri);

    let conn_id = null;

    socket.addEventListener('open', () => {
        console.log("WebSocket connection opened. Waiting for connection_ready.");
    });

    socket.addEventListener('error', (err) => {
        document.body.innerHTML = `<h1>Proxy Connection Error</h1><p>Could not connect to the relay server at ${ws_uri}. Please ensure the server is running and you have accepted its self-signed certificate.</p>`;
        console.error("WebSocket Error:", err);
    });

    socket.addEventListener('message', (event) => {
        const message = JSON.parse(event.data);

        if (message.type === 'connection_ready') {
            conn_id = message.conn_id;
            console.log(`Connection ready with conn_id: ${conn_id}. Fetching path: ${path}`);

            const requestData = {
                type: 'http_request',
                conn_id: conn_id,
                fetchId: crypto.randomUUID(), // Still useful for debugging on the agent
                method: 'GET',
                headers: { 'Accept': 'text/html' }, // Simple headers for a simple GET
                path: path,
                body: '', // No body for GET
            };
            socket.send(JSON.stringify(requestData));

        } else if (message.type === 'http_response') {
            console.log("Received http_response from proxy.");

            const response_body = atob(message.body);

            // This is the key part: we replace the document's content.
            // We use DOMParser to avoid issues with scripts in the head.
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(response_body, 'text/html');

            // Replace the entire document element with the new one.
            // This is more robust than innerHTML as it handles <head> and <body> correctly.
            document.documentElement.replaceWith(newDoc.documentElement);

            // The socket will close after this, as the page is effectively reloaded.
        }
    });

    socket.addEventListener('close', () => {
        console.log("WebSocket connection closed.");
    });
}
