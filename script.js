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
    const pendingRequests = new Map(); // Track pending HTTP requests

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

            // Setup request interception after connection is ready
            setupRequestInterception(socket, conn_id, port, pendingRequests);

            const requestData = {
                type: 'http_request',
                conn_id: conn_id,
                fetchId: crypto.randomUUID(),
                method: 'GET',
                headers: { 'Accept': 'text/html' },
                path: path,
                body: '',
            };
            socket.send(JSON.stringify(requestData));

        } else if (message.type === 'http_response') {
            const fetchId = message.fetchId;
            console.log(`Received http_response for fetchId: ${fetchId.substring(0, 8)}`);

            // Check if this is a pending intercepted request
            if (pendingRequests.has(fetchId)) {
                const { resolve } = pendingRequests.get(fetchId);
                pendingRequests.delete(fetchId);
                
                // Create a Response object for intercepted requests
                const responseInit = {
                    status: message.status,
                    statusText: message.status_text,
                    headers: new Headers(message.headers)
                };
                
                const responseBody = atob(message.body);
                const response = new Response(responseBody, responseInit);
                resolve(response);
                return;
            }

            // This is the initial page load
            const response_body = atob(message.body);
            const parser = new DOMParser();
            const newDoc = parser.parseFromString(response_body, 'text/html');
            document.documentElement.replaceWith(newDoc.documentElement);
        }
    });

    socket.addEventListener('close', () => {
        console.log("WebSocket connection closed.");
    });
}

function setupRequestInterception(socket, conn_id, port, pendingRequests) {
    // Store original functions
    const originalFetch = window.fetch;
    const originalXMLHttpRequest = window.XMLHttpRequest;

    // Intercept fetch requests
    window.fetch = async function(url, options = {}) {
        const fullUrl = new URL(url, window.location.href);
        
        // Only intercept requests to localhost or the current hostname
        if (shouldIntercept(fullUrl, port)) {
            console.log(`Intercepting fetch request to: ${fullUrl.pathname}`);
            return await proxyRequest(socket, conn_id, fullUrl, options, pendingRequests);
        }
        
        // Let other requests go through normally
        return originalFetch.call(this, url, options);
    };

    // Intercept XMLHttpRequest
    const OriginalXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
        const xhr = new OriginalXHR();
        const originalOpen = xhr.open;
        const originalSend = xhr.send;
        
        let intercepted = false;
        let requestUrl;
        let requestOptions = {};

        xhr.open = function(method, url, async = true, user, password) {
            requestUrl = new URL(url, window.location.href);
            requestOptions.method = method;
            
            if (shouldIntercept(requestUrl, port)) {
                intercepted = true;
                console.log(`Intercepting XHR request to: ${requestUrl.pathname}`);
                return; // Don't call original open for intercepted requests
            }
            
            return originalOpen.call(this, method, url, async, user, password);
        };

        xhr.send = function(body) {
            if (intercepted) {
                // Handle intercepted request
                requestOptions.body = body;
                
                // Copy headers from XHR to options
                requestOptions.headers = {};
                
                proxyRequest(socket, conn_id, requestUrl, requestOptions, pendingRequests)
                    .then(response => {
                        // Simulate XHR response
                        Object.defineProperty(xhr, 'status', { value: response.status, writable: false });
                        Object.defineProperty(xhr, 'statusText', { value: response.statusText, writable: false });
                        Object.defineProperty(xhr, 'readyState', { value: 4, writable: false });
                        
                        response.text().then(text => {
                            Object.defineProperty(xhr, 'responseText', { value: text, writable: false });
                            Object.defineProperty(xhr, 'response', { value: text, writable: false });
                            
                            if (xhr.onreadystatechange) xhr.onreadystatechange();
                            if (xhr.onload) xhr.onload();
                        });
                    })
                    .catch(error => {
                        console.error('XHR proxy error:', error);
                        if (xhr.onerror) xhr.onerror();
                    });
                
                return;
            }
            
            return originalSend.call(this, body);
        };

        return xhr;
    };
}

function shouldIntercept(url, port) {
    // Intercept requests to localhost on the specified port, or relative URLs
    const hostname = url.hostname;
    const urlPort = url.port;
    
    return (hostname === 'localhost' || hostname === '127.0.0.1') && 
           (urlPort === port.toString() || urlPort === '');
}

async function proxyRequest(socket, conn_id, url, options, pendingRequests) {
    const fetchId = crypto.randomUUID();
    
    // Prepare headers
    const headers = { ...options.headers };
    if (options.method === 'POST' && options.body && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
    }

    // Prepare body
    let bodyB64 = '';
    if (options.body) {
        if (typeof options.body === 'string') {
            bodyB64 = btoa(options.body);
        } else if (options.body instanceof FormData) {
            // Convert FormData to URLSearchParams for simplicity
            const params = new URLSearchParams();
            for (const [key, value] of options.body) {
                params.append(key, value);
            }
            bodyB64 = btoa(params.toString());
        } else {
            bodyB64 = btoa(options.body.toString());
        }
    }

    const requestData = {
        type: 'http_request',
        conn_id: conn_id,
        fetchId: fetchId,
        method: options.method || 'GET',
        headers: headers,
        path: url.pathname + url.search,
        body: bodyB64,
    };

    // Create a promise to resolve when response comes back
    return new Promise((resolve, reject) => {
        pendingRequests.set(fetchId, { resolve, reject });
        
        // Set a timeout to avoid hanging forever
        setTimeout(() => {
            if (pendingRequests.has(fetchId)) {
                pendingRequests.delete(fetchId);
                reject(new Error('Request timeout'));
            }
        }, 30000);
        
        socket.send(JSON.stringify(requestData));
    });
}
