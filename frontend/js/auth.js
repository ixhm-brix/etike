// Login state: keeps the token from /api/auth/login or /register, and the
// account links in the top bar. api.js sends the token on every request.

const auth = (() => {
  const KEY = "etike.session";

  // Browser storage can be blocked (private mode); then the session lasts
  // only until the page is closed.
  let memory = null;
  function load() {
    try {
      return JSON.parse(localStorage.getItem(KEY)) || null;
    } catch (err) {
      return memory;
    }
  }
  function store(value) {
    memory = value;
    try {
      if (value) localStorage.setItem(KEY, JSON.stringify(value));
      else localStorage.removeItem(KEY);
    } catch (err) {
      // keep it in memory only
    }
  }

  const token = () => load()?.token || null;
  const user = () => load()?.user || null;

  function save(response) {
    store({ token: response.access_token, user: response.user });
  }

  function logout() {
    store(null);
    location.href = "/";
  }

  // Send people who are not logged in (or have the wrong role) to the
  // login page, then bring them back here afterwards.
  function require(role) {
    const u = user();
    if (u && (!role || u.role === role)) return u;
    const next = location.pathname + location.search;
    location.replace(`/login.html?next=${encodeURIComponent(next)}`);
    return null;
  }

  // Only follow "next" links to pages on this site.
  function nextPage(fallback) {
    const next = new URLSearchParams(location.search).get("next");
    return next && next.startsWith("/") && !next.startsWith("//") ? next : fallback;
  }

  function homeFor(u) {
    return u.role === "driver" ? "/driver/offer.html" : "/search.html";
  }

  function renderAccount() {
    const box = document.getElementById("account");
    if (!box) return;
    const u = user();
    box.replaceChildren();
    const link = (href, text, cls) => {
      const a = document.createElement("a");
      a.href = href;
      a.textContent = text;
      if (cls) a.className = cls;
      box.append(a);
    };
    if (!u) {
      link("/login.html", "Log in");
      link("/register.html", "Sign up", "account-cta");
      return;
    }
    const name = document.createElement("span");
    name.className = "account-name";
    name.textContent = u.full_name.split(" ")[0];
    box.append(name);
    if (u.role === "driver") link("/driver/offer.html", "Post a ride");
    else link("/bookings.html", "My bookings");
    const out = document.createElement("button");
    out.type = "button";
    out.textContent = "Log out";
    out.addEventListener("click", logout);
    box.append(out);
  }

  document.addEventListener("DOMContentLoaded", renderAccount);

  return { token, user, save, logout, require, nextPage, homeFor, forget: () => store(null) };
})();
