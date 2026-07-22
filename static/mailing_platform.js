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
      unlink: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/>',
      pause: '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>',
      play: '<path d="M8 5v14l11-7z"/>',
      eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>'
    };
    return '<svg class="mm-ico" viewBox="0 0 24 24" aria-hidden="true">' + (p[name] || "") + "</svg>";
  }

  function syncOperatorBadge(tid) {
    var badge = document.getElementById("mm-operator-badge");
    if (!badge) return;
    var id = tid != null ? Number(tid) : (window.MAIL_TENANT_ID ? Number(window.MAIL_TENANT_ID) : 0);
    if (id) {
      badge.hidden = false;
      var t = (window._mmTenantsCache || []).find(function (x) { return Number(x.id) === id; });
      badge.textContent = t
        ? ("Operatör · " + (t.slug || t.name || ("#" + id)))
        : ("Operatör · #" + id);
    } else {
      badge.hidden = true;
      badge.textContent = "Operatör";
    }
  }

  function syncPanelLoginFields() {
    var chk = document.getElementById("mm-t-panel-login");
    var wrap = document.getElementById("mm-t-login-fields");
    var user = document.getElementById("mm-t-user");
    var pass = document.getElementById("mm-t-pass");
    var on = !chk || chk.checked;
    if (wrap) wrap.style.display = on ? "" : "none";
    if (user) {
      user.required = on && !_editTenantId;
      if (!on) user.value = user.value || "admin";
    }
    if (pass) {
      pass.required = on && !_editTenantId;
      if (!on) pass.value = "";
    }
  }

  function hideTenantActivity() {
    var card = document.getElementById("mm-tenant-activity-card");
    if (card) card.hidden = true;
  }

  function showTenantActivity(tenantId) {
    var card = document.getElementById("mm-tenant-activity-card");
    if (!card) return;
    card.hidden = false;
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
    var title = document.getElementById("mm-tenant-activity-title");
    if (title) title.textContent = "Firma aktivitesi · yükleniyor…";
    api("/api/platform/tenants/" + tenantId + "/activity").then(function (res) {
      if (!res.ok) {
        if (title) title.textContent = "Firma aktivitesi · hata";
        return;
      }
      var t = res.data.tenant || {};
      var s = res.data.summary || {};
      if (title) title.textContent = "Firma aktivitesi · " + (t.name || t.slug || ("#" + tenantId));
      var set = function (id, v) {
        var el = document.getElementById(id);
        if (el) el.textContent = v == null ? "—" : String(v);
      };
      set("mm-act-kpi-camp", s.campaigns);
      set("mm-act-kpi-tpl", s.templates);
      set("mm-act-kpi-ok", s.sends_ok);
      set("mm-act-kpi-fail", s.sends_fail);
      var usersEl = document.getElementById("mm-act-users");
      var users = res.data.users || [];
      if (usersEl) {
        if (!users.length) {
          usersEl.textContent = "Panel kullanıcısı yok — sadece sen (süper admin) operatör olarak yönetiyorsun. Üstten bu firmayı seçip şablon/kampanya ekleyebilirsin.";
        } else {
          usersEl.textContent = "Panel kullanıcıları (" + users.length + "): " +
            users.map(function (u) {
              return (u.username || "?") + " (" + (u.role || "user") + ")";
            }).join(", ") +
            " · Kontak: " + (s.contacts || 0);
        }
      }
      var tbody = document.getElementById("mm-act-camps");
      var camps = res.data.campaigns || [];
      if (tbody) {
        if (!camps.length) {
          tbody.innerHTML = '<tr><td colspan="4" class="empty">Henüz kampanya yok</td></tr>';
        } else {
          tbody.innerHTML = camps.map(function (c) {
            var prog = (c.sent_count || 0) + "/" + (c.total_count || 0);
            if (c.failed_count) prog += " · fail " + c.failed_count;
            return "<tr>" +
              "<td>" + esc(c.name) + "</td>" +
              "<td>" + mmStatusBadge(c.status) + "</td>" +
              "<td>" + esc(prog) + "</td>" +
              "<td>" + esc(c.updated_at || c.created_at || "—") + "</td></tr>";
          }).join("");
        }
      }
    });
  }

  function mmIconBtn(cls, title, icon, extra) {
    return '<button type="button" class="btn btn-icon mm-tip-btn ' + cls + '" data-tip="' + esc(title) +
      '" title="' + esc(title) + '" aria-label="' + esc(title) + '" ' + (extra || "") + ">" +
      mmIcon(icon) + "</button>";
  }

  function mmStatusBadge(status) {
    var s = String(status || "").toLowerCase();
    var cls = "mm-badge-muted";
    if (s === "warm" || s === "active" || s === "ok" || s === "done") cls = "mm-badge-ok";
    else if (s === "cold") cls = "mm-badge-info";
    else if (s === "warming" || s === "pending" || s === "queued") cls = "mm-badge-warn";
    else if (s === "burned" || s === "suspended" || s === "error" || s === "failed" || s === "unconfigured" || s === "deleted") cls = "mm-badge-danger";
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

  function openModal(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.add("open");
    el.setAttribute("aria-hidden", "false");
  }

  function closeModal(id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove("open");
    el.setAttribute("aria-hidden", "true");
  }

  function loadTenantSelect(tenants) {
    var sel = document.getElementById("mm-tenant-select");
    if (!sel) return;
    var cur = sel.value || (window.MAIL_TENANT_ID ? String(window.MAIL_TENANT_ID) : "");
    var active = (tenants || []).filter(function (t) { return t.status !== "deleted"; });
    sel.innerHTML = '<option value="">— seç / impersonate —</option>' +
      active.map(function (t) {
        return '<option value="' + esc(String(t.id)) + '">' +
          esc(t.slug) + " — " + esc(t.name) + " (" + esc(t.status) + ")</option>";
      }).join("");
    if (cur) sel.value = cur;
    if (!sel.value && active.length) {
      var makro = active.find(function (t) { return t.slug === "makro"; }) || active[0];
      if (makro) {
        sel.value = String(makro.id);
        api("/api/mail-auth/select-tenant", { method: "POST", body: { tenant_id: Number(makro.id) } })
          .then(function () {
            window.MAIL_TENANT_ID = Number(makro.id);
            syncOperatorBadge(makro.id);
          });
      }
    } else {
      syncOperatorBadge(sel.value || window.MAIL_TENANT_ID);
    }
  }

  function fillAllocTenantSelect(tenants) {
    var sel = document.getElementById("mm-alloc-tenant");
    if (!sel) return;
    var active = (tenants || []).filter(function (t) { return t.status === "active" || t.status === "suspended"; });
    sel.innerHTML = active.map(function (t) {
      return '<option value="' + esc(String(t.id)) + '">#' + esc(t.id) + " · " +
        esc(t.slug) + " — " + esc(t.name) + "</option>";
    }).join("") || '<option value="">Tenant yok</option>';
  }

  var _editTenantId = null;

  function setTenantFormMode(editId, t) {
    _editTenantId = editId || null;
    var form = document.getElementById("mm-tenant-form");
    var btn = document.getElementById("mm-t-submit");
    var cancel = document.getElementById("mm-t-cancel-edit");
    var slug = document.getElementById("mm-t-slug");
    var user = document.getElementById("mm-t-user");
    var pass = document.getElementById("mm-t-pass");
    var hint = document.getElementById("mm-tenant-create-hint");
    var panelChk = document.getElementById("mm-t-panel-login");
    var loginWrap = document.getElementById("mm-t-login-fields");
    if (!form) return;
    if (editId && t) {
      document.getElementById("mm-t-name").value = t.name || "";
      if (slug) { slug.value = t.slug || ""; slug.readOnly = true; }
      document.getElementById("mm-t-cap").value = t.max_sends_day != null ? t.max_sends_day : 50000;
      if (panelChk) panelChk.checked = true;
      if (loginWrap) loginWrap.style.display = "none";
      if (user) { user.value = ""; user.required = false; user.placeholder = "değiştirme"; }
      if (pass) { pass.value = ""; pass.required = false; pass.placeholder = "değiştirme"; }
      if (btn) btn.textContent = "Firmayı kaydet";
      if (cancel) cancel.hidden = false;
      if (hint) hint.textContent = "Düzenleniyor: #" + t.id + " " + (t.slug || "");
      form.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      form.reset();
      if (slug) slug.readOnly = false;
      if (panelChk) panelChk.checked = true;
      if (user) { user.value = "admin"; user.placeholder = ""; }
      if (pass) { pass.placeholder = ""; }
      if (btn) btn.textContent = "Oluştur";
      if (cancel) cancel.hidden = true;
      if (hint) hint.textContent = "";
      _editTenantId = null;
      syncPanelLoginFields();
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
      window._mmTenantsCache = rows;
      loadTenantSelect(rows);
      fillAllocTenantSelect(rows);
      if (!tbody) return;
      var visible = rows.filter(function (t) { return t.status !== "deleted"; });
      if (!visible.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Tenant yok</td></tr>';
        return;
      }
      tbody.innerHTML = visible.map(function (t) {
        var suspend = t.status === "active";
        var panelTag = Number(t.user_count || 0) > 0
          ? ' <span class="mm-badge mm-badge-ok">panel</span>'
          : ' <span class="mm-badge mm-badge-info">operatör</span>';
        return "<tr>" +
          "<td>" + esc(t.id) + "</td>" +
          "<td>" + esc(t.slug) + "</td>" +
          "<td>" + esc(t.name) + panelTag + "</td>" +
          "<td>" + mmStatusBadge(t.status) + "</td>" +
          "<td>" + esc(t.max_sends_day) + "</td>" +
          "<td>" + esc(t.domain_count) + "</td>" +
          '<td class="mm-actions-cell">' +
          mmIconBtn("mm-activity-tenant", "Aktivite / ne yaptılar", "eye", 'data-id="' + esc(t.id) + '"') +
          mmIconBtn("mm-edit-tenant", "Firmayı düzenle", "edit", 'data-id="' + esc(t.id) + '"') +
          mmIconBtn(
            "mm-suspend" + (suspend ? "" : " btn-primary"),
            suspend ? "Askıya al" : "Aktif et",
            suspend ? "pause" : "play",
            'data-id="' + esc(t.id) + '" data-status="' + (suspend ? "suspended" : "active") + '"'
          ) +
          mmIconBtn("mm-del-tenant btn-danger", "Firmayı sil", "trash", 'data-id="' + esc(t.id) + '" data-name="' + esc(t.name || t.slug || "") + '"') +
          "</td></tr>";
      }).join("");
      syncOperatorBadge(window.MAIL_TENANT_ID);
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
    hint.style.color = isError ? "#fb7185" : "";
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
        var hasAlloc = (d.allocations || []).length > 0;
        return '<td class="mm-actions-cell">' +
          mmIconBtn("mm-edit-domain", "Domain düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
          mmIconBtn("mm-alloc", hasAlloc ? "Tahsis değiştir / kaldır" : "Firmaya tahsis et", "alloc", 'data-id="' + esc(d.id) + '"') +
          (hasAlloc
            ? mmIconBtn("mm-dealloc-all btn-danger", "Tüm tahsisleri kaldır", "unlink", 'data-id="' + esc(d.id) + '"')
            : "") +
          mmIconBtn("mm-warm", "Isınmaya al", "warm", 'data-id="' + esc(d.id) + '"') +
          "</td>";
      }
      tbody.innerHTML = rows.map(function (d) {
        var alloc = (d.allocations || []).map(function (a) {
          return '<span class="mm-badge mm-badge-info" style="margin:0 0.15rem 0.15rem 0;">' +
            esc(a.slug || a.name || ("#" + a.tenant_id)) +
            ' <button type="button" class="mm-dealloc-one" data-domain-id="' + esc(d.id) +
            '" data-tenant-id="' + esc(a.tenant_id) + '" title="Bu firmadan kaldır" ' +
            'style="border:0;background:transparent;color:inherit;cursor:pointer;padding:0 0 0 0.15rem;">×</button></span>';
        }).join(" ") || '<span class="muted">—</span>';
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
            '<td class="mm-actions-cell">' +
            mmIconBtn("mm-edit-domain", "Domain düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
            mmIconBtn("mm-alloc", "Firmaya tahsis et", "alloc", 'data-id="' + esc(d.id) + '"') +
            mmIconBtn("mm-warm", "Isınmaya al", "warm", 'data-id="' + esc(d.id) + '"') +
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

  function renderAllocCurrentList(domainId) {
    var list = document.getElementById("mm-alloc-current-list");
    if (!list) return;
    var d = (window._mmDomainsCache || []).find(function (x) { return Number(x.id) === Number(domainId); });
    var allocs = (d && d.allocations) || [];
    if (!allocs.length) {
      list.innerHTML = '<span class="muted">Henüz kimseye tahsis yok</span>';
      return;
    }
    list.innerHTML = allocs.map(function (a) {
      return '<div style="display:flex;align-items:center;gap:0.45rem;margin:0.25rem 0;">' +
        '<span class="mm-badge mm-badge-info">' + esc(a.slug || a.name || ("#" + a.tenant_id)) + "</span>" +
        '<button type="button" class="btn btn-sm btn-danger mm-dealloc-one" data-domain-id="' +
        esc(domainId) + '" data-tenant-id="' + esc(a.tenant_id) + '">Kaldır</button></div>';
    }).join("");
  }

  function openAllocModal(domainId) {
    var d = (window._mmDomainsCache || []).find(function (x) { return Number(x.id) === Number(domainId); });
    document.getElementById("mm-alloc-domain-id").value = String(domainId);
    var label = document.getElementById("mm-alloc-domain-label");
    if (label) label.textContent = d ? ("Domain: " + (d.domain || ("#" + domainId))) : ("Domain #" + domainId);
    fillAllocTenantSelect(window._mmTenantsCache || []);
    var replaceChk = document.getElementById("mm-alloc-replace");
    if (replaceChk) replaceChk.checked = true;
    renderAllocCurrentList(domainId);
    openModal("mm-alloc-modal");
  }

  function deallocDomain(domainId, tenantId, all) {
    var body = all ? { all: true } : { tenant_id: Number(tenantId) };
    return api("/api/platform/domains/" + domainId + "/deallocate", {
      method: "POST",
      body: body
    }).then(function (res) {
      if (!res.ok) {
        alert((res.data && res.data.error) || "Tahsis kaldırılamadı");
        return;
      }
      return refreshDomains().then(function () {
        var modal = document.getElementById("mm-alloc-modal");
        if (modal && modal.classList.contains("open")) {
          renderAllocCurrentList(domainId);
        }
        refreshTenants();
      });
    });
  }

  function openTenantDeleteModal(id, name) {
    document.getElementById("mm-tenant-del-id").value = String(id);
    var text = document.getElementById("mm-tenant-del-text");
    if (text) text.textContent = "“" + (name || ("#" + id)) + "” firmasını silmek istediğine emin misin? (soft-delete)";
    openModal("mm-tenant-del-modal");
  }

  var Platform = {
    init: function () {
      if (!window.MAIL_IS_SUPERADMIN) return;
      var sel = document.getElementById("mm-tenant-select");
      if (sel) {
        sel.addEventListener("change", function () {
          var tid = sel.value ? Number(sel.value) : null;
          api("/api/mail-auth/select-tenant", { method: "POST", body: { tenant_id: tid } }).then(function () {
            window.MAIL_TENANT_ID = tid;
            syncOperatorBadge(tid);
            if (window.MakroMailing && window.MakroMailing.refreshImports) {
              window.MakroMailing.refreshImports();
            } else if (window.MakroMailing && typeof window.MakroMailing.onShow === "function") {
              window.MakroMailing.onShow();
            }
          });
        });
      }
      document.getElementById("mm-t-panel-login")?.addEventListener("change", syncPanelLoginFields);
      syncPanelLoginFields();
      document.getElementById("mm-tenant-activity-close")?.addEventListener("click", hideTenantActivity);
      document.getElementById("mm-tenants-refresh")?.addEventListener("click", refreshTenants);
      document.getElementById("mm-domains-refresh")?.addEventListener("click", function () {
        resetDomainForm();
        refreshDomains();
      });
      document.getElementById("mm-t-cancel-edit")?.addEventListener("click", function () {
        setTenantFormMode(null);
      });
      document.getElementById("mm-tenant-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        var hint = document.getElementById("mm-tenant-create-hint");
        if (_editTenantId) {
          api("/api/platform/tenants/" + _editTenantId, {
            method: "PATCH",
            body: {
              name: document.getElementById("mm-t-name").value.trim(),
              max_sends_day: Number(document.getElementById("mm-t-cap").value) || 50000
            }
          }).then(function (res) {
            if (!res.ok) {
              if (hint) hint.textContent = (res.data && res.data.error) || "Kaydedilemedi";
              return;
            }
            if (hint) hint.textContent = "Firma güncellendi";
            setTenantFormMode(null);
            refreshTenants();
          });
          return;
        }
        var wantPanel = !!(document.getElementById("mm-t-panel-login") || { checked: true }).checked;
        api("/api/platform/tenants", {
          method: "POST",
          body: {
            name: document.getElementById("mm-t-name").value.trim(),
            slug: document.getElementById("mm-t-slug").value.trim(),
            owner_username: document.getElementById("mm-t-user").value.trim() || "admin",
            owner_password: wantPanel ? document.getElementById("mm-t-pass").value : "",
            create_panel_login: wantPanel,
            max_sends_day: Number(document.getElementById("mm-t-cap").value) || 50000
          }
        }).then(function (res) {
          if (!res.ok) {
            if (hint) hint.textContent = (res.data && res.data.error) || "Hata";
            return;
          }
          if (hint) {
            hint.textContent = res.data.operator_only
              ? "OK — firma açıldı (panel yok). Üstten seçip sen yönet."
              : ("OK — panel girişi: " + (res.data.login_hint || ""));
          }
          setTenantFormMode(null);
          refreshTenants();
        });
      });
      document.getElementById("mm-domain-form")?.addEventListener("submit", saveDomainForm);

      document.getElementById("mm-alloc-cancel")?.addEventListener("click", function () {
        closeModal("mm-alloc-modal");
      });
      document.getElementById("mm-alloc-clear")?.addEventListener("click", function () {
        var domainId = Number(document.getElementById("mm-alloc-domain-id").value);
        if (!domainId) return;
        if (!confirm("Bu domaini tüm firmalardan kaldırmak istediğine emin misin?")) return;
        deallocDomain(domainId, null, true).then(function () {
          closeModal("mm-alloc-modal");
        });
      });
      document.getElementById("mm-alloc-confirm")?.addEventListener("click", function () {
        var domainId = Number(document.getElementById("mm-alloc-domain-id").value);
        var tid = Number(document.getElementById("mm-alloc-tenant").value);
        var replace = !!(document.getElementById("mm-alloc-replace") || { checked: true }).checked;
        if (!domainId || !tid) return;
        api("/api/platform/domains/" + domainId + "/allocate", {
          method: "POST",
          body: { tenant_id: tid, replace: replace }
        }).then(function (res) {
          if (!res.ok) {
            alert((res.data && res.data.error) || "Tahsis başarısız");
            return;
          }
          closeModal("mm-alloc-modal");
          refreshDomains();
          refreshTenants();
        });
      });
      document.getElementById("mm-tenant-del-cancel")?.addEventListener("click", function () {
        closeModal("mm-tenant-del-modal");
      });
      document.getElementById("mm-tenant-del-confirm")?.addEventListener("click", function () {
        var id = Number(document.getElementById("mm-tenant-del-id").value);
        if (!id) return;
        api("/api/platform/tenants/" + id, { method: "DELETE" }).then(function (res) {
          if (!res.ok) {
            alert((res.data && res.data.error) || "Silinemedi");
            return;
          }
          closeModal("mm-tenant-del-modal");
          if (_editTenantId === id) setTenantFormMode(null);
          refreshTenants();
        });
      });
      document.getElementById("mm-alloc-modal")?.addEventListener("click", function (e) {
        if (e.target.id === "mm-alloc-modal") closeModal("mm-alloc-modal");
      });
      document.getElementById("mm-tenant-del-modal")?.addEventListener("click", function (e) {
        if (e.target.id === "mm-tenant-del-modal") closeModal("mm-tenant-del-modal");
      });

      document.addEventListener("click", function (e) {
        var sus = e.target.closest(".mm-suspend");
        if (sus) {
          var id = Number(sus.getAttribute("data-id"));
          var st = sus.getAttribute("data-status");
          api("/api/platform/tenants/" + id, { method: "PATCH", body: { status: st } }).then(refreshTenants);
          return;
        }
        var actTenant = e.target.closest(".mm-activity-tenant");
        if (actTenant) {
          showTenantActivity(Number(actTenant.getAttribute("data-id")));
          return;
        }
        var editTenant = e.target.closest(".mm-edit-tenant");
        if (editTenant) {
          var tidEdit = Number(editTenant.getAttribute("data-id"));
          var foundT = (window._mmTenantsCache || []).find(function (x) { return Number(x.id) === tidEdit; });
          if (foundT) setTenantFormMode(tidEdit, foundT);
          return;
        }
        var delTenant = e.target.closest(".mm-del-tenant");
        if (delTenant) {
          openTenantDeleteModal(
            Number(delTenant.getAttribute("data-id")),
            delTenant.getAttribute("data-name") || ""
          );
          return;
        }
        var editBtn = e.target.closest(".mm-edit-domain");
        if (editBtn) {
          var eid = Number(editBtn.getAttribute("data-id"));
          var found = (window._mmDomainsCache || []).find(function (x) { return Number(x.id) === eid; });
          if (found) {
            if (window.mmNavigate) window.mmNavigate("plat-domains");
            setDomainFormMode(eid, found);
          } else setDomainHint("Domain listesi güncel değil — Yenile'ye bas", true);
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
          openAllocModal(Number(alloc.getAttribute("data-id")));
          return;
        }
        var deallocAll = e.target.closest(".mm-dealloc-all");
        if (deallocAll) {
          var didAll = Number(deallocAll.getAttribute("data-id"));
          if (!confirm("Bu domaini tüm firmalardan kaldırmak istediğine emin misin?")) return;
          deallocDomain(didAll, null, true);
          return;
        }
        var deallocOne = e.target.closest(".mm-dealloc-one");
        if (deallocOne) {
          deallocDomain(
            Number(deallocOne.getAttribute("data-domain-id")),
            Number(deallocOne.getAttribute("data-tenant-id")),
            false
          );
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
