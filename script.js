window.addEventListener('load', () => {
    const params = new URLSearchParams(window.location.search);
    const port = params.get('port');
    const b64path = params.get('path');

    if (!port || !b64path) {
        document.body.innerHTML = '<h1>Error</h1><p>Missing "port" or "path" in URL.</p>';
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
