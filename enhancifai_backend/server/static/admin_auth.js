// Shared HTTP Basic Auth helpers for admin pages
function getAuthHeader(forcePrompt = false) {
    let auth = sessionStorage.getItem('admin_auth');
    if (!auth || forcePrompt) {
        const username = prompt('Admin Username:');
        const password = prompt('Admin Password:');
        if (username === null || password === null) return null;
        auth = 'Basic ' + btoa(username + ':' + password);
        sessionStorage.setItem('admin_auth', auth);
    }
    return auth;
}

async function fetchWithAuthRetry(url, options = {}, retry = true) {
    let auth = getAuthHeader();
    if (!auth) return null;
    options.headers = options.headers || {};
    options.headers['Authorization'] = auth;
    // Always send credentials (cookies) for same-origin requests
    options.credentials = 'same-origin';
    // Debug: log the Authorization header
    // console.log('fetchWithAuthRetry: Authorization:', auth);

    let res = await fetch(url, options);
    if (res.status === 401 && retry) {
        sessionStorage.removeItem('admin_auth');
        auth = getAuthHeader(true);
        if (!auth) return null;
        options.headers['Authorization'] = auth;
        res = await fetch(url, options);
    }
    return res;
}

// Optional: Helper to force re-authentication (call this on page load if needed)
function forceAdminReauth() {
    sessionStorage.removeItem('admin_auth');
    return getAuthHeader(true);
}

// Make helpers available globally
window.getAuthHeader = getAuthHeader;
window.fetchWithAuthRetry = fetchWithAuthRetry;
window.forceAdminReauth = forceAdminReauth;
