// Admin: approve or reject drivers after checking their licence.
(async function adminDrivers() {
  if (!auth.require("admin")) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");
  const params = new URLSearchParams(location.search);
  const status = ["pending", "approved", "rejected"].includes(params.get("status"))
    ? params.get("status") : "pending";

  const tabs = document.getElementById("tabs");
  [["pending", "Waiting"], ["approved", "Approved"], ["rejected", "Rejected"]].forEach(([value, label]) => {
    const a = ui.el("a", "mode");
    a.href = `?status=${value}`;
    if (value === status) a.setAttribute("aria-current", "page");
    a.append(ui.el("span", null, label));
    tabs.append(a);
  });

  try {
    const { drivers } = await api.get(`/admin/drivers?status=${status}`);
    loading.hidden = true;
    if (!drivers.length) {
      const text = { pending: "No drivers are waiting for approval.", approved: "No approved drivers yet.",
        rejected: "No rejected drivers." }[status];
      list.replaceWith(ui.empty("Nothing here", text));
      return;
    }
    list.append(...drivers.map(card));
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function card(d) {
    const li = ui.el("li", "result");
    const vehicles = d.vehicles.length
      ? d.vehicles.map((v) => `${v.plate_number} (${v.model}, ${v.seats} seats)`).join(", ")
      : "No vehicles yet";
    li.append(
      ui.el("span", "result-time", d.full_name),
      ui.el("span", "result-price", d.license_number),
      ui.el("span", "result-meta", `${d.phone}${d.email ? ` · ${d.email}` : ""}`),
      ui.el("span", "result-note", `Joined ${ui.day(d.registered_at)}`),
      ui.el("span", "result-meta result-wide", vehicles),
    );
    const actions = ui.el("div", "result-actions");
    actions.append(ui.el("span", `status status-${d.status}`, d.status[0].toUpperCase() + d.status.slice(1)));
    if (d.status !== "approved") actions.append(button(d, "approve", "Approve", "btn-black"));
    if (d.status !== "rejected") actions.append(button(d, "reject", "Reject", "btn-gray"));
    li.append(actions);
    return li;
  }

  function button(d, action, label, style) {
    const b = ui.el("button", `${style} btn-sm`, label);
    b.type = "button";
    b.addEventListener("click", async () => {
      try {
        const { driver } = await ui.busy(b, "Saving…", () =>
          api.post(`/admin/drivers/${d.driver_id}/${action}`),
        );
        b.closest("li").remove();
        ui.say(msg, `${driver.full_name} is now ${driver.status}.`, "info");
      } catch (err) {
        ui.say(msg, err.message);
      }
    });
    return b;
  }
})();
