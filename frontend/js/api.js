// Small helper for talking to the ETIKE API.
// Usage: const data = await api.get("/health");
// When auth.js is loaded, the login token is sent with every request.

const api = (() => {
  const BASE_URL = "/api";

  class ApiError extends Error {
    constructor(message, status, body) {
      super(message);
      this.name = "ApiError";
      this.status = status; // HTTP status, or 0 when the server was unreachable
      this.body = body; // parsed JSON error body, if there was one
      this.code = body?.error?.code || null;
      this.fields = body?.error?.fields || {};
    }
  }

  async function request(path, { method = "GET", body, timeoutMs = 8000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    const token = typeof auth !== "undefined" ? auth.token() : null;
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(BASE_URL + path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      // Network down, server off, or the request timed out.
      throw new ApiError("Could not reach ETIKE. Check your connection and try again.", 0, null);
    } finally {
      clearTimeout(timer);
    }

    // Error responses from our API are JSON too, so parse before checking ok.
    let data = null;
    try {
      data = await response.json();
    } catch (err) {
      data = null;
    }

    if (!response.ok) {
      // An expired or broken token: forget it so the user can log in again.
      if (response.status === 401 && token) auth.forget();
      // Nginx limits login and sign-up attempts; its 429 page isn't JSON.
      const message = data?.error?.message
        || (response.status === 429 ? "Too many attempts. Wait a minute and try again." : null)
        || `Something went wrong (error ${response.status}).`;
      throw new ApiError(message, response.status, data);
    }
    return data;
  }

  return {
    ApiError,
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body: body || {} }),
  };
})();
