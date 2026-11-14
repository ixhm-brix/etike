// Admin: verify bus companies so their trips appear in search.
(async function adminCompanies() {
  if (!auth.require("admin")) return;
  const list = document.getElementById("results");
  const loading = document.getElementById("loading");
  const msg = document.getElementById("msg");

  try {
    const { companies } = await api.get("/admin/companies");
    loading.hidden = true;
    if (!companies.length) {
      list.replaceWith(ui.empty("No bus companies yet",
        "Companies appear here once their collected data is loaded with data/scripts/load_data.py."));
      return;
    }
    list.append(...companies.map(card));
  } catch (err) {
    loading.hidden = true;
    ui.say(msg, err.message);
  }

  function card(c) {
    const li = ui.el("li", "result");
    li.append(
      ui.el("span", "result-time", c.name),
      ui.el("span", "result-price", c.registration_number),
      ui.el("span", "result-meta", c.contact_phone || "No phone recorded"),
      ui.el("span", "result-note", c.licence_number ? `Licence ${c.licence_number}` : "No licence recorded"),
    );
    const actions = ui.el("div", "result-actions");
    actions.append(ui.el("span", `status status-${c.is_verified ? "approved" : "pending"}`,
      c.is_verified ? "Verified" : "Not verified"));
    if (!c.is_verified) {
      const b = ui.el("button", "btn-black btn-sm", "Verify");
      b.type = "button";
      b.addEventListener("click", async () => {
        try {
          const { company } = await ui.busy(b, "Saving…", () =>
            api.post(`/admin/companies/${c.company_id}/verify`),
          );
          li.replaceWith(card(company));
          ui.say(msg, `${company.name} is verified. Its trips now show in search.`, "info");
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
