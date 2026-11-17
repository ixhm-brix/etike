// Admin: refunds owed to passengers who cancelled a paid bus ticket.
(async function adminRefunds() {
  if (!auth.require("admin")) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");
  const status = new URLSearchParams(location.search).get("status") === "refunded" ? "refunded" : "due";

  const tabs = document.getElementById("tabs");
  [["due", "To send"], ["refunded", "Sent"]].forEach(([value, label]) => {
    const a = ui.el("a", "mode");
    a.href = `?status=${value}`;
    if (value === status) a.setAttribute("aria-current", "page");
    a.append(ui.el("span", null, label));
    tabs.append(a);
  });

  try {
    const { refunds } = await api.get(`/admin/refunds?status=${status}`);
    loading.hidden = true;
    if (!refunds.length) {
      list.replaceWith(ui.empty("Nothing here",
        status === "due" ? "No refunds are waiting to be sent." : "No refunds have been sent yet."));
      return;
    }
    list.append(...refunds.map(card));
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function card(r) {
    const li = ui.el("li", "result");
    li.append(
      ui.el("span", "result-time", `${ui.money(r.amount)} to ${r.passenger_name}`),
      ui.el("span", "result-price", r.passenger_phone),
      ui.el("span", "result-meta", `Booking #${r.booking_id} · ${r.trip} · ${ui.when(r.departure_time)} · ${r.operator}`),
      ui.el("span", "result-note", r.refunded_at ? `Sent ${ui.day(r.refunded_at)}` : ""),
    );
    const actions = ui.el("div", "result-actions");
    actions.append(ui.el("span", `status status-${r.refund_status === "due" ? "pending" : "approved"}`,
      r.refund_status === "due" ? "To send" : "Sent"));
    if (r.refund_status === "due") {
      const b = ui.el("button", "btn-black btn-sm", "Mark as sent");
      b.type = "button";
      b.addEventListener("click", async () => {
        try {
          await ui.busy(b, "Saving…", () => api.post(`/admin/refunds/${r.payment_id}/done`));
          li.remove();
          ui.say(msg, `Refund of ${ui.money(r.amount)} to ${r.passenger_name} marked as sent.`, "info");
        } catch (err) {
          ui.say(msg, err.message);
        }
      });
      actions.append(b);
    }
    li.append(actions);
    return li;
  }
})();
