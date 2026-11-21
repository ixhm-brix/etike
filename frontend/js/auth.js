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

  // On the log-in and sign-up pages: keep the page someone was going to
  // (their search) when they switch between the two, and say why they're here.
  function explainNext(otherLinkId) {
    const next = nextPage(null);
    if (!next) return;
    const link = document.getElementById(otherLinkId);
    if (link) link.href += `${link.href.includes("?") ? "&" : "?"}next=${encodeURIComponent(next)}`;
    const box = document.getElementById("why-login");
    const wanted = new URL(next, location.origin);
    if (box && wanted.pathname === "/results.html") {
      const p = wanted.searchParams;
      box.textContent = `Log in or create an account to see prices for ${p.get("origin")} to ${p.get("destination")}. Your search is kept.`;
      box.hidden = false;
    }
  }

  function homeFor(u) {
    if (u.role === "admin") return "/admin/drivers.html";
    // Passengers start on the home page: search with the map.
    return u.role === "driver" ? "/driver/offer.html" : "/";
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
      return a;
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
    if (u.role === "admin") {
      link("/admin/drivers.html", "Drivers");
      link("/admin/companies.html", "Companies").dataset.feature = "bus";
      link("/admin/refunds.html", "Refunds");
    } else if (u.role === "driver") link("/driver/offer.html", "Post a ride");
    else link("/bookings.html", "My bookings");
    const out = document.createElement("button");
    out.type = "button";
    out.textContent = "Log out";
    out.addEventListener("click", logout);
    box.append(out);
  }

  // Phones, once logged in: a bottom tab bar like a mobile app (CSS shows it
  // only on small screens, where it replaces the top-bar links and the
  // footer). Visitors keep Log in / Sign up in the top bar instead.
  const ICONS = {
    search: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    bookings: '<rect x="4" y="4" width="16" height="17" rx="2"/><path d="M8 2v4M16 2v4M4 10h16"/>',
    trips: '<path d="M3 15l2-6a2 2 0 0 1 2-1.5h10a2 2 0 0 1 2 1.5l2 6v4H3z"/><path d="M3 15h18"/>',
    drivers: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    refunds: '<path d="M4 12a8 8 0 1 0 3-6.2"/><path d="M4 4v4h4"/>',
    account: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
  };

  function renderTabbar() {
    document.querySelector(".tabbar")?.remove();
    const u = user();
    if (!u) return; // visitors: Log in / Sign up stay in the top bar
    let tabs;
    if (u.role === "admin") tabs = [["/admin/drivers.html", "Drivers", "drivers"], ["/admin/refunds.html", "Refunds", "refunds"]];
    else if (u.role === "driver") tabs = [["/", "Search", "search"], ["/driver/offer.html", "My trips", "trips"]];
    else tabs = [["/", "Search", "search"], ["/bookings.html", "Bookings", "bookings"]];
    const nav = document.createElement("nav");
    nav.className = "tabbar";
    nav.setAttribute("aria-label", "App");
    const item = (tag, label, icon) => {
      const el = document.createElement(tag);
      el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[icon]}</svg>`;
      el.append(label);
      nav.append(el);
      return el;
    };
    tabs.forEach(([href, label, icon]) => {
      const a = item("a", label, icon);
      a.href = href;
      if (location.pathname === href || (href === "/" && location.pathname === "/index.html")) {
        a.setAttribute("aria-current", "page");
      }
    });
    const account = item("button", "Account", "account");
    account.type = "button";
    account.setAttribute("aria-expanded", "false");
    account.addEventListener("click", () => toggleSheet(u, account));
    document.body.append(nav);
    document.body.classList.add("has-tabbar");
    if (u.role !== "admin") watchMessages(nav, u);
  }

  // A red count on Bookings / My trips when someone has written.
  function watchMessages(nav, u) {
    const tab = nav.querySelector(`a[href="${u.role === "driver" ? "/driver/offer.html" : "/bookings.html"}"]`);
    const check = async () => {
      if (document.hidden || typeof api === "undefined") return;
      try {
        const { total } = await api.get("/messages/unread");
        tab.querySelector(".badge")?.remove();
        if (total) {
          const b = document.createElement("span");
          b.className = "badge";
          b.textContent = String(total);
          b.setAttribute("aria-label", `${total} new messages`);
          tab.append(b);
        }
      } catch (err) {
        // The next check tries again.
      }
    };
    check();
    setInterval(check, 30000);
    document.addEventListener("etike:messages-read", check);
  }

  // The Account tab opens a small panel from the bottom: who you are, and
  // Log out (two taps away, so nobody logs out by accident).
  function toggleSheet(u, button) {
    const open = document.querySelector(".sheet");
    if (open) {
      open.remove();
      button.setAttribute("aria-expanded", "false");
      return;
    }
    const sheet = document.createElement("div");
    sheet.className = "sheet";
    sheet.setAttribute("role", "dialog");
    sheet.setAttribute("aria-label", "Account");
    const role = { passenger: "Traveller", driver: "Driver", admin: "Admin" }[u.role];
    const name = document.createElement("strong");
    name.textContent = u.full_name;
    const meta = document.createElement("span");
    meta.textContent = `${role} · 0${u.phone.slice(4)}`;
    const out = document.createElement("button");
    out.type = "button";
    out.className = "btn-black";
    out.textContent = "Log out";
    out.addEventListener("click", logout);
    sheet.append(name, meta, out);
    document.body.append(sheet);
    button.setAttribute("aria-expanded", "true");
    out.focus();
  }

  document.addEventListener("DOMContentLoaded", () => {
    renderAccount();
    renderTabbar();
  });

  return { token, user, save, logout, require, nextPage, homeFor, explainNext, forget: () => store(null) };
})();
