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

        // Reconstruct the original query string, excluding our control parameters
        const forwardedParams = new URLSearchParams();
        for (const [key, value] of params.entries()) {
            if (key !== 'port' && key !== 'path') {
                forwardedParams.append(key, value);
            }
        }

        const queryString = forwardedParams.toString();
        const fullPath = queryString ? `${decodedPath}?${queryString}` : decodedPath;

        connectAndFetch(port, fullPath);

    } catch (e) {
        document.body.innerHTML = '<h1>Error</h1><p>Invalid Base64 path in URL.</p>';
        console.error("Base64 Decode Error:", e);
    }
});

function connectAndFetch(port, path) {
    const ws_uri = `wss://${window.location.hostname || 'localhost'}:8765/?port=${port}`;
    const socket = new WebSocket(ws_uri);

    socket.addEventListener('open', () => {
        console.log("WebSocket connection opened. Waiting for connection_ready.");
    });

    socket.addEventListener('error', (err) => {
        document.body.innerHTML = `<h1>Proxy Connection Error</h1><p>Could not connect to the relay server at ${ws_uri}.</p>`;
        console.error("WebSocket Error:", err);
    });

    socket.addEventListener('message', (event) => {
        const message = JSON.parse(event.data);

        if (message.type === 'connection_ready') {
            const conn_id = message.conn_id;
            console.log(`Connection ready. Fetching path: ${path}`);

            // For the initial request, we don't have original headers to forward.
            // We send a basic GET request.
            const requestData = {
                type: 'http_request',
                conn_id: conn_id,
                fetchId: crypto.randomUUID(),
                method: 'GET',
                headers: { 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8' },
                path: path,
                body: '',
            };
            socket.send(JSON.stringify(requestData));

        } else if (message.type === 'http_response') {
            console.log("Received http_response from proxy.");

            const response_body = atob(message.body);
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(response_body, 'text/html');

            // Set the base URL in the new document's head so relative paths work correctly
            // before they are handled by the (non-existent) service worker.
            // The link rewriter on the agent makes this less critical, but it's good practice.
            let base = newDoc.querySelector('base');
            if (!base) {
                base = newDoc.createElement('base');
                const head = newDoc.querySelector('head');
                if (head) head.prepend(base);
            }
            // The base href should be the proxy URL itself.
            base.href = window.location.href;


            document.documentElement.replaceWith(newDoc.documentElement);
        }
    });

    socket.addEventListener('close', () => {
        console.log("WebSocket connection closed.");
    });
}
