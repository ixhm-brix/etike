// Small helper for talking to the ETIKE API.
// Usage: const data = await api.get("/health");

const api = (() => {
  const BASE_URL = "/api";

  class ApiError extends Error {
    constructor(message, status, body) {
      super(message);
      this.name = "ApiError";
      this.status = status; // HTTP status, or 0 when the server was unreachable
      this.body = body; // parsed JSON error body, if there was one
    }
  }

  async function request(path, { method = "GET", body, timeoutMs = 8000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    let response;
    try {
      response = await fetch(BASE_URL + path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      // Network down, server off, or the request timed out.
      throw new ApiError("Could not reach the server", 0, null);
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
      throw new ApiError(`Request failed (${response.status})`, response.status, data);
    }
    return data;
  }

  return {
    ApiError,
    get: (path) => request(path),
    post: (path, body) => request(path, { method: "POST", body }),
  };
})();
