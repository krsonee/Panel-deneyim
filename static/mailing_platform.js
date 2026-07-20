/* MakroMail superadmin platform UI */
(function () {
  function api(path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    return fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin"
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        return { ok: r.ok, status: r.status, data: data };
      });
    });
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadTenantSelect(tenants) {
    var sel = document.getElementById("mm-tenant-select");
    if (!sel) return;
    var cur = sel.value;
    sel.innerHTML = '<option value="">— seç / impersonate —</option>' +
      (tenants || []).map(function (t) {
        return '<option value="' + esc(String(t.id)) + '">' +
          esc(t.slug) + " — " + esc(t.name) + " (" + esc(t.status) + ")</option>";
      }).join("");
    if (cur) sel.value = cur;
  }

  function refreshTenants() {
    return api("/api/platform/tenants").then(function (res) {
      var tbody = document.getElementById("mm-tenants-table");
      if (!res.ok) {
        if (tbody) tbody.innerHTML = '<tr><td colspan="7" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.tenants || [];
      loadTenantSelect(rows);
      if (!tbody) return;
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Tenant yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (t) {
        return "<tr>" +
          "<td>" + esc(t.id) + "</td>" +
          "<td>" + esc(t.slug) + "</td>" +
          "<td>" + esc(t.name) + "</td>" +
          "<td>" + esc(t.status) + "</td>" +
          "<td>" + esc(t.max_sends_day) + "</td>" +
          "<td>" + esc(t.domain_count) + "</td>" +
          '<td><button type="button" class="btn btn-sm mm-suspend" data-id="' + esc(t.id) + '" data-status="' +
          (t.status === "active" ? "suspended" : "active") + '">' +
          (t.status === "active" ? "Askıya al" : "Aktifleştir") + "</button></td></tr>";
      }).join("");
    });
  }

  function refreshDomains() {
    return api("/api/platform/domains").then(function (res) {
      var tbody = document.getElementById("mm-domains-table");
      if (!tbody) return;
      if (!res.ok) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.domains || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Domain yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (d) {
        var alloc = (d.allocations || []).map(function (a) {
          return esc(a.slug) + (a.exclusive ? "*" : "");
        }).join(", ") || "—";
        return "<tr>" +
          "<td>" + esc(d.domain) + "</td>" +
          "<td>" + esc(d.warm_status || "cold") + " · day " + esc(d.warm_day || 0) + "</td>" +
          "<td>" + esc(d.daily_cap) + "/g · " + esc(d.hourly_cap) + "/s</td>" +
          "<td>" + esc(d.health_score) + "</td>" +
          "<td>" + alloc + "</td>" +
          '<td style="white-space:nowrap;">' +
          '<button type="button" class="btn btn-sm mm-alloc" data-id="' + esc(d.id) + '">Tahsis</button> ' +
          '<button type="button" class="btn btn-sm mm-warm" data-id="' + esc(d.id) + '">Warming</button>' +
          "</td></tr>";
      }).join("");
    });
  }

  var Platform = {
    init: function () {
      if (!window.MAIL_IS_SUPERADMIN) return;
      var sel = document.getElementById("mm-tenant-select");
      if (sel) {
        sel.addEventListener("change", function () {
          var tid = sel.value ? Number(sel.value) : null;
          api("/api/mail-auth/select-tenant", { method: "POST", body: { tenant_id: tid } }).then(function () {
            var hint = document.getElementById("mm-tenant-hint");
            if (hint) hint.textContent = tid ? ("Tenant #" + tid + " seçili") : "Tenant seçilmedi";
            window.MAIL_TENANT_ID = tid;
            if (window.MakroMailing && window.MakroMailing.onShow) window.MakroMailing.onShow();
          });
        });
      }
      document.getElementById("mm-tenants-refresh")?.addEventListener("click", refreshTenants);
      document.getElementById("mm-domains-refresh")?.addEventListener("click", refreshDomains);
      document.getElementById("mm-tenant-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        api("/api/platform/tenants", {
          method: "POST",
          body: {
            name: document.getElementById("mm-t-name").value.trim(),
            slug: document.getElementById("mm-t-slug").value.trim(),
            owner_username: document.getElementById("mm-t-user").value.trim(),
            owner_password: document.getElementById("mm-t-pass").value,
            max_sends_day: Number(document.getElementById("mm-t-cap").value) || 50000
          }
        }).then(function (res) {
          var hint = document.getElementById("mm-tenant-create-hint");
          if (!res.ok) {
            if (hint) hint.textContent = res.data.error || "Hata";
            return;
          }
          if (hint) hint.textContent = "OK — giriş: " + (res.data.login_hint || "");
          e.target.reset();
          refreshTenants();
        });
      });
      document.getElementById("mm-domain-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        api("/api/platform/domains", {
          method: "POST",
          body: {
            domain: document.getElementById("mm-d-domain").value.trim(),
            from_name: document.getElementById("mm-d-from").value.trim(),
            warm_status: document.getElementById("mm-d-warm").value,
            daily_cap: Number(document.getElementById("mm-d-cap").value) || 500,
            smtp_password: document.getElementById("mm-d-smtp").value
          }
        }).then(function (res) {
          if (!res.ok) { alert(res.data.error || "Hata"); return; }
          e.target.reset();
          refreshDomains();
        });
      });
      document.addEventListener("click", function (e) {
        var sus = e.target.closest(".mm-suspend");
        if (sus) {
          var id = Number(sus.getAttribute("data-id"));
          var st = sus.getAttribute("data-status");
          api("/api/platform/tenants/" + id, { method: "PATCH", body: { status: st } }).then(refreshTenants);
          return;
        }
        var warm = e.target.closest(".mm-warm");
        if (warm) {
          var did = Number(warm.getAttribute("data-id"));
          api("/api/platform/domains/" + did, { method: "PATCH", body: { warm_status: "warming", warm_day: 0 } })
            .then(refreshDomains);
          return;
        }
        var alloc = e.target.closest(".mm-alloc");
        if (alloc) {
          var domainId = Number(alloc.getAttribute("data-id"));
          var tid = prompt("Tahsis edilecek tenant id?");
          if (!tid) return;
          api("/api/platform/domains/" + domainId + "/allocate", {
            method: "POST",
            body: { tenant_id: Number(tid) }
          }).then(function (res) {
            if (!res.ok) alert(res.data.error || "Hata");
            refreshDomains();
            refreshTenants();
          });
        }
      });
      this.refresh();
    },
    refresh: function () {
      return Promise.all([refreshTenants(), refreshDomains()]);
    }
  };

  window.MakroMailPlatform = Platform;
})();
