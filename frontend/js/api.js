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

  async function request(path, { method = "GET", body, form, timeoutMs = 8000, raw = false } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    const headers = {};
    if (body) headers["Content-Type"] = "application/json";
    // For file uploads the browser sets the multipart Content-Type itself.
    const token = typeof auth !== "undefined" ? auth.token() : null;
    if (token) headers.Authorization = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(BASE_URL + path, {
        method,
        headers,
        body: form || (body ? JSON.stringify(body) : undefined),
        signal: controller.signal,
      });
    } catch (err) {
      // Network down, server off, or the request timed out.
      throw new ApiError("Could not reach ETIKE. Check your connection and try again.", 0, null);
    } finally {
      clearTimeout(timer);
    }

    // A file (raw): hand back its contents; errors are still JSON.
    if (raw && response.ok) return response.blob();

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

  // Which features are on (see backend/app/features.py). Bus booking is a
  // future phase, so bus-only parts of pages stay hidden unless it is on.
  const config = request("/config").catch(() => ({ features: { bus_booking: false } }));
  const features = config.then((data) => data.features);
  features.then((f) => {
    document.documentElement.classList.toggle("has-bus", Boolean(f.bus_booking));
    document.documentElement.classList.toggle("has-demo", Boolean(f.demo_login));
  });

  return {
    ApiError,
    features: () => features,
    // Booking rules from the server, e.g. { cancel_cutoff_hours: 2 }.
    config: () => config,
    get: (path) => request(path),
    // options: { timeoutMs } for slow requests such as starting a payment.
    post: (path, body, options) => request(path, { method: "POST", body: body || {}, ...options }),
    put: (path, body) => request(path, { method: "PUT", body: body || {} }),
    del: (path) => request(path, { method: "DELETE" }),
    // extra: more form fields sent with the file, e.g. { expires_on: "2027-01-31" }.
    upload: (path, field, file, extra = {}) => {
      const form = new FormData();
      form.append(field, file);
      Object.entries(extra).forEach(([k, v]) => form.append(k, v));
      return request(path, { method: "POST", form, timeoutMs: 30000 });
    },
    // A private file that needs the login token (driver documents): a Blob.
    file: (path) => request(path, { raw: true, timeoutMs: 30000 }),
  };
})();
