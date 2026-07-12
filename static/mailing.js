(function () {
  "use strict";

  var mailActiveTab = "dashboard";
  var mailPerms = [];
  var mailTemplates = [];
  var mailDomains = [];
  var mailTags = [];
  var mailLoaded = false;
  var mailTplMode = "simple";

  function mailHas(key) {
    if (!mailPerms || !mailPerms.length) return true;
    if (mailPerms.indexOf("*") >= 0) return true;
    if (mailPerms.indexOf("module.mailing") >= 0) return true;
    return mailPerms.indexOf(key) >= 0;
  }

  function mailApi(path, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 15000;
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs) : null;
    var fetchOpts = Object.assign({ headers: {} }, opts);
    delete fetchOpts.timeoutMs;
    if (fetchOpts.body && typeof fetchOpts.body === "object" && !(fetchOpts.body instanceof FormData)) {
      fetchOpts.headers["Content-Type"] = "application/json";
      fetchOpts.body = JSON.stringify(fetchOpts.body);
    }
    if (controller) fetchOpts.signal = controller.signal;
    return fetch(path, fetchOpts).then(function (r) {
      if (timer) clearTimeout(timer);
      if (r.status === 401) { location.href = "/admin/login"; return null; }
      return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
    }).catch(function () {
      if (timer) clearTimeout(timer);
      return null;
    });
  }

  function mailToast(msg) {
    var el = document.getElementById("toast");
    if (!el) { alert(msg); return; }
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(function () { el.classList.remove("show"); }, 2800);
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
    } catch (e) {
      return iso;
    }
  }

  function switchMailTab(name) {
    mailActiveTab = name || "dashboard";
    document.querySelectorAll("#mail-tabs .acc-tab").forEach(function (btn) {
      btn.classList.toggle("active", btn.getAttribute("data-mail-tab") === mailActiveTab);
    });
    document.querySelectorAll("#module-mailing-panel [data-mail-pane]").forEach(function (pane) {
      var on = pane.getAttribute("data-mail-pane") === mailActiveTab;
      pane.classList.toggle("active", on);
      pane.hidden = !on;
    });
    mailLoadTab(mailActiveTab);
  }

  function mailLoadTab(tab) {
    if (tab === "dashboard") mailLoadDashboard();
    else if (tab === "crm") { mailLoadTags(); mailLoadContacts(); }
    else if (tab === "templates") mailLoadTemplates();
    else if (tab === "campaigns") { mailLoadSelects().then(mailLoadCampaigns); }
    else if (tab === "ivr") { mailLoadSelects().then(mailLoadIvr); }
    else if (tab === "reports") mailLoadReports();
    else if (tab === "settings") mailLoadSettings();
  }

  function mailLoadDashboard() {
    return mailApi("/api/mailing/dashboard").then(function (res) {
      if (!res || !res.ok) return;
      var k = res.data.kpi || {};
      setText("mail-kpi-contacts", k.contacts);
      setText("mail-kpi-contacts-sub", (k.active_contacts || 0) + " aktif");
      setText("mail-kpi-campaigns", k.campaigns);
      setText("mail-kpi-sent", k.sends_delivered);
      setText("mail-kpi-sent-sub", "kuyruk " + (k.sends_queued || 0) + " · fail " + (k.sends_failed || 0));
      setText("mail-kpi-ivr", k.ivr_events);
      setText("mail-dash-note", res.data.note || "");
      mailDomains = res.data.domains || [];
      renderDomainChips(mailDomains);
      updateProviderPill(res.data.provider_mode);
    });
  }

  function updateProviderPill(mode) {
    var pill = document.getElementById("mail-provider-pill");
    if (!pill) return;
    if (mode === "smtp") {
      pill.textContent = "SMTP / DirectMail";
      pill.style.background = "var(--green-soft)";
      pill.style.borderColor = "rgba(34,197,94,0.35)";
      pill.style.color = "var(--green)";
    } else {
      pill.textContent = "Stub mod";
      pill.style.background = "var(--amber)";
      pill.style.borderColor = "rgba(245,158,11,0.35)";
      pill.style.color = "#92400e";
    }
  }

  function renderDomainChips(domains) {
    var el = document.getElementById("mail-domain-chips");
    if (!el) return;
    if (!domains.length) { el.innerHTML = '<span class="muted">Domain yok</span>'; return; }
    el.innerHTML = domains.map(function (d) {
      return '<span class="acc-chip"><span class="acc-chip-text">' + esc(d.domain) +
        '</span> <span class="muted">' + esc(d.dns_status || d.status) + "</span></span>";
    }).join("");
  }

  function setText(id, val) {
    var el = document.getElementById(id);
    if (el) el.textContent = val == null || val === "" ? "—" : String(val);
  }

  // ── CRM ───────────────────────────────────────────────────
  function mailLoadTags() {
    return mailApi("/api/mailing/tags").then(function (res) {
      if (!res || !res.ok) return;
      mailTags = res.data.tags || [];
      var sel = document.getElementById("mail-contact-tag-filter");
      if (!sel) return;
      var cur = sel.value;
      sel.innerHTML = '<option value="">Tüm etiketler</option>' +
        mailTags.map(function (t) {
          return '<option value="' + esc(t.name) + '">' + esc(t.name) + "</option>";
        }).join("");
      sel.value = cur;
    });
  }

  function mailLoadContacts() {
    var q = (document.getElementById("mail-contact-q") || {}).value || "";
    var tag = (document.getElementById("mail-contact-tag-filter") || {}).value || "";
    var url = "/api/mailing/contacts?limit=500";
    if (q) url += "&q=" + encodeURIComponent(q);
    if (tag) url += "&tag=" + encodeURIComponent(tag);
    return mailApi(url).then(function (res) {
      var tbody = document.getElementById("mail-contacts-table");
      if (!tbody) return;
      if (!res || !res.ok) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.contacts || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Kontak yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (c) {
        var tags = (c.tags || []).map(function (t) {
          return '<span class="acc-chip"><span class="acc-chip-text">' + esc(t) + "</span></span>";
        }).join(" ");
        return "<tr>" +
          "<td>" + esc(c.email) + (c.unsubscribed ? ' <span class="muted">(unsub)</span>' : "") + "</td>" +
          "<td>" + esc(c.name) + "</td>" +
          "<td>" + (tags || "—") + "</td>" +
          "<td>" + esc(c.source) + "</td>" +
          '<td><button type="button" class="btn btn-sm mail-del-contact" data-id="' + c.id + '">Sil</button></td>' +
          "</tr>";
      }).join("");
    });
  }

  function mailPollImportJob(jobId) {
    var progBox = document.getElementById("mail-bulk-progress");
    var progBar = document.getElementById("mail-bulk-progress-bar");
    var progText = document.getElementById("mail-bulk-progress-text");
    function poll() {
      mailApi("/api/mailing/contacts/import/status/" + jobId).then(function (res) {
        if (!res || !res.ok || !res.data.job) {
          if (progText) progText.textContent = "Durum alınamadı, tekrar deneniyor…";
          setTimeout(poll, 3000);
          return;
        }
        var j = res.data.job;
        var pct = j.total_rows > 0 ? Math.min(100, Math.round((j.processed_rows / j.total_rows) * 100)) : 0;
        if (progBar) progBar.style.width = pct + "%";
        if (progText) {
          progText.textContent = (j.status === "pending" ? "Başlıyor… " : "") +
            j.processed_rows + " / " + j.total_rows + " satır (" + pct + "%) · " +
            "işlenen: " + j.upserted_count + " · geçersiz: " + j.skipped_count;
        }
        if (j.status === "done") {
          mailToast("İçe aktarma tamam · " + j.upserted_count + " kontak işlendi · " + j.skipped_count + " geçersiz e-posta atlandı");
          mailLoadContacts();
          mailLoadTags();
          setTimeout(function () { if (progBox) progBox.hidden = true; }, 4000);
          return;
        }
        if (j.status === "error") {
          mailToast("İçe aktarma hata verdi: " + (j.error || "bilinmeyen hata"));
          return;
        }
        setTimeout(poll, 2000);
      });
    }
    poll();
  }

  function mailLoadTemplates() {
    return mailApi("/api/mailing/templates").then(function (res) {
      mailTemplates = (res && res.ok && res.data.templates) || [];
      var tbody = document.getElementById("mail-tpl-table");
      if (!tbody) return;
      if (!mailTemplates.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">Şablon yok</td></tr>';
        return;
      }
      tbody.innerHTML = mailTemplates.map(function (t) {
        return "<tr>" +
          "<td>" + esc(t.name) + "</td>" +
          "<td>" + esc(t.subject) + "</td>" +
          "<td>" + esc(fmtTime(t.updated_at)) + "</td>" +
          '<td style="white-space:nowrap;">' +
          '<button type="button" class="btn btn-sm mail-edit-tpl" data-id="' + t.id + '">Düzenle</button> ' +
          '<button type="button" class="btn btn-sm mail-del-tpl" data-id="' + t.id + '">Sil</button>' +
          "</td></tr>";
      }).join("");
    });
  }

  function setTplMode(mode) {
    mailTplMode = mode === "html" ? "html" : "simple";
    var simplePane = document.getElementById("mail-tpl-pane-simple");
    var htmlPane = document.getElementById("mail-tpl-pane-html");
    var btnS = document.getElementById("mail-tpl-mode-simple");
    var btnH = document.getElementById("mail-tpl-mode-html");
    if (simplePane) simplePane.hidden = mailTplMode !== "simple";
    if (htmlPane) htmlPane.hidden = mailTplMode !== "html";
    if (btnS) btnS.classList.toggle("active", mailTplMode === "simple");
    if (btnH) btnH.classList.toggle("active", mailTplMode === "html");
    if (mailTplMode === "html") refreshTplPreview();
  }

  function previewHtmlFromEditors() {
    var html = (document.getElementById("mail-tpl-html") || {}).value || "";
    var text = (document.getElementById("mail-tpl-text") || {}).value || "";
    if (!html.trim() && text.trim()) {
      html = text
        .replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim()
        .split(/\n\n+/).map(function (block) {
          return "<p>" + block.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>\n") + "</p>";
        }).join("\n");
      // restore link tokens that got escaped
      html = html.replace(/\{\{link:([^}]+)\}\}/g, function (_m, url) {
        return "{{link:" + url.replace(/&amp;/g, "&") + "}}";
      });
    }
    return (html || "<p class='muted'>Önizleme boş</p>")
      .replace(/\{\{name\}\}/g, "Ali")
      .replace(/\{\{email\}\}/g, "ali@ornek.com")
      .replace(/\{\{phone\}\}/g, "+90555…")
      .replace(/\{\{\s*link\s*:\s*([^}]+)\s*\}\}/gi, function (_m, url) {
        var u = url.trim().replace(/^sc\s*:\s*/i, "");
        return '<a href="' + u + '" style="color:#2563eb;">' + u + "</a>";
      });
  }

  function refreshTplPreview() {
    var frame = document.getElementById("mail-tpl-preview");
    if (!frame) return;
    var doc = "<!DOCTYPE html><html><head><meta charset='utf-8'>" +
      "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;padding:16px;color:#111;line-height:1.5;font-size:15px}a{color:#2563eb}</style>" +
      "</head><body>" + previewHtmlFromEditors() + "</body></html>";
    frame.srcdoc = doc;
  }

  function insertAtCursor(textarea, snippet) {
    if (!textarea) return;
    var start = textarea.selectionStart || 0;
    var end = textarea.selectionEnd || 0;
    var val = textarea.value || "";
    textarea.value = val.slice(0, start) + snippet + val.slice(end);
    var pos = start + snippet.length;
    textarea.focus();
    try { textarea.setSelectionRange(pos, pos); } catch (e) {}
  }

  function activeTplEditor() {
    return mailTplMode === "html"
      ? document.getElementById("mail-tpl-html")
      : document.getElementById("mail-tpl-text");
  }

  function fillSelect(sel, items, valueKey, labelFn, placeholder) {
    if (!sel) return;
    var cur = sel.value;
    var html = placeholder ? '<option value="">' + esc(placeholder) + "</option>" : "";
    html += (items || []).map(function (it) {
      return '<option value="' + esc(it[valueKey]) + '">' + esc(labelFn(it)) + "</option>";
    }).join("");
    sel.innerHTML = html;
    if (cur) sel.value = cur;
  }

  function mailLoadSelects() {
    return Promise.all([
      mailApi("/api/mailing/templates"),
      mailApi("/api/mailing/domains")
    ]).then(function (results) {
      var tplRes = results[0];
      var domRes = results[1];
      mailTemplates = (tplRes && tplRes.ok && tplRes.data.templates) || [];
      mailDomains = (domRes && domRes.ok && domRes.data.domains) || [];
      var labelTpl = function (t) { return t.name; };
      var labelDom = function (d) { return d.domain + " (" + (d.from_local || "noreply") + "@…)"; };
      fillSelect(document.getElementById("mail-camp-tpl"), mailTemplates, "id", labelTpl, "Şablon seç");
      fillSelect(document.getElementById("mail-camp-domain"), mailDomains, "id", labelDom, "Domain seç");
      fillSelect(document.getElementById("mail-ivr-tpl"), mailTemplates, "id", labelTpl, "Şablon seç");
      fillSelect(document.getElementById("mail-ivr-domain"), mailDomains, "id", labelDom, "Domain seç");
    });
  }

  function mailLoadCampaigns() {
    return mailApi("/api/mailing/campaigns").then(function (res) {
      var tbody = document.getElementById("mail-camp-table");
      if (!tbody) return;
      if (!res || !res.ok) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.campaigns || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Kampanya yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (c) {
        var actions = "";
        if (c.status === "draft" || c.status === "queued") {
          actions += '<button type="button" class="btn btn-sm btn-primary mail-queue-camp" data-id="' + c.id + '">Kuyruğa al</button> ';
        }
        actions += '<button type="button" class="btn btn-sm mail-del-camp" data-id="' + c.id + '">Sil</button>';
        return "<tr>" +
          "<td>" + esc(c.name) + "</td>" +
          "<td>" + esc(c.status) + "</td>" +
          "<td>" + esc(c.recipient_count) + "</td>" +
          "<td>" + esc(fmtTime(c.created_at)) + "</td>" +
          '<td style="white-space:nowrap;">' + actions + "</td></tr>";
      }).join("");
    });
  }

  function mailLoadIvr() {
    return Promise.all([
      mailApi("/api/mailing/ivr/rules"),
      mailApi("/api/mailing/ivr/events?limit=100")
    ]).then(function (results) {
      var rulesRes = results[0];
      var evRes = results[1];
      if (rulesRes && rulesRes.ok) {
        var rules = rulesRes.data.rules || [];
        var rule = rules[0];
        if (rule) {
          document.getElementById("mail-ivr-rule-id").value = rule.id;
          document.getElementById("mail-ivr-name").value = rule.name || "";
          document.getElementById("mail-ivr-tpl").value = rule.template_id || "";
          document.getElementById("mail-ivr-domain").value = rule.domain_id || "";
          document.getElementById("mail-ivr-delay").value = rule.delay_seconds || 0;
          document.getElementById("mail-ivr-active").checked = !!rule.active;
        }
      }
      var urlEl = document.getElementById("mail-ivr-webhook-url");
      if (urlEl) urlEl.textContent = "POST " + location.origin + "/api/mailing/webhooks/ivr";

      var tbody = document.getElementById("mail-ivr-table");
      if (!tbody) return;
      var events = (evRes && evRes.ok && evRes.data.events) || [];
      if (!events.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Olay yok</td></tr>';
        return;
      }
      tbody.innerHTML = events.map(function (e) {
        return "<tr>" +
          "<td>" + esc(fmtTime(e.created_at)) + "</td>" +
          "<td>" + esc(e.phone) + "</td>" +
          "<td>" + esc(e.email) + "</td>" +
          "<td>" + esc(e.status) + "</td>" +
          "<td>" + esc(e.error) + "</td></tr>";
      }).join("");
    });
  }

  function mailLoadReports() {
    var channel = (document.getElementById("mail-rep-channel") || {}).value || "";
    var status = (document.getElementById("mail-rep-status") || {}).value || "";
    var url = "/api/mailing/sends?limit=300";
    if (channel) url += "&channel=" + encodeURIComponent(channel);
    if (status) url += "&status=" + encodeURIComponent(status);
    return Promise.all([
      mailApi("/api/mailing/dashboard"),
      mailApi(url)
    ]).then(function (results) {
      var dash = results[0];
      var sendsRes = results[1];
      if (dash && dash.ok) {
        var k = dash.data.kpi || {};
        setText("mail-rep-delivered", k.sends_delivered);
        setText("mail-rep-queued", k.sends_queued);
        setText("mail-rep-failed", k.sends_failed);
        setText("mail-rep-opened", k.opened);
      }
      var tbody = document.getElementById("mail-rep-table");
      if (!tbody) return;
      var rows = (sendsRes && sendsRes.ok && sendsRes.data.sends) || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Gönderim yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (s) {
        return "<tr>" +
          "<td>" + esc(fmtTime(s.created_at)) + "</td>" +
          "<td>" + esc(s.channel) + "</td>" +
          "<td>" + esc(s.to_email) + "</td>" +
          "<td>" + esc(s.subject) + "</td>" +
          "<td>" + esc(s.status) + "</td>" +
          "<td>" + esc(s.provider_msg_id) + "</td></tr>";
      }).join("");
    });
  }

  function mailLoadSettings() {
    return mailApi("/api/mailing/settings").then(function (res) {
      if (!res || !res.ok) return;
      var s = res.data.settings || {};
      mailDomains = res.data.domains || [];
      document.getElementById("mail-set-mode").value = s.provider_mode || "stub";
      document.getElementById("mail-set-host").value = s.smtp_host || "";
      document.getElementById("mail-set-port").value = s.smtp_port || "465";
      document.getElementById("mail-set-user").value = s.smtp_user || "";
      document.getElementById("mail-set-pass").value = "";
      document.getElementById("mail-set-default-domain").value = s.default_domain_id || "";
      var scAff = document.getElementById("mail-set-sc-affid");
      var scSub = document.getElementById("mail-set-sc-subid");
      if (scAff) scAff.value = s.smartico_affiliate_id || "";
      if (scSub) scSub.value = s.smartico_subid_param || "afp1";
      setText("mail-set-webhook-masked", s.webhook_secret_masked || "—");
      setText("mail-set-pass-hint", s.smtp_password_set ? "Şifre kayıtlı (değiştirmek için yaz)" : "Şifre yok");
      updateProviderPill(s.provider_mode);
      renderDomainsTable(mailDomains);
    });
  }

  function renderDomainsTable(domains) {
    var tbody = document.getElementById("mail-domains-table");
    if (!tbody) return;
    if (!domains.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Domain yok</td></tr>';
      return;
    }
    tbody.innerHTML = domains.map(function (d) {
      var from = (d.from_local || "noreply") + "@" + d.domain;
      return "<tr>" +
        "<td>" + esc(d.domain) + "</td>" +
        "<td>" + esc(d.from_name) + " &lt;" + esc(from) + "&gt;</td>" +
        "<td>" + esc(d.status) + "</td>" +
        "<td>" + esc(d.dns_status) + "</td>" +
        "<td>" + esc(d.notes) + "</td>" +
        '<td><button type="button" class="btn btn-sm mail-edit-domain" data-id="' + d.id + '">Düzenle</button></td></tr>';
    }).join("");
  }

  function bindEvents() {
    var tabs = document.getElementById("mail-tabs");
    if (tabs) {
      tabs.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-mail-tab]");
        if (!btn) return;
        switchMailTab(btn.getAttribute("data-mail-tab"));
      });
    }

    var cForm = document.getElementById("mail-contact-form");
    if (cForm) {
      cForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var tags = (document.getElementById("mail-c-tags").value || "").split(",").map(function (t) {
          return t.trim();
        }).filter(Boolean);
        mailApi("/api/mailing/contacts", {
          method: "POST",
          body: {
            email: document.getElementById("mail-c-email").value.trim(),
            name: document.getElementById("mail-c-name").value.trim(),
            tags: tags
          }
        }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Eklenemedi");
            return;
          }
          cForm.reset();
          mailToast("Kontak eklendi");
          mailLoadContacts();
          mailLoadTags();
        });
      });
    }

    bindClick("mail-btn-import-csv", function () {
      var box = document.getElementById("mail-csv-box");
      if (box) box.hidden = !box.hidden;
    });
    bindClick("mail-csv-submit", function () {
      mailApi("/api/mailing/contacts/import", {
        method: "POST",
        body: {
          csv: document.getElementById("mail-csv-input").value,
          tag: document.getElementById("mail-csv-tag").value.trim()
        }
      }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Import başarısız");
          return;
        }
        mailToast("Yeni: " + res.data.created + " · Güncellenen: " + res.data.updated + " · Atlanan: " + res.data.skipped);
        mailLoadContacts();
        mailLoadTags();
      });
    });
    var bulkForm = document.getElementById("mail-bulk-import-form");
    if (bulkForm) {
      bulkForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var fileInput = document.getElementById("mail-bulk-file");
        var file = fileInput && fileInput.files && fileInput.files[0];
        if (!file) { mailToast("Önce bir CSV dosyası seç"); return; }
        var tag = (document.getElementById("mail-bulk-tag").value || "").trim();
        var fd = new FormData();
        fd.append("file", file);
        fd.append("tag", tag);
        var progBox = document.getElementById("mail-bulk-progress");
        var progBar = document.getElementById("mail-bulk-progress-bar");
        var progText = document.getElementById("mail-bulk-progress-text");
        if (progBox) progBox.hidden = false;
        if (progBar) progBar.style.width = "0%";
        if (progText) progText.textContent = "Dosya yükleniyor…";
        mailApi("/api/mailing/contacts/import/start", { method: "POST", body: fd, timeoutMs: 20 * 60 * 1000 })
          .then(function (res) {
            if (!res || !res.ok) {
              mailToast((res && res.data && res.data.error) || "Yükleme başlatılamadı");
              if (progBox) progBox.hidden = true;
              return;
            }
            mailToast("Yükleme başladı, arka planda işleniyor…");
            fileInput.value = "";
            mailPollImportJob(res.data.job_id);
          });
      });
    }
    bindClick("mail-contacts-refresh", mailLoadContacts);
    var qEl = document.getElementById("mail-contact-q");
    if (qEl) qEl.addEventListener("input", debounce(mailLoadContacts, 300));
    var tagEl = document.getElementById("mail-contact-tag-filter");
    if (tagEl) tagEl.addEventListener("change", mailLoadContacts);

    document.addEventListener("click", function (e) {
      var delC = e.target.closest(".mail-del-contact");
      if (delC) {
        if (!confirm("Kontak silinsin mi?")) return;
        mailApi("/api/mailing/contacts/" + delC.getAttribute("data-id"), { method: "DELETE" })
          .then(function () { mailLoadContacts(); });
        return;
      }
      var editT = e.target.closest(".mail-edit-tpl");
      if (editT) {
        var tid = Number(editT.getAttribute("data-id"));
        var t = mailTemplates.find(function (x) { return x.id === tid; });
        if (!t) return;
        document.getElementById("mail-tpl-id").value = t.id;
        document.getElementById("mail-tpl-name").value = t.name || "";
        document.getElementById("mail-tpl-subject").value = t.subject || "";
        document.getElementById("mail-tpl-html").value = t.html_body || "";
        document.getElementById("mail-tpl-text").value = t.text_body || "";
        setText("mail-tpl-form-title", "Şablon düzenle #" + t.id);
        // HTML doluysa HTML moduna geç
        setTplMode((t.html_body || "").trim() && !(t.text_body || "").trim() ? "html" : "simple");
        if ((t.html_body || "").trim() && (t.text_body || "").trim()) setTplMode("html");
        refreshTplPreview();
        return;
      }
      var delT = e.target.closest(".mail-del-tpl");
      if (delT) {
        if (!confirm("Şablon silinsin mi?")) return;
        mailApi("/api/mailing/templates/" + delT.getAttribute("data-id"), { method: "DELETE" })
          .then(function () { mailLoadTemplates(); });
        return;
      }
      var queueC = e.target.closest(".mail-queue-camp");
      if (queueC) {
        if (!confirm("Kampanya stub kuyruğa alınsın mı?")) return;
        mailApi("/api/mailing/campaigns/" + queueC.getAttribute("data-id") + "/queue", { method: "POST" })
          .then(function (res) {
            mailToast((res && res.data && res.data.message) || (res && res.ok ? "Kuyruğa alındı" : "Hata"));
            mailLoadCampaigns();
          });
        return;
      }
      var delCamp = e.target.closest(".mail-del-camp");
      if (delCamp) {
        if (!confirm("Kampanya silinsin mi?")) return;
        mailApi("/api/mailing/campaigns/" + delCamp.getAttribute("data-id"), { method: "DELETE" })
          .then(function () { mailLoadCampaigns(); });
        return;
      }
      var editD = e.target.closest(".mail-edit-domain");
      if (editD) {
        var did = Number(editD.getAttribute("data-id"));
        var d = mailDomains.find(function (x) { return x.id === did; });
        if (!d) return;
        var fromName = prompt("From adı", d.from_name || "");
        if (fromName === null) return;
        var fromLocal = prompt("From local (noreply)", d.from_local || "noreply");
        if (fromLocal === null) return;
        mailApi("/api/mailing/domains/" + did, {
          method: "PATCH",
          body: { from_name: fromName, from_local: fromLocal }
        }).then(function () { mailLoadSettings(); });
      }
    });

    bindClick("mail-tpl-mode-simple", function () { setTplMode("simple"); });
    bindClick("mail-tpl-mode-html", function () { setTplMode("html"); });
    bindClick("mail-tpl-insert-name", function () { insertAtCursor(activeTplEditor(), "{{name}}"); refreshTplPreview(); });
    bindClick("mail-tpl-insert-email", function () { insertAtCursor(activeTplEditor(), "{{email}}"); refreshTplPreview(); });
    bindClick("mail-tpl-insert-link", function () {
      var url = (document.getElementById("mail-tpl-link-url").value || "").trim();
      if (!url) { mailToast("Önce hedef URL yaz"); return; }
      if (!/^https?:\/\//i.test(url)) url = "https://" + url;
      var isSc = (document.getElementById("mail-tpl-link-smartico") || {}).checked;
      insertAtCursor(activeTplEditor(), "{{link:" + (isSc ? "sc:" : "") + url + "}}");
      refreshTplPreview();
    });

    var htmlEl = document.getElementById("mail-tpl-html");
    if (htmlEl) htmlEl.addEventListener("input", debounce(refreshTplPreview, 250));
    var textEl = document.getElementById("mail-tpl-text");
    if (textEl) textEl.addEventListener("input", debounce(function () {
      if (mailTplMode === "html") refreshTplPreview();
    }, 250));

    var tplForm = document.getElementById("mail-tpl-form");
    if (tplForm) {
      tplForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var id = document.getElementById("mail-tpl-id").value;
        var body = {
          name: document.getElementById("mail-tpl-name").value.trim(),
          subject: document.getElementById("mail-tpl-subject").value.trim(),
          html_body: document.getElementById("mail-tpl-html").value,
          text_body: document.getElementById("mail-tpl-text").value,
          sync_html_from_text: mailTplMode === "simple"
        };
        if (mailTplMode === "simple") {
          // HTML'i sunucu üretsin
          body.html_body = body.html_body || "";
        }
        var req = id
          ? mailApi("/api/mailing/templates/" + id, { method: "PATCH", body: body })
          : mailApi("/api/mailing/templates", { method: "POST", body: body });
        req.then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Kaydedilemedi");
            return;
          }
          mailToast("Şablon kaydedildi");
          if (res.data.template) {
            document.getElementById("mail-tpl-id").value = res.data.template.id;
            document.getElementById("mail-tpl-html").value = res.data.template.html_body || "";
            document.getElementById("mail-tpl-text").value = res.data.template.text_body || "";
            setText("mail-tpl-form-title", "Şablon düzenle #" + res.data.template.id);
          }
          mailLoadTemplates();
          refreshTplPreview();
        });
      });
    }
    bindClick("mail-tpl-reset", function () {
      document.getElementById("mail-tpl-id").value = "";
      document.getElementById("mail-tpl-form").reset();
      setText("mail-tpl-form-title", "Yeni şablon");
      setTplMode("simple");
      refreshTplPreview();
    });
    bindClick("mail-tpl-refresh", mailLoadTemplates);
    bindClick("mail-tpl-test-send", function () {
      var id = document.getElementById("mail-tpl-id").value;
      var email = (document.getElementById("mail-tpl-test-email").value || "").trim();
      if (!id) {
        mailToast("Önce şablonu kaydet");
        return;
      }
      if (!email) {
        mailToast("Test e-postası yaz");
        return;
      }
      mailApi("/api/mailing/templates/" + id + "/test-send", {
        method: "POST",
        body: { email: email }
      }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Test gönderilemedi");
          return;
        }
        var n = (res.data.tracked_links || []).length;
        mailToast((res.data.message || "OK") + (n ? " · " + n + " takip linki" : ""));
      });
    });

    var campForm = document.getElementById("mail-camp-form");
    if (campForm) {
      campForm.addEventListener("submit", function (e) {
        e.preventDefault();
        mailApi("/api/mailing/campaigns", {
          method: "POST",
          body: {
            name: document.getElementById("mail-camp-name").value.trim(),
            template_id: Number(document.getElementById("mail-camp-tpl").value),
            domain_id: Number(document.getElementById("mail-camp-domain").value),
            tag_filter: document.getElementById("mail-camp-tag").value.trim(),
            notes: document.getElementById("mail-camp-notes").value.trim()
          }
        }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Oluşturulamadı");
            return;
          }
          mailToast("Kampanya oluşturuldu · " + (res.data.campaign.recipient_count || 0) + " alıcı");
          campForm.reset();
          mailLoadCampaigns();
        });
      });
    }
    bindClick("mail-camp-refresh", mailLoadCampaigns);

    var ivrForm = document.getElementById("mail-ivr-form");
    if (ivrForm) {
      ivrForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var id = document.getElementById("mail-ivr-rule-id").value;
        if (!id) { mailToast("Kural bulunamadı"); return; }
        mailApi("/api/mailing/ivr/rules/" + id, {
          method: "PATCH",
          body: {
            name: document.getElementById("mail-ivr-name").value.trim(),
            template_id: Number(document.getElementById("mail-ivr-tpl").value) || null,
            domain_id: Number(document.getElementById("mail-ivr-domain").value) || null,
            delay_seconds: Number(document.getElementById("mail-ivr-delay").value) || 0,
            active: document.getElementById("mail-ivr-active").checked
          }
        }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Kaydedilemedi");
            return;
          }
          mailToast("IVR kuralı kaydedildi");
          mailLoadIvr();
        });
      });
    }
    bindClick("mail-ivr-refresh", mailLoadIvr);
    bindClick("mail-rep-refresh", mailLoadReports);
    var ch = document.getElementById("mail-rep-channel");
    if (ch) ch.addEventListener("change", mailLoadReports);
    var st = document.getElementById("mail-rep-status");
    if (st) st.addEventListener("change", mailLoadReports);

    var setForm = document.getElementById("mail-settings-form");
    if (setForm) {
      setForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = {
          provider_mode: document.getElementById("mail-set-mode").value,
          smtp_host: document.getElementById("mail-set-host").value.trim(),
          smtp_port: document.getElementById("mail-set-port").value.trim(),
          smtp_user: document.getElementById("mail-set-user").value.trim(),
          default_domain_id: document.getElementById("mail-set-default-domain").value.trim()
        };
        var pw = document.getElementById("mail-set-pass").value;
        if (pw) body.smtp_password = pw;
        mailApi("/api/mailing/settings", { method: "PATCH", body: body }).then(function (res) {
          if (!res || !res.ok) {
            mailToast("Kaydedilemedi");
            return;
          }
          mailToast("Ayarlar kaydedildi");
          mailLoadSettings();
        });
      });
    }
    var scForm = document.getElementById("mail-smartico-form");
    if (scForm) {
      scForm.addEventListener("submit", function (e) {
        e.preventDefault();
        mailApi("/api/mailing/settings", {
          method: "PATCH",
          body: {
            smartico_affiliate_id: document.getElementById("mail-set-sc-affid").value.trim(),
            smartico_subid_param: document.getElementById("mail-set-sc-subid").value.trim() || "afp1"
          }
        }).then(function (res) {
          if (!res || !res.ok) { mailToast("Kaydedilemedi"); return; }
          mailToast("Smartico ayarları kaydedildi");
          mailLoadSettings();
        });
      });
    }
    bindClick("mail-btn-sync-smartico", function () {
      mailToast("Smartico segmentleri güncelleniyor…");
      mailApi("/api/mailing/crm/sync-smartico", { method: "POST", timeoutMs: 30000 }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Güncellenemedi");
          return;
        }
        mailToast(res.data.message || "Segmentler güncellendi");
        mailLoadContacts();
        mailLoadTags();
      });
    });
    bindClick("mail-btn-rotate-secret", function () {
      if (!confirm("Webhook secret yenilensin mi? IVR tarafını da güncellemen gerekir.")) return;
      mailApi("/api/mailing/settings", {
        method: "PATCH",
        body: { rotate_webhook_secret: true }
      }).then(function (res) {
        if (!res || !res.ok) { mailToast("Yenilenemedi"); return; }
        mailToast("Secret yenilendi");
        mailLoadSettings();
      });
    });
  }

  function bindClick(id, fn) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", fn);
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(null, args); }, ms);
    };
  }

  window.MakroMailing = {
    init: function () {
      if (mailLoaded) return;
      mailLoaded = true;
      bindEvents();
      setTplMode("simple");
    },
    onShow: function () {
      if (!mailLoaded) this.init();
      switchMailTab(mailActiveTab || "dashboard");
    },
    setPermissions: function (perms) {
      mailPerms = perms || [];
    },
    refresh: function () {
      mailLoadTab(mailActiveTab);
    }
  };
})();
