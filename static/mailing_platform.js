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
    }).catch(function (err) {
      // fetch() reddi (offline/DNS/timeout) yakalanmazsa çağıran .then() zinciri
      // hiç çalışmaz — 28 çağrı noktasının 27'sinde sessiz başarısızlık oluyordu.
      return { ok: false, status: 0, data: { error: "Ağ hatası: " + (err && err.message ? err.message : "bağlantı kurulamadı") } };
    });
  }

  /** Render/proxy ara sıra ilk POST cevabını düşürüyor (~30s Load failed).
   * status=0 ise bir kez daha dene — domain eklemede "hata sandım, tekrar basınca oldu" senaryosu. */
  function apiRetry(path, opts, left) {
    left = left == null ? 1 : left;
    return api(path, opts).then(function (res) {
      if (res.status === 0 && left > 0) {
        return new Promise(function (resolve) {
          setTimeout(function () {
            resolve(apiRetry(path, opts, left - 1));
          }, 1200);
        });
      }
      return res;
    });
  }

  function findDomainByName(name) {
    var n = String(name || "").trim().toLowerCase();
    if (!n) return null;
    return (window._mmDomainsCache || []).find(function (d) {
      return String(d.domain || "").toLowerCase() === n;
    }) || null;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtCr(n) {
    try { return Number(n || 0).toLocaleString("tr-TR"); } catch (e) { return String(n); }
  }

  /** Sunucu UTC ISO zaman damgalarını TR yerel saatine çevirir — mailing.js'teki
   * fmtTime() ile aynı davranış (bu dosyada eşdeğeri yoktu, ham UTC string'ler
   * doğrudan admin'e gösteriliyordu, ör. "son auto-run" 3 saat geride görünüyordu). */
  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return String(iso);
      return d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
    } catch (e) {
      return String(iso);
    }
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
      eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8S1 12 1 12z"/><circle cx="12" cy="12" r="3"/>',
      key: '<path d="M21 2 11.6 11.4"/><path d="m15.5 7.5 3 3L22 7l-3-3"/><circle cx="7.5" cy="15.5" r="5.5"/>'
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

  // NOT: "mailing.settings" bilerek YOK — Sistem Ayarları SADECE süper admin
  // hesabında olur, firma kullanıcısına buradan asla verilemez (backend'de de
  // sert bloklu, bkz mailing_app.py _mail_permission_required).
  var MAILING_PERM_KEYS = [
    { key: "mailing.dashboard", label: "Mailing Özet" },
    { key: "mailing.crm", label: "Mail Rehber" },
    { key: "mailing.relations", label: "CRM (İlişki)" },
    { key: "mailing.templates", label: "Mail Şablonları" },
    { key: "mailing.campaigns", label: "Kampanyalar" },
    { key: "mailing.ivr", label: "IVR Tetikleme" },
    { key: "mailing.reports", label: "Mailing Raporları" }
  ];

  var _activityTenantId = null;
  var _activityCampaigns = [];

  function hideTenantActivity() {
    var card = document.getElementById("mm-tenant-activity-card");
    if (card) card.hidden = true;
    _activityTenantId = null;
  }

  /** UTC ISO -> <input type="datetime-local"> değeri (yerel saat, saniyesiz). */
  function isoToLocalInput(iso) {
    if (!iso) return "";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return "";
      var pad = function (n) { return String(n).padStart(2, "0"); };
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
        "T" + pad(d.getHours()) + ":" + pad(d.getMinutes());
    } catch (e) { return ""; }
  }

  /** <input type="datetime-local"> değeri -> UTC ISO string. */
  function localInputToIso(val) {
    if (!val) return null;
    var d = new Date(val);
    if (isNaN(d.getTime())) return null;
    return d.toISOString();
  }

  function renderCutoffBox(t) {
    var status = document.getElementById("mm-cutoff-status");
    var dt = document.getElementById("mm-cutoff-datetime");
    var pick = document.getElementById("mm-cutoff-campaign-pick");
    if (status) {
      status.textContent = t.data_visible_from
        ? ("Aktif — " + fmtTime(t.data_visible_from) + " öncesi bu firmaya gösterilmiyor.")
        : "Kısıtlama yok — bu firma tüm geçmişi görüyor.";
    }
    if (dt) dt.value = isoToLocalInput(t.data_visible_from);
    if (pick) {
      pick.innerHTML = '<option value="">— bir kampanya seç —</option>' +
        _activityCampaigns.map(function (c) {
          return '<option value="' + esc(c.created_at || "") + '">' +
            esc(c.name || ("#" + c.id)) + " · " + esc(fmtTime(c.created_at)) + "</option>";
        }).join("");
    }
  }

  function renderTenantUsersTable(tenantId, users) {
    var tbody = document.getElementById("mm-act-user-rows");
    if (!tbody) return;
    if (!users || !users.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Henüz panel kullanıcısı yok</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(function (u) {
      var permCount = (u.permissions || []).filter(function (p) { return p !== "module.mailing"; }).length;
      var activeBadge = u.active
        ? '<span class="mm-badge mm-badge-ok">aktif</span>'
        : '<span class="mm-badge mm-badge-danger">pasif</span>';
      // Güvenlik durumu: ilk girişte zorunlu şifre değişikliği + zorunlu
      // Google Authenticator (TOTP) — ikisi de tamamlanmadan panele giremez.
      var secBadges = "";
      if (u.must_change_password) {
        secBadges += '<span class="mm-badge mm-badge-warn" title="Kullanıcı ilk girişte şifresini değiştirmek zorunda">şifre bekliyor</span> ';
      }
      secBadges += u.totp_enabled
        ? '<span class="mm-badge mm-badge-ok" title="Google Authenticator kurulu">2FA aktif</span>'
        : '<span class="mm-badge mm-badge-danger" title="Kullanıcı ilk girişte Authenticator kurmak zorunda">2FA bekliyor</span>';
      return "<tr>" +
        "<td>" + esc(u.username) + "</td>" +
        "<td>" + esc(u.display_name || "") + "</td>" +
        "<td>" + activeBadge + "</td>" +
        '<td style="white-space:nowrap;">' + secBadges + "</td>" +
        "<td>" + permCount + " / " + MAILING_PERM_KEYS.length + "</td>" +
        '<td class="mm-actions-cell">' +
        mmIconBtn("mm-user-edit", "Düzenle / yetkiler", "edit",
          'data-tid="' + esc(tenantId) + '" data-uid="' + esc(u.id) + '"') +
        mmIconBtn("mm-user-reset-pass", "Şifre sıfırla", "key",
          'data-tid="' + esc(tenantId) + '" data-uid="' + esc(u.id) + '" data-username="' + esc(u.username) + '"') +
        mmIconBtn("mm-user-reset-totp", "2FA sıfırla (Authenticator'ı yeniden kurmaya zorla)", "shield",
          'data-tid="' + esc(tenantId) + '" data-uid="' + esc(u.id) + '" data-username="' + esc(u.username) + '"') +
        mmIconBtn(u.active ? "mm-user-del btn-danger" : "mm-user-del",
          u.active ? "Devre dışı bırak" : "Yeniden aktif et", u.active ? "trash" : "play",
          'data-tid="' + esc(tenantId) + '" data-uid="' + esc(u.id) + '" data-username="' + esc(u.username) + '" data-active="' + (u.active ? "1" : "0") + '"') +
        "</td></tr>";
    }).join("");
  }

  function refreshTenantUsersTable(tenantId) {
    return apiRetry("/api/platform/tenants/" + tenantId + "/users").then(function (res) {
      if (!res.ok) return;
      renderTenantUsersTable(tenantId, res.data.users || []);
    });
  }

  function showTenantActivity(tenantId) {
    var card = document.getElementById("mm-tenant-activity-card");
    if (!card) return;
    _activityTenantId = tenantId;
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
      if (usersEl) usersEl.textContent = "Kontak: " + (s.contacts || 0);
      var tbody = document.getElementById("mm-act-camps");
      var camps = res.data.campaigns || [];
      _activityCampaigns = camps;
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
              "<td>" + esc(fmtTime(c.updated_at || c.created_at)) + "</td></tr>";
          }).join("");
        }
      }
      renderCutoffBox(t);
      refreshTenantUsersTable(tenantId);
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

  function mmHealthGauge(score, note) {
    var n = Math.max(0, Math.min(100, Number(score) || 0));
    var title = note ? (' title="' + esc(note) + '"') : "";
    return '<span class="mm-gauge-wrap"' + title + '><span class="mm-gauge" style="--p:' + n + '"></span>' +
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
    // Boş değer = "Tümü" — TÜM firmaların genel toplamı + firma firma kartlar
    // (bkz. mailLoadDashboard). Önceden burada otomatik "makro" seçiliyordu ve
    // "Tümü" görünümüne hiç geçilemiyordu; artık bilinçli/sticky bir seçim.
    sel.innerHTML = '<option value="">— Tümü (genel) —</option>' +
      active.map(function (t) {
        return '<option value="' + esc(String(t.id)) + '">' +
          esc(t.slug) + " — " + esc(t.name) + " (" + esc(t.status) + ")</option>";
      }).join("");
    sel.value = cur || "";
    syncOperatorBadge(sel.value || window.MAIL_TENANT_ID);
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
      var crEl = document.getElementById("mm-t-credit");
      if (crEl) crEl.value = t.credit_allocated != null ? t.credit_allocated : 0;
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
        if (tbody) tbody.innerHTML = '<tr><td colspan="8" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.tenants || [];
      window._mmTenantsCache = rows;
      loadTenantSelect(rows);
      fillAllocTenantSelect(rows);
      if (!tbody) return;
      var visible = rows.filter(function (t) { return t.status !== "deleted"; });
      if (!visible.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="empty">Tenant yok</td></tr>';
        return;
      }
      tbody.innerHTML = visible.map(function (t) {
        var suspend = t.status === "active";
        var panelTag = Number(t.user_count || 0) > 0
          ? ' <span class="mm-badge mm-badge-ok">panel</span>'
          : ' <span class="mm-badge mm-badge-info">operatör</span>';
        var crAlloc = Number(t.credit_allocated || 0);
        var crUsed = Number(t.credit_used || 0);
        var crRem = crAlloc > 0 ? (crAlloc - crUsed) : null;
        var crCell = crAlloc > 0
          ? (fmtCr(crRem) + " / " + fmtCr(crAlloc))
          : '<span class="muted">tahsis yok</span>';
        return "<tr>" +
          "<td>" + esc(t.id) + "</td>" +
          "<td>" + esc(t.slug) + "</td>" +
          "<td>" + esc(t.name) + panelTag + "</td>" +
          "<td>" + mmStatusBadge(t.status) + "</td>" +
          "<td>" + esc(t.max_sends_day) + "</td>" +
          "<td>" + crCell + "</td>" +
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

  function renderAccountQuota(q) {
    if (!q) return;
    var rem = document.getElementById("mm-aq-remaining");
    var used = document.getElementById("mm-aq-used");
    var renew = document.getElementById("mm-aq-renew");
    var fill = document.getElementById("mm-aq-fill");
    var lim = document.getElementById("mm-aq-limit");
    var tz = document.getElementById("mm-aq-tz");
    var hint = document.getElementById("mm-aq-hint");
    function fmt(n) {
      try { return Number(n || 0).toLocaleString("tr-TR"); } catch (e) { return String(n); }
    }
    if (rem) rem.textContent = "Kalan " + fmt(q.remaining);
    if (used) used.textContent = "kullanılan " + fmt(q.used) + " / " + fmt(q.limit);
    if (renew) renew.textContent = "yenilenme: " + (q.renews_at_label || "—");
    if (fill) {
      var pct = Math.min(100, Math.max(0, Number(q.pct_used) || 0));
      fill.style.width = pct + "%";
      fill.classList.toggle("is-warn", pct >= 70 && pct < 90);
      fill.classList.toggle("is-danger", pct >= 90 || !!q.exhausted);
    }
    if (lim && document.activeElement !== lim) lim.value = q.limit;
    if (tz && document.activeElement !== tz) tz.value = q.tz || "UTC";
    if (hint) {
      hint.textContent = q.exhausted
        ? ("Kota dolu — kampanya başlatılmaz. " + (q.renews_at_label || ""))
        : "Limit Alibaba’daki hesap kotasıyla eşleşmeli. Panel kalanı mail_sends üzerinden sayar.";
    }
  }

  function refreshAccountQuota() {
    return api("/api/platform/account-quota").then(function (res) {
      if (res.ok && res.data.quota) renderAccountQuota(res.data.quota);
    }).catch(function () {});
  }

  function renderMailCredit(credit, tenants) {
    if (!credit) return;
    var rem = document.getElementById("mm-cr-remaining");
    var usedLbl = document.getElementById("mm-cr-used-lbl");
    var alloc = document.getElementById("mm-cr-alloc");
    var fill = document.getElementById("mm-cr-fill");
    var hint = document.getElementById("mm-cr-hint");
    var totalInp = document.getElementById("mm-cr-total");
    var usedInp = document.getElementById("mm-cr-used");
    if (rem) rem.textContent = "Kalan " + fmtCr(credit.remaining);
    if (usedLbl) usedLbl.textContent = "kullanılan " + fmtCr(credit.used) + " / " + fmtCr(credit.total);
    if (alloc) {
      alloc.textContent = "tahsis " + fmtCr(credit.allocated_to_tenants) +
        " · serbest " + fmtCr(credit.unallocated);
    }
    if (fill) {
      var pct = Math.min(100, Math.max(0, Number(credit.pct_used) || 0));
      fill.style.width = pct + "%";
      fill.classList.toggle("is-warn", pct >= 70 && pct < 90);
      fill.classList.toggle("is-danger", pct >= 90 || !!credit.exhausted);
    }
    if (totalInp && document.activeElement !== totalInp) totalInp.value = credit.total;
    if (usedInp && document.activeElement !== usedInp) usedInp.value = credit.used;
    if (hint) {
      hint.textContent = credit.exhausted
        ? "Paket bitti — top-up yap."
        : "Firma oluştururken kredi tahsis et; tahsis edilmeyen firma gönderemez.";
    }
    var tbody = document.getElementById("mm-cr-tenants");
    if (tbody) {
      var rows = tenants || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Firma yok</td></tr>';
      } else {
        tbody.innerHTML = rows.map(function (t) {
          var remT = t.credit_remaining == null ? "—" : fmtCr(t.credit_remaining);
          return "<tr>" +
            "<td>" + esc(t.slug || t.name) + "</td>" +
            "<td>" + fmtCr(t.credit_allocated) + "</td>" +
            "<td>" + fmtCr(t.credit_used) + "</td>" +
            "<td>" + remT + "</td>" +
            '<td><button type="button" class="btn btn-sm btn-secondary mm-cr-alloc-btn" data-id="' +
            esc(t.id) + '" data-alloc="' + esc(t.credit_allocated) + '">Tahsis</button></td></tr>';
        }).join("");
      }
    }
  }

  function refreshMailCredit() {
    return api("/api/platform/mail-credit").then(function (res) {
      if (res.ok) renderMailCredit(res.data.credit, res.data.tenants);
    }).catch(function () {});
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
      var cohortEl = document.getElementById("mm-d-cohort");
      if (cohortEl) cohortEl.value = d.warmup_cohort === "legacy" ? "legacy" : "new";
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

  var MM_DOMAINS_PAGE_SIZE = 25;
  window._mmDomainsPage = window._mmDomainsPage || 1;

  function domainActions(d) {
    var hasAlloc = (d.allocations || []).length > 0;
    var isPaused = d.warm_status === "paused" || d.warm_status === "burned";
    return '<td class="mm-actions-cell">' +
      mmIconBtn("mm-edit-domain", "Domain düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
      mmIconBtn("mm-alloc", hasAlloc ? "Tahsis değiştir / kaldır" : "Firmaya tahsis et", "alloc", 'data-id="' + esc(d.id) + '"') +
      (hasAlloc
        ? mmIconBtn("mm-dealloc-all btn-danger", "Tüm tahsisleri kaldır", "unlink", 'data-id="' + esc(d.id) + '"')
        : "") +
      (isPaused
        ? mmIconBtn("mm-unpause-domain btn-primary", "Pause'u geri al (health sıfırlanır)", "play", 'data-id="' + esc(d.id) + '"')
        : mmIconBtn("mm-warm", "Isınmaya al", "warm", 'data-id="' + esc(d.id) + '"')) +
      "</td>";
  }

  function mmDomainRowHtml(d) {
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
      '<td style="max-width:220px;word-break:break-word;">' + esc(d.domain) +
      (d.warmup_cohort === "legacy"
        ? ' <span class="mm-badge mm-badge-info">eski</span>'
        : ' <span class="mm-badge mm-badge-warn">yeni</span>') +
      "</td>" +
      "<td>" + fromAddr + smtpTag + "</td>" +
      "<td>" + mmWarmProgress(d) + "</td>" +
      "<td>" + esc(d.daily_cap) + "/g · " + esc(d.hourly_cap) + "/s</td>" +
      "<td>" + mmHealthGauge(d.health_score, d.health_note) + "</td>" +
      '<td style="min-width:140px;">' + alloc + "</td>" +
      domainActions(d) +
      "</tr>";
  }

  function mmRenderDomainsStats(rows) {
    var total = rows.length, active = 0, warming = 0, passive = 0;
    rows.forEach(function (d) {
      var s = d.warm_status || "cold";
      if (s === "warm") active++;
      else if (s === "warming" || s === "cold") warming++;
      else if (s === "paused" || s === "burned") passive++;
    });
    setText2("mm-domains-stat-total", total);
    setText2("mm-domains-stat-active", active);
    setText2("mm-domains-stat-warming", warming);
    setText2("mm-domains-stat-passive", passive);
  }

  function setText2(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = String(val);
  }

  function mmRenderDomainsPager(totalRows) {
    var pager = document.getElementById("mm-domains-pager");
    if (!pager) return;
    var pageCount = Math.max(1, Math.ceil(totalRows / MM_DOMAINS_PAGE_SIZE));
    if (window._mmDomainsPage > pageCount) window._mmDomainsPage = pageCount;
    if (pageCount <= 1) { pager.innerHTML = ""; return; }
    var page = window._mmDomainsPage;
    pager.innerHTML =
      '<button type="button" class="btn btn-sm" id="mm-domains-prev"' + (page <= 1 ? " disabled" : "") + '>‹ Önceki</button>' +
      '<span class="mm-pager-info">Sayfa ' + page + ' / ' + pageCount + ' · ' + totalRows + ' domain</span>' +
      '<button type="button" class="btn btn-sm" id="mm-domains-next"' + (page >= pageCount ? " disabled" : "") + '>Sonraki ›</button>';
    var prevBtn = document.getElementById("mm-domains-prev");
    var nextBtn = document.getElementById("mm-domains-next");
    if (prevBtn) prevBtn.addEventListener("click", function () {
      if (window._mmDomainsPage > 1) { window._mmDomainsPage--; mmRenderDomainsTable(); }
    });
    if (nextBtn) nextBtn.addEventListener("click", function () {
      if (window._mmDomainsPage < pageCount) { window._mmDomainsPage++; mmRenderDomainsTable(); }
    });
  }

  function mmRenderDomainsTable() {
    var tbody = document.getElementById("mm-domains-table");
    if (!tbody) return;
    var rows = window._mmDomainsCache || [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Domain yok</td></tr>';
      mmRenderDomainsPager(0);
      return;
    }
    var start = (window._mmDomainsPage - 1) * MM_DOMAINS_PAGE_SIZE;
    var pageRows = rows.slice(start, start + MM_DOMAINS_PAGE_SIZE);
    tbody.innerHTML = pageRows.map(mmDomainRowHtml).join("");
    mmRenderDomainsPager(rows.length);
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
      mmRenderDomainsStats(rows);
      mmRenderDomainsTable();
      if (!rows.length) {
        return;
      }

      var wbody = document.getElementById("mm-warmup-table");
      if (wbody) {
        wbody.innerHTML = rows.map(function (d) {
          var isPaused = d.warm_status === "paused" || d.warm_status === "burned";
          return "<tr>" +
            "<td>" + esc(d.domain) + "</td>" +
            "<td>" + mmStatusBadge(d.warm_status || "cold") +
              (isPaused && d.health_note
                ? ' <span class="mm-tip" tabindex="0" data-tip="' + esc(d.health_note) + '">?</span>'
                : "") +
              "</td>" +
            "<td>" + mmWarmProgress(d) + "</td>" +
            "<td>" + mmHealthGauge(d.health_score, d.health_note) + "</td>" +
            "<td>" + esc(d.daily_cap) + "/gün</td>" +
            '<td class="mm-actions-cell">' +
            mmIconBtn("mm-edit-domain", "Domain düzenle", "edit", 'data-id="' + esc(d.id) + '"') +
            mmIconBtn("mm-alloc", "Firmaya tahsis et", "alloc", 'data-id="' + esc(d.id) + '"') +
            (isPaused
              ? mmIconBtn("mm-unpause-domain btn-primary", "Pause'u geri al (health sıfırlanır)", "play", 'data-id="' + esc(d.id) + '"')
              : mmIconBtn("mm-warm", "Isınmaya al", "warm", 'data-id="' + esc(d.id) + '"')) +
            "</td></tr>";
        }).join("");
      }
    });
  }

  var _wuSelected = {};
  var _wuCohort = "legacy";
  var _wuProgramFull = null;

  function activeWarmupTrack(program) {
    if (!program) return null;
    if (program.tracks && program.tracks[_wuCohort]) return program.tracks[_wuCohort];
    return program;
  }

  function setWuCohortTab(cohort) {
    _wuCohort = cohort === "new" ? "new" : "legacy";
    var leg = document.getElementById("mm-wu-tab-legacy");
    var neu = document.getElementById("mm-wu-tab-new");
    if (leg) {
      leg.classList.toggle("is-active", _wuCohort === "legacy");
      leg.setAttribute("aria-selected", _wuCohort === "legacy" ? "true" : "false");
    }
    if (neu) {
      neu.classList.toggle("is-active", _wuCohort === "new");
      neu.setAttribute("aria-selected", _wuCohort === "new" ? "true" : "false");
    }
    _wuSelected = {};
    if (_wuProgramFull) renderWarmupProgram(_wuProgramFull);
  }

  function applyWarmupBanner(program) {
    var banner = document.getElementById("mm-warmup-banner");
    var text = document.getElementById("mm-warmup-banner-text");
    if (!banner) return;
    var show = program && program.banner && program.banner.show;
    banner.hidden = !show;
    if (text) text.textContent = (program && program.banner && program.banner.text) || "Isıtma görevleri bekliyor";
  }

  function renderWarmupProgram(program) {
    window._mmWarmupProgram = program || null;
    _wuProgramFull = program || null;
    applyWarmupBanner(program);
    var track = activeWarmupTrack(program);
    var statusEl = document.getElementById("mm-wu-status");
    var setup = document.getElementById("mm-wu-setup");
    var todayBox = document.getElementById("mm-wu-today");
    var startBtn = document.getElementById("mm-wu-start");
    var pauseBtn = document.getElementById("mm-wu-pause");
    var resumeBtn = document.getElementById("mm-wu-resume");
    if (!program || !track) {
      if (statusEl) statusEl.textContent = "Program yüklenemedi";
      return;
    }
    var cohortLabel = track.cohort_label || (_wuCohort === "new" ? "Yeni" : "Eski");
    if (statusEl) {
      if (!track.active) {
        statusEl.textContent = track.started_on
          ? (cohortLabel + " program duraklatıldı · başlangıç " + track.started_on)
          : (cohortLabel + " program henüz başlamadı. Yalnız bu gruptan domain seç.");
      } else if (track.all_done_today) {
        statusEl.textContent = cohortLabel + " · bugünün görevleri tamam.";
      } else {
        var tgt = (track.plan && track.plan.per_domain_target) || "—";
        var sug = (track.plan && track.plan.daily_cap_suggest) || "—";
        var real = track.cap_reality && track.cap_reality.min_daily_cap;
        var gap = track.activity_gap_days || 0;
        var lastSend = track.last_send_date || "—";
        statusEl.textContent =
          cohortLabel + " aktif · Gün " + track.day + "/" + track.total_days +
          " · ~" + tgt + "/domain · daily_cap " + sug +
          (real != null ? (" · min cap " + real) : "") +
          " · son gönderim " + lastSend +
          (gap >= 2 ? (" · gap " + gap + "g") : "");
      }
      if (track.realign_note) statusEl.textContent += " · " + track.realign_note;
    }
    if (setup) setup.hidden = !!track.active;
    if (todayBox) todayBox.hidden = !track.active && !(track.domains && track.domains.length);
    if (startBtn) {
      startBtn.hidden = !!track.active;
      startBtn.textContent = track.started_on && !track.active ? "Yeniden başlat" : "Programı başlat";
    }
    if (pauseBtn) pauseBtn.hidden = !track.active;
    if (resumeBtn) resumeBtn.hidden = !(!track.active && track.started_on);

    var pick = document.getElementById("mm-wu-domain-pick");
    if (pick && !track.active) {
      var pool = (window._mmDomainsCache || []).filter(function (d) {
        var c = (d.warmup_cohort || "new");
        return c === _wuCohort;
      });
      if (!pool.length && track.suggested_domains) pool = track.suggested_domains;
      if (!Object.keys(_wuSelected).length) {
        (track.domains && track.domains.length ? track.domains : (track.suggested_domains || []))
          .forEach(function (d) { _wuSelected[String(d.id)] = true; });
      }
      if (!pool.length) {
        pick.innerHTML = '<span class="muted">Bu grupta domain yok — Domainler’den ekle / grubunu «' +
          (_wuCohort === "new" ? "Yeni" : "Eski") + '» yap.</span>';
      } else {
        pick.innerHTML = pool.map(function (d) {
          var id = String(d.id);
          var checked = _wuSelected[id] ? " checked" : "";
          return '<label class="mm-wu-pick">' +
            '<input type="checkbox" data-wu-id="' + esc(id) + '"' + checked + ">" +
            "<span>" + esc(d.domain) + "</span></label>";
        }).join("");
      }
    }

    // hero / tasks — reuse existing ids with track
    var dayEl = document.getElementById("mm-wu-day");
    var titleEl = document.getElementById("mm-wu-title");
    var targetsEl = document.getElementById("mm-wu-targets");
    var progLabel = document.getElementById("mm-wu-progress-label");
    var ringEl = document.getElementById("mm-wu-progress-ring");
    var cards = document.getElementById("mm-wu-domains");
    var tasksEl = document.getElementById("mm-wu-tasks");
    var rulesEl = document.getElementById("mm-wu-rules");
    if (track.active || (track.domains && track.domains.length)) {
      var day = track.day || 1;
      var totalDays = track.total_days || 30;
      if (dayEl) dayEl.textContent = "Gün " + day + "/" + totalDays;
      if (titleEl) titleEl.textContent = (track.plan && track.plan.title) || "—";
      if (targetsEl) {
        targetsEl.textContent =
          "önerilen ~" + ((track.plan && track.plan.per_domain_target) || "—") +
          "/domain · daily_cap hedef " + ((track.plan && track.plan.daily_cap_suggest) || "—") +
          " — gönderimi kesen sayı daily_cap’tir";
      }
      var tasks = (track.plan && track.plan.tasks) || [];
      var doneN = tasks.filter(function (t) { return t.done; }).length;
      if (progLabel) progLabel.textContent = doneN + "/" + tasks.length;
      // Dekoratif progress ring — önceden conic-gradient açısı hep 0deg sabitti
      // (hiçbir zaman güncellenmiyordu, görsel olarak hep "boş" görünüyordu).
      // Burada bugünün görev tamamlanma % üzerinden gerçek zamanlı çiziliyor.
      if (ringEl) {
        var pct = tasks.length ? Math.round((doneN / tasks.length) * 100) : 0;
        var deg = Math.round(pct * 3.6);
        ringEl.style.background =
          "radial-gradient(circle at 30% 30%, rgba(56,189,248,0.25), transparent 60%), " +
          "conic-gradient(#38bdf8 " + deg + "deg, rgba(148,163,184,0.2) " + deg + "deg)";
      }
      if (cards) {
        var domainMeta = {};
        (window._mmDomainsCache || []).forEach(function (d) { domainMeta[String(d.id)] = d; });
        cards.innerHTML = (track.domains || []).map(function (d) {
          var meta = domainMeta[String(d.id)] || {};
          var status = meta.warm_status || "warming";
          var dayPct = Math.min(100, Math.round((day / totalDays) * 100));
          var health = meta.health_score != null ? meta.health_score : null;
          var dotClass = status === "warm" ? "mm-dot-green" : (status === "paused" || status === "burned" ? "mm-dot-rose" : "mm-dot-amber");
          return '<div class="mm-wu-progress-card">' +
            '<div class="mm-wu-progress-card-head">' +
              '<span class="mm-dot ' + dotClass + '"></span>' +
              '<strong>' + esc(d.domain) + "</strong>" +
              '<span class="mm-badge mm-badge-info" style="margin-left:auto;">' + esc(status) + "</span>" +
            "</div>" +
            '<div class="mm-wu-progress-card-bar"><div style="width:' + dayPct + '%;"></div></div>' +
            '<div class="mm-wu-progress-card-meta">' +
              "<span>Gün " + day + "/" + totalDays + "</span>" +
              "<span>cap " + esc(d.daily_cap) + "</span>" +
              (health != null ? ("<span>health " + esc(health) + "</span>") : "") +
            "</div>" +
          "</div>";
        }).join("") || '<span class="muted">Domain yok</span>';
      }
      if (tasksEl) {
        tasksEl.innerHTML = tasks.map(function (t) {
          return '<label class="mm-wu-task' + (t.done ? " is-done" : "") + '">' +
            '<span class="mm-dot ' + (t.done ? "mm-dot-green" : "mm-dot-amber") + '"></span>' +
            '<input type="checkbox" data-wu-task="' + esc(t.key) + '"' + (t.done ? " checked" : "") + ">" +
            '<span class="mm-wu-task-body"><strong>' + esc(t.title) + "</strong>" +
            "<small>" + esc(t.hint || "") + "</small></span></label>";
        }).join("");
      }
      if (rulesEl) {
        rulesEl.innerHTML = ((track.plan && track.plan.rules) || []).map(function (r) {
          return "<li>" + esc(r) + "</li>";
        }).join("");
      }
    }
  }

  function refreshWarmupProgram() {
    return api("/api/platform/warmup-program").then(function (res) {
      if (!res.ok) {
        applyWarmupBanner(null);
        var statusEl = document.getElementById("mm-wu-status");
        if (statusEl) statusEl.textContent = (res.data && res.data.error) || "Program yüklenemedi";
        return;
      }
      renderWarmupProgram(res.data.program);
    });
  }

  function selectedWarmupDomainIds() {
    var pick = document.getElementById("mm-wu-domain-pick");
    var ids = [];
    if (pick) {
      pick.querySelectorAll('input[type="checkbox"][data-wu-id]:checked').forEach(function (el) {
        ids.push(Number(el.getAttribute("data-wu-id")));
      });
    }
    if (!ids.length) {
      Object.keys(_wuSelected).forEach(function (k) {
        if (_wuSelected[k]) ids.push(Number(k));
      });
    }
    // Önceden 20'ye sessizce kırpılıyordu (bkz. backend MAX_WARMUP_DOMAINS notu) —
    // 20'den fazla domain seçilince kalanı hiç ısıtma programına girmiyordu ve
    // kullanıcı bunu fark edemiyordu. Backend'deki gerçek üst sınırla eşleşsin.
    return ids.filter(function (n) { return n > 0; }).slice(0, 300);
  }

  function applyWeeklyBanner(maint) {
    var banner = document.getElementById("mm-weekly-banner");
    var text = document.getElementById("mm-weekly-banner-text");
    if (!banner) return;
    var show = maint && maint.banner && maint.banner.show;
    banner.hidden = !show;
    if (text) text.textContent = (maint && maint.banner && maint.banner.text) || "Pazar bakımı bekliyor";
  }

  function renderWeeklyMaintenance(maint) {
    window._mmWeeklyMaint = maint || null;
    applyWeeklyBanner(maint);
    var statusEl = document.getElementById("mm-weekly-status");
    var tasksEl = document.getElementById("mm-weekly-tasks");
    var metaEl = document.getElementById("mm-weekly-meta");
    var runBtn = document.getElementById("mm-weekly-run");
    if (!maint) {
      if (statusEl) statusEl.textContent = "Haftalık bakım yüklenemedi";
      return;
    }
    var pending = maint.pending || 0;
    var gap = maint.warmup_gap_days || 0;
    if (statusEl) {
      if (maint.is_sunday) {
        statusEl.textContent = maint.all_done
          ? "Bu Pazar bakımı tamam · gelecek Pazara kadar tamam."
          : ("Pazar bakımı aktif · " + pending + " görev bekliyor" +
            (gap >= 2 ? (" · ısıtma gap " + gap + " gün (soft resume önerilir)") : ""));
      } else {
        statusEl.textContent =
          "Program: her Pazar (TR) · bu hafta " + (maint.week_key || "—") +
          (maint.last_run_at ? (" · son auto-run " + fmtTime(maint.last_run_at)) : " · henüz auto-run yok");
      }
    }
    if (tasksEl) {
      tasksEl.innerHTML = (maint.tasks || []).map(function (t) {
        var autoTag = t.auto ? ' <span class="muted">(otomatik)</span>' : "";
        return '<label class="mm-wu-task' + (t.done ? " is-done" : "") + '">' +
          '<span class="mm-dot ' + (t.done ? "mm-dot-green" : "mm-dot-amber") + '"></span>' +
          '<input type="checkbox" data-weekly-task="' + esc(t.key) + '"' + (t.done ? " checked" : "") + ">" +
          '<span class="mm-wu-task-body"><strong>' + esc(t.title) + autoTag + "</strong>" +
          '<small>' + esc(t.hint) + "</small></span></label>";
      }).join("");
    }
    if (metaEl) {
      var run = maint.this_week_run;
      var act = run && run.actions ? run.actions.length : 0;
      metaEl.textContent = run
        ? ("Bu hafta auto-run: " + fmtTime(run.ran_at) + " · " + act + " adım")
        : "Bu hafta henüz otomatik bakım koşmadı — «Bakımı çalıştır» ile başlat.";
    }
    if (runBtn) {
      runBtn.textContent = maint.this_week_run ? "Tekrar çalıştır" : "Bakımı çalıştır";
    }
  }

  function refreshWeeklyMaintenance() {
    return api("/api/platform/weekly-maintenance").then(function (res) {
      if (!res.ok) {
        applyWeeklyBanner(null);
        var statusEl = document.getElementById("mm-weekly-status");
        if (statusEl) statusEl.textContent = (res.data && res.data.error) || "Yüklenemedi";
        return;
      }
      renderWeeklyMaintenance(res.data.maintenance);
    });
  }

  function bindWeeklyMaintenanceUi() {
    var refreshBtn = document.getElementById("mm-weekly-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", refreshWeeklyMaintenance);
    var runBtn = document.getElementById("mm-weekly-run");
    if (runBtn) {
      runBtn.addEventListener("click", function () {
        var force = !!(window._mmWeeklyMaint && window._mmWeeklyMaint.this_week_run);
        if (!confirm(force
          ? "Bu haftanın bakımını tekrar çalıştır? (cap sync + soft resume)"
          : "Pazar bakımı çalışsın mı? (cap sync + ısıtma catch-up)")) return;
        api("/api/platform/weekly-maintenance/run", {
          method: "POST",
          body: { force: force }
        }).then(function (res) {
          if (!res.ok) {
            alert((res.data && res.data.error) || "Çalıştırılamadı");
            return;
          }
          if (res.data.skipped) {
            alert(res.data.reason || "Zaten çalışmış");
          } else {
            var acts = res.data.actions || [];
            var sync = (acts[0] && acts[0].result) || {};
            var catchup = (acts[1] && acts[1].result) || {};
            alert(
              "Bakım tamam · cap=" + (sync.daily_cap || "—") +
              " · program günü=" + (sync.effective_day || catchup.effective_day || "—") +
              " · son gönderim=" + (catchup.last_send_date || sync.last_send_date || "—") +
              " · gap=" + (sync.gap_days != null ? sync.gap_days : "—") + "g" +
              (sync.resumed ? " · program devam ettirildi" : "")
            );
          }
          renderWeeklyMaintenance(res.data.snapshot);
          refreshWarmupProgram();
          refreshDomains();
        });
      });
    }
    var bannerGo = document.getElementById("mm-weekly-banner-go");
    if (bannerGo) {
      bannerGo.addEventListener("click", function () {
        if (window.mmNavigate) window.mmNavigate("plat-warmup");
      });
    }
    var tasksEl = document.getElementById("mm-weekly-tasks");
    if (tasksEl) {
      tasksEl.addEventListener("change", function (e) {
        var el = e.target;
        if (!el || !el.getAttribute) return;
        var key = el.getAttribute("data-weekly-task");
        if (!key) return;
        api("/api/platform/weekly-maintenance", {
          method: "PATCH",
          body: { task_key: key, done: !!el.checked }
        }).then(function (res) {
          if (!res.ok) {
            el.checked = !el.checked;
            alert((res.data && res.data.error) || "Kaydedilemedi");
            return;
          }
          renderWeeklyMaintenance(res.data.maintenance);
        });
      });
    }
  }

  function bindWarmupProgramUi() {
    var refreshBtn = document.getElementById("mm-wu-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", refreshWarmupProgram);
    var tabL = document.getElementById("mm-wu-tab-legacy");
    var tabN = document.getElementById("mm-wu-tab-new");
    if (tabL) tabL.addEventListener("click", function () { setWuCohortTab("legacy"); });
    if (tabN) tabN.addEventListener("click", function () { setWuCohortTab("new"); });
    var infoOverlay = document.getElementById("mm-wu-info-overlay");
    var infoBtn = document.getElementById("mm-wu-info-btn");
    var infoClose = document.getElementById("mm-wu-info-close");
    if (infoBtn && infoOverlay) infoBtn.addEventListener("click", function () { infoOverlay.hidden = false; });
    if (infoClose && infoOverlay) infoClose.addEventListener("click", function () { infoOverlay.hidden = true; });
    if (infoOverlay) infoOverlay.addEventListener("click", function (e) { if (e.target === infoOverlay) infoOverlay.hidden = true; });
    var startBtn = document.getElementById("mm-wu-start");
    if (startBtn) {
      startBtn.addEventListener("click", function () {
        var ids = selectedWarmupDomainIds();
        if (!ids.length) {
          alert("En az 1 domain seç.");
          return;
        }
        if (!confirm(ids.length + " domain ile «" + (_wuCohort === "new" ? "Yeni" : "Eski") + "» 30 günlük ısıtma programını başlat?")) return;
        api("/api/platform/warmup-program/start", {
          method: "POST",
          body: { domain_ids: ids, cohort: _wuCohort }
        }).then(function (res) {
          if (!res.ok) {
            alert((res.data && res.data.error) || "Başlatılamadı");
            return;
          }
          _wuSelected = {};
          renderWarmupProgram(res.data.program);
          refreshDomains();
        });
      });
    }
    var pauseBtn = document.getElementById("mm-wu-pause");
    if (pauseBtn) {
      pauseBtn.addEventListener("click", function () {
        api("/api/platform/warmup-program", { method: "PATCH", body: { pause: true, cohort: _wuCohort } })
          .then(function (res) {
            if (res.ok) renderWarmupProgram(res.data.program);
            else alert((res.data && res.data.error) || "Duraklatılamadı");
          });
      });
    }
    var resumeBtn = document.getElementById("mm-wu-resume");
    if (resumeBtn) {
      resumeBtn.addEventListener("click", function () {
        api("/api/platform/warmup-program", { method: "PATCH", body: { resume: true, cohort: _wuCohort } })
          .then(function (res) {
            if (res.ok) renderWarmupProgram(res.data.program);
            else alert((res.data && res.data.error) || "Devam edilemedi");
          });
      });
    }
    var realignBtn = document.getElementById("mm-wu-realign");
    if (realignBtn) {
      realignBtn.addEventListener("click", function () {
        if (!confirm(
          "Programı son gerçek gönderim gününe hizala?\n\n" +
          "Takvim «her gün attın» diye ileri sarmışsa geri çeker; " +
          "daily_cap / warm_day o güne göre ayarlanır."
        )) return;
        api("/api/platform/warmup-program/realign-last-send", {
          method: "POST",
          body: { advance: false, cohort: _wuCohort }
        }).then(function (res) {
          if (!res.ok) {
            alert((res.data && res.data.error) || "Hizalanamadı");
            return;
          }
          var r = res.data.realign || {};
          alert(
            "Hizalandı · program günü " + (r.resume_day || "?") +
            " · son gönderim " + (r.last_send_date || "—") +
            " · gap " + (r.gap_days != null ? r.gap_days : "—") + "g" +
            " · daily_cap " + (r.daily_cap || "—") +
            " · önce takvim günü " + (r.calendar_day_before || "—") + " idi"
          );
          if (res.data.program) renderWarmupProgram(res.data.program);
          else refreshWarmupProgram();
          refreshDomains();
        });
      });
    }
    var bannerGo = document.getElementById("mm-warmup-banner-go");
    if (bannerGo) {
      bannerGo.addEventListener("click", function () {
        if (window.mmNavigate) window.mmNavigate("plat-warmup");
      });
    }
    var pick = document.getElementById("mm-wu-domain-pick");
    if (pick) {
      pick.addEventListener("change", function (e) {
        var el = e.target;
        if (!el || !el.getAttribute || !el.getAttribute("data-wu-id")) return;
        _wuSelected[el.getAttribute("data-wu-id")] = !!el.checked;
      });
    }
    var tasksEl = document.getElementById("mm-wu-tasks");
    if (tasksEl) {
      tasksEl.addEventListener("change", function (e) {
        var el = e.target;
        if (!el || !el.getAttribute) return;
        var key = el.getAttribute("data-wu-task");
        if (!key) return;
        api("/api/platform/warmup-program", {
          method: "PATCH",
          body: { task_key: key, done: !!el.checked, cohort: _wuCohort }
        }).then(function (res) {
          if (!res.ok) {
            el.checked = !el.checked;
            alert((res.data && res.data.error) || "Kaydedilemedi");
            return;
          }
          renderWarmupProgram(res.data.program);
          if (res.data.program && res.data.program.all_done_today) refreshDomains();
        });
      });
    }
  }

  function resetDomainForm() {
    var form = document.getElementById("mm-domain-form");
    if (form) form.reset();
    setDomainFormMode(null);
  }

  var _bulkDomainsSaving = false;

  function toggleBulkDomainsPanel() {
    var panel = document.getElementById("mm-domains-bulk-panel");
    if (!panel) return;
    panel.hidden = !panel.hidden;
  }

  function submitBulkDomains() {
    if (_bulkDomainsSaving) return;
    var ta = document.getElementById("mm-domains-bulk-text");
    var resultsBox = document.getElementById("mm-domains-bulk-results");
    var text = ta ? ta.value : "";
    if (!text || !text.trim()) {
      if (resultsBox) resultsBox.innerHTML = '<p class="hint" style="color:var(--danger,#dc2626);">Liste boş — en az bir satır yaz.</p>';
      return;
    }
    var btn = document.getElementById("mm-domains-bulk-submit");
    var defaults = {
      warmup_cohort: (document.getElementById("mm-bulk-cohort") || {}).value || "new",
      daily_cap: Number((document.getElementById("mm-bulk-cap") || {}).value) || 50,
      warm_status: (document.getElementById("mm-bulk-warm") || {}).value || "cold"
    };
    _bulkDomainsSaving = true;
    if (btn) { btn.disabled = true; btn.textContent = "Ekleniyor…"; }
    if (resultsBox) resultsBox.innerHTML = '<p class="hint">Ekleniyor…</p>';
    apiRetry("/api/platform/domains/bulk", { method: "POST", body: { text: text, defaults: defaults } })
      .then(function (res) {
        _bulkDomainsSaving = false;
        if (btn) { btn.disabled = false; btn.textContent = "Hepsini ekle"; }
        if (!res.ok) {
          if (resultsBox) resultsBox.innerHTML = '<p class="hint" style="color:var(--danger,#dc2626);">' +
            esc((res.data && res.data.error) || "Eklenemedi") + "</p>";
          return;
        }
        var rows = res.data.results || [];
        var okCount = res.data.created || 0;
        var failCount = rows.length - okCount;
        var html = '<p class="hint"><strong>' + okCount + ' / ' + rows.length + '</strong> domain eklendi' +
          (failCount ? (' · <span style="color:var(--danger,#dc2626);">' + failCount + " başarısız</span>") : "") +
          "</p>";
        html += '<div class="table-wrap"><div class="table-scroll"><table><thead><tr><th>#</th><th>Domain</th><th>Sonuç</th></tr></thead><tbody>';
        rows.forEach(function (r) {
          html += "<tr>" +
            "<td>" + esc(r.line) + "</td>" +
            "<td>" + esc(r.domain || "—") + "</td>" +
            "<td>" + (r.ok
              ? '<span class="mm-badge mm-badge-ok">Eklendi</span>'
              : ('<span class="mm-badge mm-badge-danger">Hata: ' + esc(r.error || "?") + "</span>")) +
            "</td></tr>";
        });
        html += "</tbody></table></div></div>";
        if (resultsBox) resultsBox.innerHTML = html;
        if (okCount > 0) {
          if (ta) ta.value = "";
          refreshDomains();
        }
      });
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
      daily_cap: Number(document.getElementById("mm-d-cap").value) || 500,
      warmup_cohort: (document.getElementById("mm-d-cohort") || {}).value || "new"
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

    apiRetry(path, { method: method, body: body })
      .then(function (res) {
        if (!res.ok) {
          var err = (res.data && res.data.error) || ("Kaydedilemedi (HTTP " + res.status + ")");
          if (res.status === 401 || res.status === 403) {
            err = "Oturum düşmüş — sayfayı yenile, tekrar giriş yap, sonra kaydet";
            setDomainHint(err, true);
            return;
          }
          // Create: cevap gelmeden kopunca sunucu yine de kaydetmiş olabilir;
          // ikinci denemede "Domain zaten var" da aynı şey. Listeyi doğrula.
          if (!_editDomainId && body.domain) {
            var maybeDup = /zaten var/i.test(String(err));
            var maybeNet = res.status === 0;
            if (maybeDup || maybeNet) {
              setDomainHint("Bağlantı koptu — kayıt kontrol ediliyor…", false);
              return refreshDomains().then(function () {
                var existing = findDomainByName(body.domain);
                if (existing) {
                  resetDomainForm();
                  setDomainHint(
                    "Kaydedildi: " + (existing.from_local || "info") + "@" + existing.domain,
                    false
                  );
                  if (window.MakroMailing && typeof window.MakroMailing.onShow === "function") {
                    window.MakroMailing.onShow();
                  }
                  return;
                }
                setDomainHint(err, true);
              });
            }
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
            var hint = document.getElementById("mm-tenant-hint");
            if (hint) {
              var t = (window._mmTenantsCache || []).find(function (x) { return Number(x.id) === tid; });
              hint.textContent = tid
                ? ("Tenant #" + tid + (t ? " (" + t.slug + ")" : "") + " seçildi")
                : "Tümü (genel) — tüm firmaların rakamları";
            }
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

      document.getElementById("mm-cutoff-campaign-pick")?.addEventListener("change", function () {
        var v = this.value;
        var dt = document.getElementById("mm-cutoff-datetime");
        if (v && dt) dt.value = isoToLocalInput(v);
      });
      document.getElementById("mm-cutoff-now")?.addEventListener("click", function () {
        var dt = document.getElementById("mm-cutoff-datetime");
        if (dt) dt.value = isoToLocalInput(new Date().toISOString());
      });
      document.getElementById("mm-cutoff-save")?.addEventListener("click", function () {
        if (!_activityTenantId) return;
        var dt = document.getElementById("mm-cutoff-datetime");
        var iso = dt && dt.value ? localInputToIso(dt.value) : null;
        if (dt && dt.value && !iso) { alert("Geçersiz tarih/saat."); return; }
        apiRetry("/api/platform/tenants/" + _activityTenantId, {
          method: "PATCH",
          body: { data_visible_from: iso }
        }).then(function (res) {
          if (!res.ok) { alert((res.data && res.data.error) || "Kaydedilemedi"); return; }
          renderCutoffBox(res.data.tenant || {});
        });
      });
      document.getElementById("mm-cutoff-clear")?.addEventListener("click", function () {
        if (!_activityTenantId) return;
        if (!confirm("Bu firma için geçmiş veri kısıtlamasını tamamen kaldırmak istediğine emin misin? (Tüm geçmiş yeniden görünür olur)")) return;
        apiRetry("/api/platform/tenants/" + _activityTenantId, {
          method: "PATCH",
          body: { data_visible_from: null }
        }).then(function (res) {
          if (!res.ok) { alert((res.data && res.data.error) || "Kaldırılamadı"); return; }
          renderCutoffBox(res.data.tenant || {});
        });
      });

      document.getElementById("mm-user-add-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        if (!_activityTenantId) return;
        var hint = document.getElementById("mm-user-add-hint");
        var username = document.getElementById("mm-nu-username").value.trim();
        var password = document.getElementById("mm-nu-password").value;
        var display = document.getElementById("mm-nu-display").value.trim();
        apiRetry("/api/platform/tenants/" + _activityTenantId + "/users", {
          method: "POST",
          body: { username: username, password: password, display_name: display }
        }).then(function (res) {
          if (!res.ok) {
            if (hint) hint.textContent = (res.data && res.data.error) || "Oluşturulamadı";
            return;
          }
          if (hint) hint.textContent = "Kullanıcı eklendi: " + username;
          document.getElementById("mm-user-add-form").reset();
          refreshTenantUsersTable(_activityTenantId);
          refreshTenants();
        });
      });

      document.getElementById("mm-ue-cancel")?.addEventListener("click", function () {
        closeModal("mm-user-edit-modal");
      });
      document.getElementById("mm-user-edit-modal")?.addEventListener("click", function (e) {
        if (e.target.id === "mm-user-edit-modal") closeModal("mm-user-edit-modal");
      });
      document.getElementById("mm-ue-save")?.addEventListener("click", function () {
        var tid = document.getElementById("mm-ue-tenant-id").value;
        var uid = document.getElementById("mm-ue-user-id").value;
        if (!tid || !uid) return;
        var perms = Array.prototype.map.call(
          document.querySelectorAll(".mm-ue-perm-chk:checked"),
          function (el) { return el.value; }
        );
        perms.unshift("module.mailing");
        apiRetry("/api/platform/tenants/" + tid + "/users/" + uid, {
          method: "PATCH",
          body: {
            username: document.getElementById("mm-ue-username").value.trim(),
            display_name: document.getElementById("mm-ue-display").value.trim(),
            active: !!document.getElementById("mm-ue-active").checked,
            permissions: perms
          }
        }).then(function (res) {
          if (!res.ok) { alert((res.data && res.data.error) || "Kaydedilemedi"); return; }
          closeModal("mm-user-edit-modal");
          refreshTenantUsersTable(tid);
        });
      });
      document.getElementById("mm-aq-refresh")?.addEventListener("click", refreshAccountQuota);
      document.getElementById("mm-cr-refresh")?.addEventListener("click", refreshMailCredit);
      document.getElementById("mm-cr-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        var hint = document.getElementById("mm-cr-hint");
        var body = {
          total: Number(document.getElementById("mm-cr-total").value) || 0,
          used: Number(document.getElementById("mm-cr-used").value) || 0
        };
        var top = Number(document.getElementById("mm-cr-topup").value) || 0;
        if (top > 0) body.top_up = top;
        api("/api/platform/mail-credit", { method: "PATCH", body: body }).then(function (res) {
          if (!res.ok) {
            if (hint) hint.textContent = (res.data && res.data.error) || "Kaydedilemedi";
            return;
          }
          renderMailCredit(res.data.credit, res.data.tenants);
          var topEl = document.getElementById("mm-cr-topup");
          if (topEl) topEl.value = "0";
          if (hint) hint.textContent = "Kredi paketi kaydedildi · kalan " +
            fmtCr((res.data.credit && res.data.credit.remaining) || 0);
        });
      });
      document.getElementById("mm-aq-form")?.addEventListener("submit", function (e) {
        e.preventDefault();
        var hint = document.getElementById("mm-aq-hint");
        api("/api/platform/account-quota", {
          method: "PATCH",
          body: {
            limit: Number(document.getElementById("mm-aq-limit").value) || 20000,
            tz: (document.getElementById("mm-aq-tz").value || "UTC").trim()
          }
        }).then(function (res) {
          if (!res.ok) {
            if (hint) hint.textContent = (res.data && res.data.error) || "Kaydedilemedi";
            return;
          }
          if (res.data.quota) renderAccountQuota(res.data.quota);
          if (hint) hint.textContent = "Alibaba hesap kotası kaydedildi (" +
            ((res.data.quota && res.data.quota.limit) || "?") + "/gün)";
        });
      });
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
              max_sends_day: Number(document.getElementById("mm-t-cap").value) || 50000,
              credit_allocated: Number((document.getElementById("mm-t-credit") || {}).value) || 0
            }
          }).then(function (res) {
            if (!res.ok) {
              if (hint) hint.textContent = (res.data && res.data.error) || "Kaydedilemedi";
              return;
            }
            if (hint) hint.textContent = "Firma güncellendi";
            setTenantFormMode(null);
            refreshTenants();
            refreshMailCredit();
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
            max_sends_day: Number(document.getElementById("mm-t-cap").value) || 50000,
            credit_allocated: Number((document.getElementById("mm-t-credit") || {}).value) || 0
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
          refreshMailCredit();
        });
      });
      document.getElementById("mm-domain-form")?.addEventListener("submit", saveDomainForm);
      document.getElementById("mm-domains-bulk-toggle")?.addEventListener("click", toggleBulkDomainsPanel);
      document.getElementById("mm-domains-bulk-submit")?.addEventListener("click", submitBulkDomains);

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
        var userEdit = e.target.closest(".mm-user-edit");
        if (userEdit) {
          var ueTid = userEdit.getAttribute("data-tid");
          var ueUid = userEdit.getAttribute("data-uid");
          api("/api/platform/tenants/" + ueTid + "/users").then(function (res) {
            if (!res.ok) { alert((res.data && res.data.error) || "Yüklenemedi"); return; }
            var u = (res.data.users || []).find(function (x) { return String(x.id) === String(ueUid); });
            if (!u) { alert("Kullanıcı bulunamadı."); return; }
            document.getElementById("mm-ue-tenant-id").value = ueTid;
            document.getElementById("mm-ue-user-id").value = ueUid;
            document.getElementById("mm-ue-username").value = u.username || "";
            document.getElementById("mm-ue-display").value = u.display_name || "";
            document.getElementById("mm-ue-active").checked = !!u.active;
            var perms = u.permissions || [];
            var grid = document.getElementById("mm-ue-perms");
            if (grid) {
              grid.style.display = "grid";
              grid.style.gridTemplateColumns = "repeat(auto-fit, minmax(150px, 1fr))";
              grid.style.gap = "0.5rem 0.75rem";
              grid.innerHTML = MAILING_PERM_KEYS.map(function (p) {
                var checked = perms.indexOf(p.key) !== -1 ? " checked" : "";
                return '<label style="display:flex !important;align-items:center;gap:0.4rem;margin:0;' +
                  'text-transform:none;letter-spacing:normal;font-size:0.8rem;font-weight:500;' +
                  'color:var(--text);cursor:pointer;width:auto;">' +
                  '<input type="checkbox" class="mm-ue-perm-chk" value="' + esc(p.key) + '"' + checked +
                  ' style="width:16px !important;min-width:16px !important;max-width:16px !important;' +
                  'height:16px !important;padding:0 !important;margin:0 !important;flex:0 0 auto !important;' +
                  'accent-color:var(--accent);">' +
                  '<span>' + esc(p.label) + "</span></label>";
              }).join("");
            }
            openModal("mm-user-edit-modal");
          });
          return;
        }
        var userResetPass = e.target.closest(".mm-user-reset-pass");
        if (userResetPass) {
          var rpTid = userResetPass.getAttribute("data-tid");
          var rpUid = userResetPass.getAttribute("data-uid");
          var rpUsername = userResetPass.getAttribute("data-username") || "";
          var newPass = prompt("«" + rpUsername + "» için yeni şifre (en az 8 karakter):", "");
          if (newPass == null) return;
          if (newPass.length < 8) { alert("Şifre en az 8 karakter olmalı."); return; }
          apiRetry("/api/platform/tenants/" + rpTid + "/users/" + rpUid + "/reset-password", {
            method: "POST",
            body: { password: newPass }
          }).then(function (res) {
            if (!res.ok) { alert((res.data && res.data.error) || "Sıfırlanamadı"); return; }
            alert("Şifre güncellendi: " + rpUsername + " — bir dahaki girişte yeni şifre belirlemek zorunda kalacak.");
            refreshTenantUsersTable(rpTid);
          });
          return;
        }
        var userResetTotp = e.target.closest(".mm-user-reset-totp");
        if (userResetTotp) {
          var rtTid = userResetTotp.getAttribute("data-tid");
          var rtUid = userResetTotp.getAttribute("data-uid");
          var rtUsername = userResetTotp.getAttribute("data-username") || "";
          if (!confirm("«" + rtUsername + "» için 2FA (Authenticator) sıfırlansın mı? Kullanıcı bir dahaki girişte QR kodu tekrar okutup yeniden kurmak zorunda kalacak.")) return;
          apiRetry("/api/platform/tenants/" + rtTid + "/users/" + rtUid + "/reset-totp", {
            method: "POST"
          }).then(function (res) {
            if (!res.ok) { alert((res.data && res.data.error) || "Sıfırlanamadı"); return; }
            alert("2FA sıfırlandı: " + rtUsername);
            refreshTenantUsersTable(rtTid);
          });
          return;
        }
        var userDel = e.target.closest(".mm-user-del");
        if (userDel) {
          var udTid = userDel.getAttribute("data-tid");
          var udUid = userDel.getAttribute("data-uid");
          var udUsername = userDel.getAttribute("data-username") || "";
          var udActive = userDel.getAttribute("data-active") === "1";
          if (udActive) {
            if (!confirm("«" + udUsername + "» kullanıcısını devre dışı bırakmak istediğine emin misin? (Giriş yapamaz olur)")) return;
            apiRetry("/api/platform/tenants/" + udTid + "/users/" + udUid, { method: "DELETE" }).then(function (res) {
              if (!res.ok) { alert((res.data && res.data.error) || "Silinemedi"); return; }
              refreshTenantUsersTable(udTid);
            });
          } else {
            apiRetry("/api/platform/tenants/" + udTid + "/users/" + udUid, {
              method: "PATCH",
              body: { active: true }
            }).then(function (res) {
              if (!res.ok) { alert((res.data && res.data.error) || "Güncellenemedi"); return; }
              refreshTenantUsersTable(udTid);
            });
          }
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
        var unpause = e.target.closest(".mm-unpause-domain");
        if (unpause) {
          var upId = Number(unpause.getAttribute("data-id"));
          if (!confirm(
            "Bu domainin pause'unu geri al? Health 100'e sıfırlanır.\n\n" +
            "Not: gerçek bounce/fail/complaint sorunu çözülmediyse domain " +
            "yeniden otomatik pause olabilir."
          )) return;
          api("/api/platform/domains/" + upId + "/unpause", { method: "POST" }).then(function (res) {
            if (!res.ok) {
              alert((res.data && res.data.error) || "Geri alınamadı");
              return;
            }
            refreshDomains();
          });
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
          return;
        }
        var crAllocBtn = e.target.closest(".mm-cr-alloc-btn");
        if (crAllocBtn) {
          var tidCr = Number(crAllocBtn.getAttribute("data-id"));
          var cur = crAllocBtn.getAttribute("data-alloc") || "0";
          var val = prompt("Bu firmaya tahsis edilecek kredi:", cur);
          if (val === null) return;
          api("/api/platform/mail-credit", {
            method: "PATCH",
            body: { tenant_id: tidCr, credit_allocated: Number(val) || 0 }
          }).then(function (res) {
            if (!res.ok) {
              alert((res.data && res.data.error) || "Tahsis başarısız");
              return;
            }
            renderMailCredit(res.data.credit, res.data.tenants);
            refreshTenants();
          });
        }
      });
      bindWarmupProgramUi();
      bindWeeklyMaintenanceUi();
      this.refresh();
      // Isıtma programı / kota / kredi sayaçları eskiden SADECE bu sayfaya
      // (yeniden) girildiğinde veya bir aksiyon butonuna tıklandığında
      // tazeleniyordu — kullanıcı sayfada kalıp saatlerce süren bir kampanyayı
      // izlerken rakamlar donmuş görünüyordu (aslında arka planda güncelleniyor,
      // sadece ekran yenilenmiyordu). Isıtma sekmesi görünürken periyodik tazele.
      setInterval(function () {
        if (document.hidden) return;
        var pane = document.getElementById("mm-plat-warmup");
        if (!pane || !pane.classList.contains("active")) return;
        refreshWarmupProgram();
        refreshAccountQuota();
        refreshMailCredit();
      }, 20000);
    },
    refresh: function () {
      return Promise.all([
        refreshTenants(),
        refreshAccountQuota(),
        refreshMailCredit(),
        refreshDomains(),
        refreshWarmupProgram(),
        refreshWeeklyMaintenance()
      ]);
    }
  };

  window.MakroMailPlatform = Platform;
})();
