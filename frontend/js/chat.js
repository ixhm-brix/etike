// Chat between a passenger and the driver of their ride: where to meet,
// "I'm at the gate", "5 minutes away". New messages show up within a few
// seconds while the page is open.
(async function chat() {
  const user = auth.require();
  if (!user) return;
  const bookingId = new URLSearchParams(location.search).get("booking");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");
  const list = document.getElementById("messages");
  const form = document.getElementById("send");
  const body = form.elements.body;
  const button = form.querySelector("button");
  const POLL_MS = 5000;
  let lastCount = -1;

  // Drivers come back to their trips, passengers to their bookings.
  if (user.role === "driver") document.getElementById("back").href = "/driver/offer.html";

  await load();
  setInterval(() => { if (!document.hidden) load(); }, POLL_MS);

  async function load() {
    let data;
    try {
      data = await api.get(`/bookings/${encodeURIComponent(bookingId)}/messages`);
    } catch (err) {
      loading.hidden = true;
      ui.say(msg, err.status === 404 ? "We couldn't find this conversation." : err.message);
      return;
    }
    loading.hidden = true;
    show(data);
    // Opening the chat marked the messages read: update the tab bar badge.
    document.dispatchEvent(new Event("etike:messages-read"));
  }

  function show({ booking: b, with: other, can_send: canSend, messages }) {
    document.getElementById("chat").hidden = false;
    document.getElementById("title").textContent = other.name;
    document.getElementById("subtitle").textContent =
      `${other.role === "driver" ? "Your driver" : "Your passenger"} · ${b.origin} to ${b.destination}, ${ui.when(b.departure_time)}`;

    const info = document.getElementById("info");
    info.replaceChildren();
    if (b.pickup_point) {
      const meet = ui.el("p", "chat-meet");
      meet.append(ui.el("strong", null, "Meeting point: "), b.pickup_point);
      info.append(meet);
    }
    if (other.phone) {
      const c = ui.contact({ phone: other.phone, bookingId: b.booking_id, name: other.name });
      c.querySelector(".btn-black")?.remove(); // already in the chat
      info.append(c);
    }

    form.hidden = !canSend;
    document.getElementById("closed").hidden = canSend;

    if (messages.length === lastCount) return; // nothing new: keep the scroll
    // Scroll to the newest message on first load, after sending, or when
    // already at the bottom; otherwise leave the reader where they are.
    const follow = lastCount === -1
      || window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
    lastCount = messages.length;
    if (!messages.length) {
      list.replaceChildren(ui.el("li", "chat-empty", other.role === "driver"
        ? "Say hello, or tell your driver where you'll be waiting."
        : "Say hello, or tell your passenger where to find you."));
      return;
    }
    list.replaceChildren(...messages.map(bubble));
    // To the very bottom, so the newest message clears the message box.
    if (follow) window.scrollTo(0, document.body.scrollHeight);
  }

  function bubble(m) {
    const li = ui.el("li", `chat-bubble${m.mine ? " is-mine" : ""}`);
    li.append(ui.el("p", null, m.body));
    const at = new Date(m.at).toLocaleString("en-GB", {
      weekday: "short", hour: "2-digit", minute: "2-digit",
    });
    li.append(ui.el("span", "chat-time", m.mine && m.read ? `${at} · Read` : at));
    return li;
  }

  // Grow the box with the text, up to a few lines.
  body.addEventListener("input", () => {
    body.style.height = "auto";
    body.style.height = `${Math.min(body.scrollHeight, 140)}px`;
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = body.value.trim();
    if (!text) return;
    try {
      await ui.busy(button, "…", () =>
        api.post(`/bookings/${encodeURIComponent(bookingId)}/messages`, { body: text }));
      body.value = "";
      body.style.height = "auto";
      ui.say(msg, "");
      lastCount = -1; // redraw and scroll to the new message
      await load();
    } catch (err) {
      ui.say(msg, err.message);
    }
  });
})();
