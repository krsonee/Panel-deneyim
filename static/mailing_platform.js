/* Mikromail superadmin platform UI */
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
    var cur = sel.value || (window.MAIL_TENANT_ID ? String(window.MAIL_TENANT_ID) : "");
    sel.innerHTML = '<option value="">— seç / impersonate —</option>' +
      (tenants || []).map(function (t) {
        return '<option value="' + esc(String(t.id)) + '">' +
          esc(t.slug) + " — " + esc(t.name) + " (" + esc(t.status) + ")</option>";
      }).join("");
    if (cur) sel.value = cur;
    if (!sel.value && tenants && tenants.length) {
      var makro = tenants.find(function (t) { return t.slug === "makro"; }) || tenants[0];
      if (makro) {
        sel.value = String(makro.id);
        api("/api/mail-auth/select-tenant", { method: "POST", body: { tenant_id: Number(makro.id) } })
          .then(function () {
            window.MAIL_TENANT_ID = Number(makro.id);
            var hint = document.getElementById("mm-tenant-hint");
            if (hint) hint.textContent = "Tenant #" + makro.id + " (" + makro.slug + ") otomatik seçildi";
          });
      }
    }
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

  var _editDomainId = null;
  var _domainSaving = false;

  function setDomainFormMode(editId, d) {
    _editDomainId = editId || null;
    var form = document.getElementById("mm-domain-form");
    var btn = form && form.querySelector('button[type="submit"]');
    var hint = document.getElementById("mm-domain-edit-hint");
    var domainInp = document.getElementById("mm-d-domain");
    if (!form) return;
    if (editId && d) {
      if (domainInp) {
        domainInp.value = d.domain || "";
        domainInp.readOnly = true;
      }
      document.getElementById("mm-d-from").value = d.from_name || "VIP";
      var localEl = document.getElementById("mm-d-local");
      if (localEl) localEl.value = d.from_local || "info";
      document.getElementById("mm-d-warm").value = d.warm_status || "cold";
      document.getElementById("mm-d-cap").value = d.daily_cap != null ? d.daily_cap : 500;
      document.getElementById("mm-d-smtp").value = "";
      document.getElementById("mm-d-smtp").placeholder = d.smtp_password_set ? "Boş = şifre aynı kalsın" : "SMTP şifresi";
      if (btn) {
        btn.textContent = "Domain kaydet";
        btn.disabled = false;
      }
      if (hint) hint.textContent = "Düzenleniyor: " + (d.from_local || "info") + "@" + (d.domain || ("#" + editId)) + " — iptal için Yenile";
      form.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      if (domainInp) domainInp.readOnly = false;
      if (btn) {
        btn.textContent = "Domain ekle";
        btn.disabled = false;
      }
      if (hint) hint.textContent = "";
      document.getElementById("mm-d-smtp").placeholder = "opsiyonel";
    }
  }

  function setDomainHint(msg, isError) {
    var hint = document.getElementById("mm-domain-edit-hint");
    if (!hint) return;
    hint.textContent = msg || "";
    hint.style.color = isError ? "#c0392b" : "";
  }

  function refreshDomains() {
    return api("/api/platform/domains").then(function (res) {
      var tbody = document.getElementById("mm-domains-table");
      if (!tbody) return;
      if (!res.ok) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.domains || [];
      window._mmDomainsCache = rows;
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Domain yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (d) {
        var alloc = (d.allocations || []).map(function (a) {
          return esc(a.slug) + (a.exclusive ? "*" : "");
        }).join(", ") || "—";
        var fromAddr = esc(d.from_local || "info") + "@" + esc(d.domain);
        var smtpTag = d.smtp_password_set ? " · SMTP ✓" : "";
        return "<tr>" +
          "<td>" + esc(d.domain) + "</td>" +
          "<td>" + fromAddr + smtpTag + "</td>" +
          "<td>" + esc(d.warm_status || "cold") + " · day " + esc(d.warm_day || 0) + "</td>" +
          "<td>" + esc(d.daily_cap) + "/g · " + esc(d.hourly_cap) + "/s</td>" +
          "<td>" + esc(d.health_score) + "</td>" +
          "<td>" + alloc + "</td>" +
          '<td style="white-space:nowrap;">' +
          '<button type="button" class="btn btn-sm mm-edit-domain" data-id="' + esc(d.id) + '">Düzenle</button> ' +
          '<button type="button" class="btn btn-sm mm-alloc" data-id="' + esc(d.id) + '">Tahsis</button> ' +
          '<button type="button" class="btn btn-sm mm-warm" data-id="' + esc(d.id) + '">Warming</button>' +
          "</td></tr>";
      }).join("");
    });
  }

  function resetDomainForm() {
    var form = document.getElementById("mm-domain-form");
    if (form) form.reset();
    setDomainFormMode(null);
  }

  function saveDomainForm(e) {
    e.preventDefault();
    if (_domainSaving) return;

    var form = e.target;
    var btn = form.querySelector('button[type="submit"]');
    var body = {
      from_name: document.getElementById("mm-d-from").value.trim(),
      from_local: (document.getElementById("mm-d-local") || {}).value
        ? document.getElementById("mm-d-local").value.trim()
        : "info",
      warm_status: document.getElementById("mm-d-warm").value,
      daily_cap: Number(document.getElementById("mm-d-cap").value) || 500
    };
    var smtp = document.getElementById("mm-d-smtp").value;
    if (smtp) body.smtp_password = smtp;

    if (!_editDomainId) {
      body.domain = document.getElementById("mm-d-domain").value.trim();
      body.smtp_password = smtp || "";
    }

    _domainSaving = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = _editDomainId ? "Kaydediliyor…" : "Ekleniyor…";
    }
    setDomainHint(_editDomainId ? "Kaydediliyor…" : "Ekleniyor…", false);

    var path = _editDomainId
      ? "/api/platform/domains/" + _editDomainId
      : "/api/platform/domains";
    var method = _editDomainId ? "PATCH" : "POST";

    api(path, { method: method, body: body })
      .then(function (res) {
        if (!res.ok) {
          var err = (res.data && res.data.error) || ("Kaydedilemedi (HTTP " + res.status + ")");
          if (res.status === 401 || res.status === 403) {
            err = "Oturum düşmüş — sayfayı yenile, tekrar giriş yap, sonra kaydet";
          }
          setDomainHint(err, true);
          return;
        }
        var saved = res.data.domain;
        resetDomainForm();
        setDomainHint(
          saved
            ? ("Kaydedildi: " + (saved.from_local || "info") + "@" + (saved.domain || ""))
            : "Domain kaydedildi",
          false
        );
        return refreshDomains().then(function () {
          if (window.MakroMailing && typeof window.MakroMailing.onShow === "function") {
            window.MakroMailing.onShow();
          }
        });
      })
      .catch(function () {
        setDomainHint("Bağlantı hatası — tekrar dene", true);
      })
      .finally(function () {
        _domainSaving = false;
        if (btn) {
          btn.disabled = false;
          btn.textContent = _editDomainId ? "Domain kaydet" : "Domain ekle";
        }
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
      document.getElementById("mm-domains-refresh")?.addEventListener("click", function () {
        resetDomainForm();
        refreshDomains();
      });
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
      document.getElementById("mm-domain-form")?.addEventListener("submit", saveDomainForm);
      document.addEventListener("click", function (e) {
        var sus = e.target.closest(".mm-suspend");
        if (sus) {
          var id = Number(sus.getAttribute("data-id"));
          var st = sus.getAttribute("data-status");
          api("/api/platform/tenants/" + id, { method: "PATCH", body: { status: st } }).then(refreshTenants);
          return;
        }
        var editBtn = e.target.closest(".mm-edit-domain");
        if (editBtn) {
          var eid = Number(editBtn.getAttribute("data-id"));
          var found = (window._mmDomainsCache || []).find(function (x) { return Number(x.id) === eid; });
          if (found) setDomainFormMode(eid, found);
          else setDomainHint("Domain listesi güncel değil — Yenile'ye bas", true);
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
          var tid = prompt("Tahsis edilecek tenant id? (Makro = 1)");
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
