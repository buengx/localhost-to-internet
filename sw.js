// sw.js - The Service Worker

// A map to store resolvers for ongoing fetch requests
const fetchResolvers = new Map();

// Helper to send a message to the controller page (client)
async function getClient() {
    const clients = await self.clients.matchAll({ type: 'window' });
    if (clients.length > 0) {
        return clients[0];
    }
    return null;
}

// Listen for messages from the controller page (which contain responses)
self.addEventListener('message', (event) => {
    const { type, fetchId, response } = event.data;

    if (type === 'http_response' && fetchResolvers.has(fetchId)) {
        const { resolve } = fetchResolvers.get(fetchId);

        // The body is Base64 encoded, so we need to decode it first
        const bodyBlob = new Blob([base64ToBytes(response.body)]);

        const res = new Response(bodyBlob, {
            status: response.status,
            statusText: response.status_text,
            headers: response.headers,
        });

        resolve(res);
        fetchResolvers.delete(fetchId);
    }
});

// The main proxy logic
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // Only proxy requests that have the 'port' search parameter.
    // This allows the service worker to coexist with other site content.
    if (!url.searchParams.has('port')) {
        return; // Do not intercept, let the browser handle it.
    }

    console.log('SW: Intercepting fetch for:', url.pathname);

    event.respondWith(
        new Promise(async (resolve) => {
            const client = await getClient();
            if (!client) {
                // If there's no controller page, we can't do anything.
                resolve(new Response("Service Worker cannot find a controller page.", { status: 500 }));
                return;
            }

            const fetchId = crypto.randomUUID();
            fetchResolvers.set(fetchId, { resolve });

            const requestData = {
                method: event.request.method,
                headers: Object.fromEntries(event.request.headers.entries()),
                path: url.pathname + url.search, // Pass the full path and query string
                body: await event.request.arrayBuffer().then(buffer => bytesToBase64(new Uint8Array(buffer))),
            };

            // Send the request to the controller page to be proxied
            client.postMessage({
                type: 'http_request',
                fetchId: fetchId,
                request: requestData,
            });
        })
    );
});

// Helper functions for Base64 conversion
function bytesToBase64(bytes) {
    const binString = Array.from(bytes, (byte) =>
        String.fromCodePoint(byte),
    ).join("");
    return btoa(binString);
}

function base64ToBytes(base64) {
    const binString = atob(base64);
    return Uint8Array.from(binString, (m) => m.codePointAt(0));
}

self.addEventListener('activate', (event) => {
    // This ensures the service worker takes control of pages immediately.
    event.waitUntil(clients.claim());
});
