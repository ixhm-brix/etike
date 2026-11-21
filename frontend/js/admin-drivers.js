// Admin: check each driver's legal documents, then approve or reject them.
// Approving needs every document uploaded and in date (the API checks too).
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
      ui.el("span", "result-price", d.license_number || "No licence number yet"),
      ui.el("span", "result-meta", `${d.phone}${d.email ? ` · ${d.email}` : ""}`),
      ui.el("span", "result-note", `Joined ${ui.day(d.registered_at)}`),
      ui.el("span", "result-meta result-wide", vehicles),
    );
    li.append(detailsLine(d.details));
    if (d.rejection_reason) {
      li.append(ui.el("span", "result-note result-wide", `Rejected: ${d.rejection_reason}`));
    }
    li.append(documentList(d));

    const actions = ui.el("div", "result-actions");
    actions.append(ui.el("span", `status status-${d.status}`, d.status[0].toUpperCase() + d.status.slice(1)));
    if (d.status !== "approved") {
      const approve = button(d, "approve", "Approve", "btn-black");
      if (d.document_problems.length) {
        approve.disabled = true;
        approve.title = `Not yet: ${d.document_problems.join("; ")}`;
      }
      actions.append(approve);
    }
    if (d.status !== "rejected") {
      const reason = ui.el("input");
      reason.type = "text";
      reason.maxLength = 300;
      reason.placeholder = "Reason (the driver sees it)";
      reason.setAttribute("aria-label", `Reason for rejecting ${d.full_name}`);
      reason.className = "reject-reason";
      actions.append(reason, button(d, "reject", "Reject", "btn-gray", () => ({ reason: reason.value })));
    }
    li.append(actions);
    return li;
  }

  // What the driver typed in, to compare with their national ID below.
  function detailsLine(x) {
    if (!x.national_id_number) {
      return ui.el("span", "result-meta result-wide is-bad", "Personal details not given yet");
    }
    const gender = x.gender[0].toUpperCase() + x.gender.slice(1);
    return ui.el("span", "result-meta result-wide",
      `ID ${x.national_id_number} · Born ${ui.date(x.date_of_birth)} · ${gender} · Lives in ${x.home_sector}, ${x.home_district}`);
  }

  // What the driver uploaded: open each file and check it against the
  // vehicle and licence details above before approving.
  function documentList(d) {
    const ul = ui.el("ul", "doc-list doc-list-compact result-wide");
    d.documents.forEach((doc) => {
      const item = ui.el("li", "doc");
      item.append(ui.el("span", "doc-name", doc.label));
      let state = "Missing";
      if (doc.uploaded) {
        state = `Uploaded ${ui.date(doc.uploaded_at)}`;
        if (doc.expires_on) state += `, valid until ${ui.date(doc.expires_on)}`;
        if (doc.expired) state = `Expired on ${ui.date(doc.expires_on)}`;
      }
      item.append(ui.el("span", `doc-state${!doc.uploaded || doc.expired ? " is-bad" : ""}`, state));
      if (doc.uploaded) {
        const actions = ui.el("div", "doc-actions");
        const view = ui.el("button", "btn-gray btn-sm", "View");
        view.type = "button";
        view.addEventListener("click", () =>
          ui.openFile(`/admin/drivers/${d.driver_id}/documents/${doc.type}/file`, view, msg));
        actions.append(view);
        item.append(actions);
      }
      ul.append(item);
    });
    return ul;
  }

  function button(d, action, label, style, body = () => ({})) {
    const b = ui.el("button", `${style} btn-sm`, label);
    b.type = "button";
    b.addEventListener("click", async () => {
      try {
        const { driver } = await ui.busy(b, "Saving…", () =>
          api.post(`/admin/drivers/${d.driver_id}/${action}`, body()),
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
