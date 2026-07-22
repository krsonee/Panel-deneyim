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

  function mmIcon(name) {
    var p = {
      edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/>',
      trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/>',
      warm: '<path d="M12 2v6"/><path d="M12 18v4"/><path d="m4.9 4.9 4.2 4.2"/><path d="m14.9 14.9 4.2 4.2"/><path d="M2 12h6"/><path d="M16 12h6"/>',
      alloc: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 11h-6"/><path d="M19 8v6"/>',
      pause: '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
      play: '<path d="M8 5v14l11-7z"/>'
    };
    return '<svg class="mm-ico" viewBox="0 0 24 24" aria-hidden="true">' + (p[name] || "") + "</svg>";
  }

  function mmIconBtn(cls, title, icon, extra) {
    return '<button type="button" class="btn btn-icon ' + cls + '" title="' + esc(title) + '" aria-label="' +
      esc(title) + '" ' + (extra || "") + ">" + mmIcon(icon) + "</button>";
  }

  function mmStatusBadge(status) {
    var s = String(status || "").toLowerCase();
    var cls = "mm-badge-muted";
    if (s === "warm" || s === "active" || s === "ok" || s === "done") cls = "mm-badge-ok";
    else if (s === "cold") cls = "mm-badge-info";
    else if (s === "warming" || s === "pending" || s === "queued") cls = "mm-badge-warn";
    else if (s === "burned" || s === "suspended" || s === "error" || s === "failed" || s === "unconfigured") cls = "mm-badge-danger";
    else if (s === "paused") cls = "mm-badge-muted";
    return '<span class="mm-badge ' + cls + '">' + esc(status || "—") + "</span>";
  }

  function mmWarmProgress(d) {
    var day = Number(d.warm_day || 0);
    var pct = Math.max(0, Math.min(100, Math.round((day / 30) * 100)));
    if (String(d.warm_status || "") === "warm") pct = 100;
    if (String(d.warm_status || "") === "cold") pct = Math.min(pct, 5);
    return '<div class="mm-warm-cell">' +
      mmStatusBadge(d.warm_status || "cold") +
      ' <span class="muted" style="font-size:0.68rem;">day ' + esc(day) + "</span>" +
      '<div class="mm-progress" title="Isınma günü / 30"><span style="width:' + pct + '%"></span></div>' +
      "</div>";
  }

  function mmHealthGauge(score) {
    var n = Math.max(0, Math.min(100, Number(score) || 0));
    return '<span class="mm-gauge-wrap"><span class="mm-gauge" style="--p:' + n + '"></span>' +
      "<span>" + esc(n) + "</span></span>";
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
        var suspend = t.status === "active";
        return "<tr>" +
          "<td>" + esc(t.id) + "</td>" +
          "<td>" + esc(t.slug) + "</td>" +
          "<td>" + esc(t.name) + "</td>" +
          "<td>" + mmStatusBadge(t.status) + "</td>" +
          "<td>" + esc(t.max_sends_day) + "</td>" +
          "<td>" + esc(t.domain_count) + "</td>" +
          "<td>" + mmIconBtn(
            "mm-suspend" + (suspend ? " btn-danger" : " btn-primary"),
            suspend ? "Askıya al" : "Aktifleştir",
            suspend ? "pause" : "play",
            'data-id="' + esc(t.id) + '" data-status="' + (suspend ? "suspended" : "active") + '"'
          ) + "</td></tr>";
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
      function domainActions(d) {
        return '<td style="white-space:nowrap;display:flex;gap:0.3rem;">' +
          mmIconBtn("mm-edit-domain", "Düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
          mmIconBtn("mm-alloc", "Tahsis", "alloc", 'data-id="' + esc(d.id) + '"') +
          mmIconBtn("mm-warm", "Warming başlat", "warm", 'data-id="' + esc(d.id) + '"') +
          "</td>";
      }
      tbody.innerHTML = rows.map(function (d) {
        var alloc = (d.allocations || []).map(function (a) {
          return esc(a.slug) + (a.exclusive ? "*" : "");
        }).join(", ") || "—";
        var fromAddr = esc(d.from_local || "info") + "@" + esc(d.domain);
        var smtpTag = d.smtp_password_set
          ? ' <span class="mm-badge mm-badge-ok">SMTP</span>'
          : ' <span class="mm-badge mm-badge-danger">SMTP yok</span>';
        return "<tr>" +
          "<td>" + esc(d.domain) + "</td>" +
          "<td>" + fromAddr + smtpTag + "</td>" +
          "<td>" + mmWarmProgress(d) + "</td>" +
          "<td>" + esc(d.daily_cap) + "/g · " + esc(d.hourly_cap) + "/s</td>" +
          "<td>" + mmHealthGauge(d.health_score) + "</td>" +
          "<td>" + alloc + "</td>" +
          domainActions(d) +
          "</tr>";
      }).join("");

      var wbody = document.getElementById("mm-warmup-table");
      if (wbody) {
        wbody.innerHTML = rows.map(function (d) {
          return "<tr>" +
            "<td>" + esc(d.domain) + "</td>" +
            "<td>" + mmStatusBadge(d.warm_status || "cold") + "</td>" +
            "<td>" + mmWarmProgress(d) + "</td>" +
            "<td>" + mmHealthGauge(d.health_score) + "</td>" +
            "<td>" + esc(d.daily_cap) + "/gün</td>" +
            '<td style="display:flex;gap:0.3rem;">' +
            mmIconBtn("mm-warm", "Warming başlat", "warm", 'data-id="' + esc(d.id) + '"') +
            mmIconBtn("mm-edit-domain", "Düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
            "</td></tr>";
        }).join("");
      }
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
