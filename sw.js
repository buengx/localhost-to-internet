// sw.js - Self-contained HTTPS Proxy Service Worker

const connections = new Map();
const fetchResolvers = new Map();

function getConnection(port) {
    if (connections.has(port)) {
        const conn = connections.get(port);
        if (conn.socket.readyState < 2) return conn;
        connections.delete(port);
    }

    const ws_uri = `wss://${self.location.hostname || 'localhost'}:8765/?port=${port}`;
    const socket = new WebSocket(ws_uri);

    const connection = {
        socket: socket,
        conn_id: null,
        pending: new Promise((resolve, reject) => {
            socket.addEventListener('open', () => console.log(`SW: WebSocket opened for port ${port}`));
            socket.addEventListener('error', (err) => {
                console.error(`SW: WebSocket error for port ${port}.`, err);
                connections.delete(port);
                reject(new Error("WebSocket connection failed."));
            });
            socket.addEventListener('close', () => {
                console.log(`SW: WebSocket closed for port ${port}.`);
                connections.delete(port);
            });
            socket.addEventListener('message', (event) => {
                const msg = JSON.parse(event.data);
                if (msg.type === 'connection_ready') {
                    connection.conn_id = msg.conn_id;
                    console.log(`SW: Connection ready for port ${port}`);
                    resolve(connection);
                } else if (msg.type === 'http_response') {
                    const resolver = fetchResolvers.get(msg.fetchId);
                    if (resolver) {
                        resolver(msg);
                        fetchResolvers.delete(msg.fetchId);
                    }
                }
            });
        }),
    };
    connections.set(port, connection);
    return connection;
}

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const port = url.searchParams.get('port');
    const b64path = url.searchParams.get('path');

    if (!port || !b64path) return;

    // The path from the browser is Base64 encoded, so we must decode it.
    const decodedPath = atob(b64path);

    console.log(`SW: Intercepting fetch for decoded path: ${decodedPath}`);

    event.respondWith(
        (async () => {
            try {
                const connection = getConnection(port);
                await connection.pending;

                if (!connection.conn_id) {
                    return new Response("Proxy error: Could not establish tunnel connection.", { status: 502 });
                }

                const fetchId = crypto.randomUUID();
                const bodyB64 = await event.request.arrayBuffer().then(buffer => {
                    const bytes = new Uint8Array(buffer);
                    let binary = '';
                    for (let i = 0; i < bytes.byteLength; i++) {
                        binary += String.fromCharCode(bytes[i]);
                    }
                    return btoa(binary);
                });

                const requestData = {
                    type: 'http_request',
                    conn_id: connection.conn_id,
                    fetchId: fetchId,
                    method: event.request.method,
                    headers: Object.fromEntries(event.request.headers.entries()),
                    path: decodedPath, // Send the DECODED path to the agent
                    body: bodyB64,
                };

                return new Promise((resolve) => {
                    fetchResolvers.set(fetchId, resolve);
                    connection.socket.send(JSON.stringify(requestData));
                }).then(responseMsg => {
                    const bodyBytes = atob(responseMsg.body).split('').map(c => c.charCodeAt(0));
                    return new Response(new Uint8Array(bodyBytes), {
                        status: responseMsg.status,
                        statusText: responseMsg.status_text,
                        headers: responseMsg.headers,
                    });
                });
            } catch (e) {
                console.error("SW Fetch Error:", e);
                return new Response("Proxy error: " + e.message, { status: 502 });
            }
        })()
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(clients.claim());
});
