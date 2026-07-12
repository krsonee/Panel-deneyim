(function () {
  "use strict";

  var mailActiveTab = "dashboard";
  var mailPerms = [];
  var mailTemplates = [];
  var mailDomains = [];
  var mailTags = [];
  var mailLoaded = false;
  var mailTplMode = "simple";
  var mailImportQueue = [];
  var mailImportBusy = false;
  var mailImportCurrentJobId = null;
  var MAIL_IMPORT_SESSION_KEY = "makro_mail_import_v1";
  var MAIL_IMPORT_DISMISSED_KEY = "makro_mail_import_dismissed_v1";
  var MAIL_TAB_STORAGE_KEY = "makro_mail_tab";
  var mailImportPollTimer = null;
  var mailImportRefreshTimer = null;
  var mailImportHandledJobs = {};
  var mailImportActiveXhr = null;
  var MAIL_AUTO_SPLIT_BYTES = 20 * 1024 * 1024;
  var MAIL_CHUNK_TARGET_BYTES = 10 * 1024 * 1024;
  var MAIL_UPLOAD_STALL_MS = 120 * 1000;

  var MAIL_IMPORT_BADGE = {
    uploading: { bg: "rgba(59,130,246,0.18)", color: "#93c5fd", border: "rgba(59,130,246,0.35)", label: "Yükleniyor" },
    processing: { bg: "rgba(34,197,94,0.15)", color: "#86efac", border: "rgba(34,197,94,0.35)", label: "İşleniyor" },
    pending: { bg: "rgba(245,158,11,0.15)", color: "#fcd34d", border: "rgba(245,158,11,0.35)", label: "Başlıyor" },
    done: { bg: "rgba(34,197,94,0.15)", color: "#86efac", border: "rgba(34,197,94,0.35)", label: "Tamamlandı" },
    error: { bg: "rgba(239,68,68,0.15)", color: "#fca5a5", border: "rgba(239,68,68,0.38)", label: "Hata" },
    cancelled: { bg: "rgba(148,163,184,0.12)", color: "#cbd5e1", border: "rgba(148,163,184,0.3)", label: "İptal" },
    idle: { bg: "rgba(148,163,184,0.12)", color: "#cbd5e1", border: "rgba(148,163,184,0.3)", label: "Hazır" }
  };

  var MAIL_TAB_PERMS = {
    dashboard: "mailing.dashboard",
    crm: "mailing.crm",
    templates: "mailing.templates",
    campaigns: "mailing.campaigns",
    ivr: "mailing.ivr",
    reports: "mailing.reports",
    settings: "mailing.settings"
  };

  function mailHas(key) {
    if (!mailPerms || !mailPerms.length) return true;
    if (mailPerms.indexOf("*") >= 0) return true;
    return mailPerms.indexOf(key) >= 0;
  }

  function mailFirstAllowedTab() {
    var order = ["dashboard", "crm", "templates", "campaigns", "ivr", "reports", "settings"];
    for (var i = 0; i < order.length; i++) {
      if (mailHas(MAIL_TAB_PERMS[order[i]])) return order[i];
    }
    return "dashboard";
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

  function fmtNum(n) {
    n = Number(n) || 0;
    try { return n.toLocaleString("tr-TR"); } catch (e) { return String(n); }
  }

  function fmtBytes(n) {
    n = Number(n) || 0;
    var units = ["B", "KB", "MB", "GB"];
    var i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + " " + units[i];
  }

  function mailUploadWithProgress(url, formData, onProgress, opts) {
    opts = opts || {};
    return new Promise(function (resolve) {
      var xhr = new XMLHttpRequest();
      mailImportActiveXhr = xhr;
      var lastAt = Date.now();
      var lastLoaded = 0;
      var stallIv = setInterval(function () {
        if (Date.now() - lastAt > (opts.stallMs || MAIL_UPLOAD_STALL_MS)) {
          clearInterval(stallIv);
          mailImportActiveXhr = null;
          try { xhr.abort(); } catch (e) { /* ignore */ }
          resolve({
            ok: false,
            status: 0,
            data: {
              error: "Yükleme durdu (bağlantı kesildi veya sunucu yanıt vermiyor). Dosya otomatik parçalara bölünerek tekrar denenecek.",
              stalled: true
            }
          });
        }
      }, 4000);
      function done(res) {
        clearInterval(stallIv);
        mailImportActiveXhr = null;
        resolve(res);
      }
      xhr.open("POST", url, true);
      xhr.timeout = 6 * 60 * 60 * 1000;
      if (xhr.upload) {
        xhr.upload.addEventListener("progress", function (e) {
          if (e.loaded > lastLoaded) {
            lastLoaded = e.loaded;
            lastAt = Date.now();
          }
          if (onProgress) onProgress(e.loaded, e.lengthComputable ? e.total : 0);
        });
      }
      xhr.onload = function () {
        if (xhr.status === 401) { location.href = "/admin/login"; done(null); return; }
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
        done({ ok: xhr.status >= 200 && xhr.status < 300, status: xhr.status, data: data });
      };
      xhr.onerror = function () {
        done({ ok: false, status: 0, data: { error: "Ağ hatası - yükleme kesildi." } });
      };
      xhr.ontimeout = function () {
        done({ ok: false, status: 0, data: { error: "Yükleme zaman aşımına uğradı." } });
      };
      xhr.send(formData);
    });
  }

  var MAIL_BULK_MAX_BYTES = 5 * 1024 * 1024 * 1024;

  function mailValidateImportFile(file) {
    var lowerName = file.name.toLowerCase();
    if (!/\.(csv|xlsx|xlsm)$/.test(lowerName)) return "sadece .csv veya .xlsx yükleyebilirsin";
    if (file.size > MAIL_BULK_MAX_BYTES) return "5GB üstü, bölüp tekrar dene";
    return null;
  }

  // Yapıştırılan ham e-posta metnini (10 milyona kadar) DOM'a hiç yazdırmadan
  // CSV'ye çevirip mevcut çoklu dosya kuyruğuna sahte bir File olarak ekler.
  function mailQueueTextAsFile(rawText, tag, labelPrefix) {
    var tokens = String(rawText || "").split(/[\s,;]+/).filter(Boolean);
    if (!tokens.length) return { count: 0, error: null };
    var csv = "email\n" + tokens.join("\n");
    var blob = new Blob([csv], { type: "text/csv" });
    var fname = (labelPrefix || "yapistirilan-liste") + "-" + Date.now() + ".csv";
    var file = new File([blob], fname, { type: "text/csv" });
    var err = mailValidateImportFile(file);
    if (err) return { count: tokens.length, error: err };
    mailEnqueueImport(file, tag);
    return { count: tokens.length, error: null };
  }

  function mailReadDismissedImportJobs() {
    try {
      var raw = localStorage.getItem(MAIL_IMPORT_DISMISSED_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (e) { return []; }
  }

  function mailDismissImportJob(jobId) {
    if (!jobId) return;
    var ids = mailReadDismissedImportJobs();
    if (ids.indexOf(jobId) < 0) ids.push(jobId);
    while (ids.length > 40) ids.shift();
    try { localStorage.setItem(MAIL_IMPORT_DISMISSED_KEY, JSON.stringify(ids)); } catch (e) { /* ignore */ }
  }

  function mailIsImportJobDismissed(jobId) {
    return mailReadDismissedImportJobs().indexOf(jobId) >= 0;
  }

  function mailMarkImportJobHandled(jobId) {
    if (jobId) mailImportHandledJobs[jobId] = true;
  }

  function mailWasImportJobHandled(jobId) {
    return !!(jobId && mailImportHandledJobs[jobId]);
  }

  function mailReadImportSession() {
    try {
      var raw = sessionStorage.getItem(MAIL_IMPORT_SESSION_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }

  function mailSaveImportSession(patch) {
    var cur = mailReadImportSession() || {};
    try {
      sessionStorage.setItem(MAIL_IMPORT_SESSION_KEY, JSON.stringify(Object.assign(cur, patch, { ts: Date.now() })));
    } catch (e) { /* quota */ }
  }

  function mailClearImportSession() {
    try { sessionStorage.removeItem(MAIL_IMPORT_SESSION_KEY); } catch (e) { /* ignore */ }
  }

  function mailFormatUploadError(res) {
    if (!res) return "Sunucuya bağlanılamadı. İnternet bağlantını veya oturum süreni kontrol et.";
    if (res.status === 401) return "Oturum süresi doldu — sayfayı yenileyip tekrar giriş yap.";
    if (res.status === 413) return "Dosya sunucu limitini aştı. Daha küçük parçalara böl.";
    if (res.status === 502 || res.status === 504) {
      return "Sunucu zaman aşımı (yük çok uzun sürdü veya bağlantı kesildi). Dosyayı parçalara bölüp tekrar dene.";
    }
    if (res.status >= 500) return "Sunucu hatası (HTTP " + res.status + "). Biraz sonra tekrar dene.";
    return (res.data && res.data.error) || ("İstek başarısız (HTTP " + res.status + ")");
  }

  function mailSetImportBadge(phase) {
    var badge = document.getElementById("mail-import-status-badge");
    var style = MAIL_IMPORT_BADGE[phase] || MAIL_IMPORT_BADGE.idle;
    if (!badge) return;
    badge.textContent = style.label;
    badge.style.background = style.bg;
    badge.style.color = style.color;
    badge.style.border = "1px solid " + style.border;
  }

  function mailShowImportDashboard(show) {
    var dash = document.getElementById("mail-import-dashboard");
    if (dash) dash.hidden = !show;
  }

  function mailSetImportDashboard(opts) {
    opts = opts || {};
    var phase = opts.phase || "idle";
    var title = opts.title || "Yükleme durumu";
    var sub = opts.sub || "";
    var showProgress = !!opts.showProgress;
    var showError = !!opts.showError;
    var errorText = opts.errorText || "";
    var showDismiss = !!opts.showDismiss;
    mailShowImportDashboard(phase !== "idle" || showError);
    mailSetImportBadge(phase);
    setText("mail-import-status-title", title);
    setText("mail-import-status-sub", sub || "—");
    var errBox = document.getElementById("mail-import-error-box");
    var errText = document.getElementById("mail-import-error-text");
    if (errBox) errBox.hidden = !showError;
    if (errText && showError) errText.textContent = errorText;
    var dismissBtn = document.getElementById("mail-import-dismiss");
    if (dismissBtn) dismissBtn.hidden = !showDismiss;
    var progBox = document.getElementById("mail-bulk-progress");
    if (progBox) progBox.hidden = !showProgress;
  }

  function mailStatusLabelTr(status) {
    var map = {
      pending: "Bekliyor",
      running: "İşleniyor",
      done: "Tamam",
      error: "Hata",
      cancelled: "İptal",
      cancelling: "İptal ediliyor"
    };
    return map[status] || status || "—";
  }

  function mailRenderImportHistory(jobs) {
    var box = document.getElementById("mail-import-history");
    var list = document.getElementById("mail-import-history-list");
    if (!box || !list) return false;
    var rows = (jobs || []).slice(0, 8);
    if (!rows.length) { box.hidden = true; return false; }
    box.hidden = false;
    list.innerHTML = rows.map(function (j) {
      var isActive = j.status === "pending" || j.status === "running" || j.status === "cancelling";
      var statusColor = j.status === "error" ? "#fca5a5"
        : j.status === "done" ? "#86efac"
        : j.status === "cancelled" ? "#cbd5e1"
        : isActive ? "#93c5fd" : "#cbd5e1";
      var progress = isActive || j.status === "done"
        ? (" · " + fmtNum(j.processed_rows || 0) + " satır")
        : "";
      var errHint = j.status === "error" && j.error
        ? ' <span style="color:#fca5a5;">— ' + esc(j.error) + "</span>" : "";
      var activeMark = isActive ? ' <span style="color:#93c5fd;font-weight:700;">● aktif</span>' : "";
      return '<div style="display:flex;justify-content:space-between;gap:0.5rem;flex-wrap:wrap;padding:0.4rem 0;border-bottom:1px solid rgba(148,163,184,0.12);">' +
        "<span><strong>" + esc(j.filename || "Dosya") + "</strong>" + activeMark +
        ' · <span style="color:' + statusColor + ';">' + esc(mailStatusLabelTr(j.status)) + "</span>" +
        progress + (j.tag ? ' · <span class="muted">' + esc(j.tag) + "</span>" : "") + errHint + "</span>" +
        '<span class="muted">' + esc(fmtTime(j.updated_at || j.created_at)) + "</span></div>";
    }).join("");
    return true;
  }

  function mailBulkSetError(msg, fileLabel, jobId) {
    var progBox = document.getElementById("mail-bulk-progress");
    var progBar = document.getElementById("mail-bulk-progress-bar");
    var progText = document.getElementById("mail-bulk-progress-text");
    if (progBox) progBox.hidden = false;
    if (progBar) { progBar.style.width = "100%"; progBar.style.background = "#ef4444"; }
    if (progText) progText.textContent = (fileLabel ? (fileLabel + " — ") : "") + "Hata: " + msg;
    mailSetImportDashboard({
      phase: "error",
      title: fileLabel ? (fileLabel + " yüklenemedi") : "Yükleme başarısız",
      sub: "Aşağıdaki hatayı kontrol et. Gerekirse dosyayı parçalara bölüp yeniden yükle.",
      showProgress: true,
      showError: true,
      errorText: msg,
      showDismiss: true
    });
    if (jobId) mailMarkImportJobHandled(jobId);
    mailClearImportSession();
  }

  function mailBulkResetBar() {
    var progBar = document.getElementById("mail-bulk-progress-bar");
    if (progBar) progBar.style.background = "";
  }

  function mailRenderImportQueue() {
    var box = document.getElementById("mail-bulk-queue");
    var list = document.getElementById("mail-bulk-queue-list");
    if (!box || !list) return;
    if (!mailImportQueue.length) { box.hidden = true; return; }
    box.hidden = false;
    list.textContent = mailImportQueue.length + " dosya · " +
      mailImportQueue.map(function (item) { return item.file.name; }).join(", ");
  }

  function mailUpdateBulkFormState() {
    var btn = document.querySelector('#mail-bulk-import-form button[type="submit"]');
    if (!btn) return;
    btn.disabled = false;
    var origText = btn.getAttribute("data-orig-text") || btn.textContent;
    btn.setAttribute("data-orig-text", origText);
    if (mailImportBusy || mailImportQueue.length) {
      btn.textContent = "Kuyruğa ekle";
    } else {
      btn.textContent = origText;
    }
  }

  function mailSplitCsvIntoChunks(file, targetBytes) {
    targetBytes = targetBytes || MAIL_CHUNK_TARGET_BYTES;
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onerror = function () { reject(new Error("Dosya okunamadı")); };
      reader.onload = function () {
        try {
          var text = String(reader.result || "");
          var lines = text.split(/\r?\n/).filter(function (ln) { return ln.trim(); });
          if (!lines.length) { resolve([]); return; }
          var hasHeader = /^email$/i.test(lines[0].trim());
          var header = "email";
          var dataLines = hasHeader ? lines.slice(1) : lines;
          var chunks = [];
          var buf = [header];
          var size = header.length + 1;
          var base = file.name.replace(/\.csv$/i, "");
          function flush(partNo) {
            if (buf.length <= 1) return;
            var body = buf.join("\n");
            var fname = base + "-part" + partNo + ".csv";
            chunks.push(new File([body], fname, { type: "text/csv" }));
            buf = [header];
            size = header.length + 1;
          }
          var partNo = 1;
          dataLines.forEach(function (line) {
            var add = line.length + 1;
            if (size + add > targetBytes && buf.length > 1) {
              flush(partNo++);
            }
            buf.push(line);
            size += add;
          });
          flush(partNo);
          resolve(chunks);
        } catch (e) {
          reject(e);
        }
      };
      reader.readAsText(file);
    });
  }

  function mailEnqueueImport(file, tag, opts) {
    opts = opts || {};
    if (mailActiveTab !== "crm") switchMailTab("crm");
    if (!opts.skipSplit && /\.csv$/i.test(file.name) && file.size > MAIL_AUTO_SPLIT_BYTES) {
      mailShowImportDashboard(true);
      mailSetImportDashboard({
        phase: "pending",
        title: file.name,
        sub: "Büyük CSV parçalara bölünüyor… (Render timeout'u önlemek için ~10MB parçalar)",
        showProgress: false
      });
      mailSplitCsvIntoChunks(file, MAIL_CHUNK_TARGET_BYTES).then(function (parts) {
        if (!parts.length) {
          mailBulkSetError("CSV boş veya bölünemedi.", file.name);
          return;
        }
        mailToast(file.name + ": " + parts.length + " parçaya bölündü, sırayla yükleniyor");
        parts.forEach(function (p) { mailImportQueue.push({ file: p, tag: tag }); });
        mailRenderImportQueue();
        mailUpdateBulkFormState();
        if (!mailImportBusy) mailStartNextImport();
      }).catch(function () {
        mailBulkSetError("Dosya okunurken hata oluştu. Daha küçük parçalara bölüp tekrar dene.", file.name);
      });
      return;
    }
    mailImportQueue.push({ file: file, tag: tag });
    mailRenderImportQueue();
    mailUpdateBulkFormState();
    mailSetImportDashboard({
      phase: "pending",
      title: file.name,
      sub: fmtBytes(file.size) + (tag ? (" · etiket: " + tag) : "") + " — kuyruğa alındı",
      showProgress: false
    });
    if (!mailImportBusy) {
      mailStartNextImport();
    } else {
      mailToast(file.name + ": kuyruğa eklendi · " + mailImportQueue.length + " dosya sırada");
    }
  }

  function mailStartNextImport() {
    if (mailImportBusy) return;
    var next = mailImportQueue.shift();
    mailRenderImportQueue();
    if (!next) {
      mailImportBusy = false;
      mailUpdateBulkFormState();
      return;
    }
    mailImportBusy = true;
    mailUpdateBulkFormState();
    mailRunImportItem(next.file, next.tag);
  }

  function mailRunImportItem(file, tag) {
    var progBox = document.getElementById("mail-bulk-progress");
    var progBar = document.getElementById("mail-bulk-progress-bar");
    var progText = document.getElementById("mail-bulk-progress-text");
    var cancelBtn = document.getElementById("mail-bulk-cancel");
    mailImportCurrentJobId = null;
    mailBulkResetBar();
    mailShowImportDashboard(true);
    if (progBox) progBox.hidden = false;
    if (progBar) progBar.style.width = "2%";
    if (progText) progText.textContent = file.name + " — dosya sunucuya gönderiliyor… %0 · 0 B / " + fmtBytes(file.size);
    if (cancelBtn) cancelBtn.hidden = true;
    mailSetImportDashboard({
      phase: "uploading",
      title: file.name,
      sub: "Dosya sunucuya yükleniyor — büyük dosyalarda bu adım uzun sürebilir, sayfayı kapatma.",
      showProgress: true,
      showError: false
    });
    mailSaveImportSession({
      phase: "upload",
      fileName: file.name,
      fileSize: file.size,
      tag: tag || "",
      jobId: null
    });

    var fd = new FormData();
    fd.append("file", file);
    fd.append("tag", tag);

    function finishItem() {
      mailImportCurrentJobId = null;
      if (cancelBtn) cancelBtn.hidden = true;
      mailImportBusy = false;
      mailUpdateBulkFormState();
      mailStartNextImport();
    }

    var uploadStarted = Date.now();
    var lastPct = 0;
    mailUploadWithProgress("/api/mailing/contacts/import/start", fd, function (loaded, total) {
      var pct = total > 0 ? Math.max(2, Math.round((loaded / total) * 100)) : lastPct;
      if (total > 0) lastPct = pct;
      if (progBar) {
        progBar.style.width = pct + "%";
        progBar.style.background = "var(--green,#22c55e)";
        progBar.style.minWidth = pct > 0 ? "4px" : "0";
      }
      var line = file.name + " — yükleniyor: %" + pct;
      if (total > 0) line += " · " + fmtBytes(loaded) + " / " + fmtBytes(total);
      else line += " · " + fmtBytes(loaded) + " gönderildi";
      if (progText) progText.textContent = line;
      mailSaveImportSession({
        phase: "upload",
        fileName: file.name,
        fileSize: file.size,
        tag: tag || "",
        jobId: null,
        loaded: loaded,
        total: total || file.size,
        pct: pct,
        ts: Date.now()
      });
      mailSetImportDashboard({
        phase: "uploading",
        title: file.name,
        sub: total > 0
          ? ("Sunucuya aktarılıyor: %" + pct + " · " + fmtBytes(loaded) + " / " + fmtBytes(total))
          : (fmtBytes(loaded) + " gönderildi — bağlantı devam ediyor…"),
        showProgress: true
      });
    }, { stallMs: MAIL_UPLOAD_STALL_MS }).then(function (res) {
      if (!res || !res.ok) {
        var errMsg = mailFormatUploadError(res);
        if (res && res.data && res.data.stalled && /\.csv$/i.test(file.name) && file.size > MAIL_AUTO_SPLIT_BYTES && !file.name.match(/-part\d+\.csv$/i)) {
          mailToast(file.name + ": takıldı — parçalara bölünüp yeniden deneniyor…");
          mailImportBusy = false;
          mailEnqueueImport(file, tag, { skipSplit: false });
          return;
        }
        mailToast(file.name + ": " + errMsg);
        mailBulkSetError(errMsg, file.name);
        finishItem();
        mailRefreshImportStatus();
        return;
      }
      mailToast(file.name + ": yükleme tamam, arka planda işleniyor…");
      mailImportCurrentJobId = res.data.job_id;
      mailSaveImportSession({
        phase: "process",
        fileName: file.name,
        fileSize: file.size,
        tag: tag || "",
        jobId: res.data.job_id
      });
      if (cancelBtn) cancelBtn.hidden = false;
      var uploadSec = Math.max(1, Math.round((Date.now() - uploadStarted) / 1000));
      mailSetImportDashboard({
        phase: "processing",
        title: file.name,
        sub: "Dosya alındı (" + uploadSec + " sn). Satırlar işleniyor — bu adım dosya boyutuna göre saatler sürebilir.",
        showProgress: true
      });
      mailPollImportJob(res.data.job_id, finishItem, file.name);
    });
  }

  function switchMailTab(name) {
    name = name || "dashboard";
    if (!mailHas(MAIL_TAB_PERMS[name])) name = mailFirstAllowedTab();
    mailActiveTab = name;
    try { localStorage.setItem(MAIL_TAB_STORAGE_KEY, mailActiveTab); } catch (e) { /* ignore */ }
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
    else if (tab === "crm") { mailLoadTags(); mailLoadContactStats(); mailLoadContacts(); }
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

  function mailLoadContactStats() {
    return mailApi("/api/mailing/contacts/stats").then(function (res) {
      if (!res || !res.ok) return;
      var s = res.data || {};
      setText("mail-crm-stat-total", fmtNum(s.total));
      setText("mail-crm-stat-mailed", fmtNum(s.mailed));
      setText("mail-crm-stat-never", fmtNum(s.never_mailed));
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

  function mailPollImportJob(jobId, onSettled, fileLabel) {
    var progBox = document.getElementById("mail-bulk-progress");
    var progBar = document.getElementById("mail-bulk-progress-bar");
    var progText = document.getElementById("mail-bulk-progress-text");
    var cancelBtn = document.getElementById("mail-bulk-cancel");
    var prefix = fileLabel ? (fileLabel + " — ") : "";
    var failedPolls = 0;
    if (mailImportPollTimer) { clearTimeout(mailImportPollTimer); mailImportPollTimer = null; }
    function settle() {
      if (cancelBtn) cancelBtn.hidden = true;
      if (typeof onSettled === "function") onSettled();
      mailFetchImportHistoryOnly();
    }
    function poll() {
      mailApi("/api/mailing/contacts/import/status/" + jobId, { timeoutMs: 30000 }).then(function (res) {
        if (!res || !res.ok || !res.data.job) {
          failedPolls++;
          if (failedPolls >= 10) {
            mailBulkSetError("Durum bilgisi alınamıyor (bağlantı sorunu). Sayfayı yenileyip tekrar dene.", fileLabel, jobId);
            settle();
            return;
          }
          if (progText) progText.textContent = prefix + "Durum alınamadı, tekrar deneniyor… (" + failedPolls + "/10)";
          mailSetImportDashboard({
            phase: "processing",
            title: fileLabel || "İçe aktarma",
            sub: "Sunucudan durum alınamadı, tekrar deneniyor…",
            showProgress: true
          });
          mailImportPollTimer = setTimeout(poll, 3000);
          return;
        }
        failedPolls = 0;
        var j = res.data.job;
        var hasTotal = j.total_rows > 0;
        var pct = hasTotal ? Math.min(100, Math.round((j.processed_rows / j.total_rows) * 100)) : 0;
        mailShowImportDashboard(true);
        if (progBox) progBox.hidden = false;
        if (progBar) {
          mailBulkResetBar();
          if (hasTotal) progBar.style.width = pct + "%";
          else if (j.processed_rows > 0) progBar.style.width = "35%";
          else progBar.style.width = "12%";
        }
        if (j.status === "cancelling") {
          if (progText) progText.textContent = prefix + "İptal ediliyor…";
          mailSetImportDashboard({
            phase: "processing",
            title: fileLabel || j.filename || "İçe aktarma",
            sub: "İptal isteği işleniyor…",
            showProgress: true
          });
          mailImportPollTimer = setTimeout(poll, 1500);
          return;
        }
        if (progText) {
          var progressLine = hasTotal
            ? "%" + pct + " · " + fmtNum(j.processed_rows) + " / " + fmtNum(j.total_rows) + " satır"
            : fmtNum(j.processed_rows) + " satır işlendi (devam ediyor…)";
          var statsLine = (j.inserted_count != null && j.updated_count != null)
            ? fmtNum(j.inserted_count) + " yeni + " + fmtNum(j.updated_count) + " güncellendi"
            : fmtNum(j.upserted_count) + " eklenen/güncellenen";
          progText.textContent = prefix + (j.status === "pending" ? "Başlıyor… " : "İşleniyor: ") +
            progressLine + " · " + statsLine +
            " · geçersiz: " + fmtNum(j.skipped_count);
        }
        mailSetImportDashboard({
          phase: j.status === "pending" ? "pending" : "processing",
          title: fileLabel || j.filename || "İçe aktarma",
          sub: (j.status === "pending" ? "Sunucu işleme hazırlığı… " : "Satırlar işleniyor… ") +
            (hasTotal
              ? (fmtNum(j.processed_rows) + " / " + fmtNum(j.total_rows) + " satır (%" + pct + ")")
              : (fmtNum(j.processed_rows) + " satır işlendi")) +
            " · " + ((j.inserted_count != null && j.updated_count != null)
              ? (fmtNum(j.inserted_count) + " yeni + " + fmtNum(j.updated_count) + " güncellendi")
              : (fmtNum(j.upserted_count) + " eklenen/güncellenen")) +
            " · geçersiz: " + fmtNum(j.skipped_count),
          showProgress: true
        });
        if (j.status === "done") {
          var doneStats = (j.inserted_count != null && j.updated_count != null)
            ? (fmtNum(j.inserted_count) + " yeni + " + fmtNum(j.updated_count) + " güncellendi")
            : (fmtNum(j.upserted_count) + " kontak işlendi");
          mailToast(prefix + "içe aktarma tamam · " + doneStats + " · " + j.skipped_count + " geçersiz e-posta atlandı");
          mailSetImportDashboard({
            phase: "done",
            title: (fileLabel || j.filename || "Dosya") + " tamamlandı",
            sub: doneStats + " · " + fmtNum(j.skipped_count) + " geçersiz satır atlandı",
            showProgress: true,
            showDismiss: true
          });
          if (progBar) { progBar.style.width = "100%"; mailBulkResetBar(); }
          mailClearImportSession();
          mailLoadContactStats();
          mailLoadContacts();
          mailLoadTags();
          settle();
          return;
        }
        if (j.status === "cancelled") {
          mailToast(prefix + "iptal edildi · " + fmtNum(j.processed_rows) + " satır işlenmişti");
          mailSetImportDashboard({
            phase: "cancelled",
            title: (fileLabel || j.filename || "Dosya") + " iptal edildi",
            sub: fmtNum(j.processed_rows) + " satır işlenmişti.",
            showProgress: true,
            showDismiss: true
          });
          mailClearImportSession();
          mailLoadContactStats();
          mailLoadContacts();
          mailLoadTags();
          settle();
          return;
        }
        if (j.status === "error") {
          if (!mailWasImportJobHandled(jobId)) {
            mailBulkSetError(j.error || "bilinmeyen hata", fileLabel || j.filename, jobId);
            mailToast(prefix + "içe aktarma hata verdi: " + (j.error || "bilinmeyen hata"));
          }
          settle();
          return;
        }
        mailImportPollTimer = setTimeout(poll, 2000);
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
          '<button type="button" class="btn btn-sm mail-view-tpl" data-id="' + t.id + '">Görüntüle</button> ' +
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

  function textToPreviewHtml(text) {
    if (!text || !text.trim()) return "";
    return text
      .replace(/\r\n/g, "\n").replace(/\r/g, "\n").trim()
      .split(/\n\n+/).map(function (block) {
        return "<p>" + block.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>\n") + "</p>";
      }).join("\n")
      .replace(/\{\{link:([^}]+)\}\}/g, function (_m, url) {
        return "{{link:" + url.replace(/&amp;/g, "&") + "}}";
      });
  }

  function substituteTplPlaceholders(html) {
    var s = html || "<p class='muted'>Önizleme boş</p>";
    function linkUrl(raw) {
      return String(raw || "").trim().replace(/^sc\s*:\s*/i, "");
    }
    // href="{{link:...}}" → sadece URL; aksi halde butonlar patlıyor
    s = s.replace(/href\s*=\s*(["'])\s*\{\{\s*link\s*:\s*([^}]+)\s*\}\}\s*\1/gi, function (_m, q, raw) {
      return "href=" + q + linkUrl(raw) + q;
    });
    s = s.replace(/\{\{name\}\}/g, "Ali")
      .replace(/\{\{email\}\}/g, "ali@ornek.com")
      .replace(/\{\{phone\}\}/g, "+90555…")
      .replace(/\{\{\s*link\s*:\s*([^}]+)\s*\}\}/gi, function (_m, raw) {
        var u = linkUrl(raw);
        return '<a href="' + u + '" style="color:#ffd53e;">' + u + "</a>";
      });
    return s;
  }

  function previewHtmlFromEditors() {
    var html = (document.getElementById("mail-tpl-html") || {}).value || "";
    var text = (document.getElementById("mail-tpl-text") || {}).value || "";
    if (!html.trim() && text.trim()) html = textToPreviewHtml(text);
    return substituteTplPlaceholders(html);
  }

  function previewHtmlFromTemplate(tpl) {
    if (!tpl) return "<p class='muted'>Şablon bulunamadı</p>";
    var html = (tpl.html_body || "").trim();
    var text = (tpl.text_body || "").trim();
    if (!html && text) html = textToPreviewHtml(text);
    return substituteTplPlaceholders(html);
  }

  function buildTplPreviewDoc(bodyHtml) {
    return "<!DOCTYPE html><html><head><meta charset='utf-8'>" +
      "<meta name='viewport' content='width=device-width, initial-scale=1.0'>" +
      "<style>" +
      "body{margin:0;padding:24px 12px;background:#0b1220;}" +
      ".mail-preview-shell{max-width:560px;margin:0 auto;}" +
      "img{max-width:100%;height:auto;display:block;}" +
      "a{color:inherit}</style></head><body>" +
      "<div class='mail-preview-shell'>" + bodyHtml + "</div></body></html>";
  }

  function refreshTplPreview() {
    var frame = document.getElementById("mail-tpl-preview");
    if (!frame) return;
    frame.srcdoc = buildTplPreviewDoc(previewHtmlFromEditors());
  }

  function openTplViewModal(tpl) {
    if (!tpl) return;
    var modal = document.getElementById("mail-tpl-view-modal");
    var frame = document.getElementById("mail-tpl-view-frame");
    var title = document.getElementById("mail-tpl-view-title");
    if (!modal || !frame) return;
    if (title) title.textContent = "Önizleme — " + (tpl.name || "Şablon");
    frame.srcdoc = buildTplPreviewDoc(previewHtmlFromTemplate(tpl));
    modal.classList.add("open");
  }

  function closeTplViewModal() {
    var modal = document.getElementById("mail-tpl-view-modal");
    if (modal) modal.classList.remove("open");
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
    window.addEventListener("beforeunload", function (e) {
      var sess = mailReadImportSession();
      if (mailImportBusy && sess && sess.phase === "upload") {
        e.preventDefault();
        e.returnValue = "";
      }
    });

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
          mailLoadContactStats();
          mailLoadContacts();
          mailLoadTags();
        });
      });
    }

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
        mailLoadContactStats();
        mailLoadContacts();
        mailLoadTags();
      });
    });
    var bulkForm = document.getElementById("mail-bulk-import-form");
    if (bulkForm) {
      mailUpdateBulkFormState();
      bulkForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var fileInput = document.getElementById("mail-bulk-file");
        var tagInput = document.getElementById("mail-bulk-tag");
        var files = fileInput && fileInput.files ? Array.prototype.slice.call(fileInput.files) : [];
        if (!files.length) { mailToast("Önce bir CSV veya XLSX dosyası seç"); return; }
        var tag = (tagInput.value || "").trim();
        var accepted = [];
        files.forEach(function (file) {
          var err = mailValidateImportFile(file);
          if (err) { mailToast(file.name + ": " + err + ", atlandı"); return; }
          accepted.push(file);
        });
        if (!accepted.length) return;
        accepted.forEach(function (file) { mailEnqueueImport(file, tag); });
        fileInput.value = "";
        tagInput.value = "";
      });
    }
    var pasteBox = document.getElementById("mail-paste-box");
    var pasteStatusEl = document.getElementById("mail-paste-status");
    function mailHandlePastedText(text) {
      var tag = (document.getElementById("mail-paste-tag") || {}).value || "";
      tag = tag.trim();
      var result = mailQueueTextAsFile(text, tag, "yapistirilan-liste");
      if (!pasteStatusEl) return;
      if (result.error) {
        pasteStatusEl.textContent = "Hata: " + result.error + " (algılanan " + fmtNum(result.count) + " e-posta işlenmedi)";
      } else if (!result.count) {
        pasteStatusEl.textContent = "Yapıştırılan içerikte e-posta bulunamadı.";
      } else {
        pasteStatusEl.textContent = fmtNum(result.count) + " e-posta algılandı, yükleme kuyruğuna eklendi.";
      }
    }
    if (pasteBox) {
      pasteBox.addEventListener("paste", function (e) {
        e.preventDefault();
        var text = (e.clipboardData || window.clipboardData).getData("text");
        pasteBox.value = "";
        mailHandlePastedText(text);
      });
    }
    bindClick("mail-paste-submit", function () {
      var text = pasteBox ? pasteBox.value : "";
      if (!text || !text.trim()) { mailToast("Önce bir şey yapıştır veya yaz"); return; }
      mailHandlePastedText(text);
      if (pasteBox) pasteBox.value = "";
    });
    bindClick("mail-bulk-cancel", function () {
      if (!mailImportCurrentJobId) return;
      mailApi("/api/mailing/contacts/import/cancel/" + mailImportCurrentJobId, { method: "POST" }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "İptal edilemedi");
          return;
        }
        mailToast("İptal isteği gönderildi, kısa süre içinde duracak…");
      });
    });
    bindClick("mail-import-dismiss", function () {
      if (mailImportCurrentJobId) mailDismissImportJob(mailImportCurrentJobId);
      var errBox = document.getElementById("mail-import-error-box");
      if (errBox) errBox.hidden = true;
      if (!mailImportBusy) {
        mailSetImportDashboard({ phase: "idle" });
        var progBox = document.getElementById("mail-bulk-progress");
        if (progBox) progBox.hidden = true;
        mailBulkResetBar();
        mailFetchImportHistoryOnly();
      } else {
        mailSetImportDashboard({
          phase: mailImportCurrentJobId ? "processing" : "uploading",
          title: "Yükleme sürüyor",
          sub: "Hata kutusu kapatıldı — işlem arka planda devam ediyor.",
          showProgress: true,
          showError: false
        });
      }
    });
    bindClick("mail-contacts-refresh", function () {
      mailLoadContactStats();
      mailLoadContacts();
    });
    var qEl = document.getElementById("mail-contact-q");
    if (qEl) qEl.addEventListener("input", debounce(mailLoadContacts, 300));
    var tagEl = document.getElementById("mail-contact-tag-filter");
    if (tagEl) tagEl.addEventListener("change", mailLoadContacts);

    document.addEventListener("click", function (e) {
      var delC = e.target.closest(".mail-del-contact");
      if (delC) {
        if (!confirm("Kontak silinsin mi?")) return;
        mailApi("/api/mailing/contacts/" + delC.getAttribute("data-id"), { method: "DELETE" })
          .then(function () { mailLoadContactStats(); mailLoadContacts(); });
        return;
      }
      var viewT = e.target.closest(".mail-view-tpl");
      if (viewT) {
        var vid = Number(viewT.getAttribute("data-id"));
        var vt = mailTemplates.find(function (x) { return x.id === vid; });
        if (vt) openTplViewModal(vt);
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
    bindClick("mail-tpl-view-close", closeTplViewModal);
    var viewModal = document.getElementById("mail-tpl-view-modal");
    if (viewModal) {
      viewModal.addEventListener("click", function (e) {
        if (e.target === viewModal) closeTplViewModal();
      });
    }
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

    function mailCampSelectionPayload() {
      var maxEl = document.getElementById("mail-camp-max");
      var maxVal = maxEl && maxEl.value ? Number(maxEl.value) : null;
      return {
        tag_filter: document.getElementById("mail-camp-tag").value.trim(),
        max_recipients: maxVal,
        exclude_previously_sent: document.getElementById("mail-camp-exclude-sent").checked
      };
    }

    var campForm = document.getElementById("mail-camp-form");
    if (campForm) {
      campForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = mailCampSelectionPayload();
        body.name = document.getElementById("mail-camp-name").value.trim();
        body.template_id = Number(document.getElementById("mail-camp-tpl").value);
        body.domain_id = Number(document.getElementById("mail-camp-domain").value);
        body.notes = document.getElementById("mail-camp-notes").value.trim();
        mailApi("/api/mailing/campaigns", { method: "POST", body: body }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Oluşturulamadı");
            return;
          }
          mailToast("Kampanya oluşturuldu · " + (res.data.campaign.recipient_count || 0) + " alıcı");
          campForm.reset();
          document.getElementById("mail-camp-exclude-sent").checked = true;
          var hint = document.getElementById("mail-camp-preview-hint");
          if (hint) hint.textContent = "";
          mailLoadCampaigns();
        });
      });
    }
    bindClick("mail-camp-preview", function () {
      var hint = document.getElementById("mail-camp-preview-hint");
      if (hint) hint.textContent = "Hesaplanıyor…";
      mailApi("/api/mailing/campaigns/select-preview", { method: "POST", body: mailCampSelectionPayload() })
        .then(function (res) {
          if (!hint) return;
          if (!res || !res.ok) { hint.textContent = "Hesaplanamadı"; return; }
          var total = res.data.matching_count || 0;
          var maxEl = document.getElementById("mail-camp-max");
          var maxVal = maxEl && maxEl.value ? Number(maxEl.value) : null;
          var willAttach = maxVal ? Math.min(maxVal, total) : total;
          hint.textContent = "Filtreye uyan: " + total + " kişi · bu kampanyaya eklenecek: " + willAttach + " kişi";
        });
    });
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

  // Sayfa yenilendiğinde sunucuda süren işleri panelde gösterir.
  function mailFetchImportHistoryOnly() {
    return mailApi("/api/mailing/contacts/import/jobs", { timeoutMs: 30000 }).then(function (res) {
      if (!res || !res.ok) return;
      var jobs = res.data.jobs || [];
      var hasHistory = mailRenderImportHistory(jobs);
      if (hasHistory) mailShowImportDashboard(true);
    });
  }

  function mailAttachToImportJob(job, fromResume) {
    if (!job || !job.id) return false;
    if (mailImportBusy && mailImportCurrentJobId) {
      if (mailImportCurrentJobId === job.id) return true;
      return false;
    }
    if (job.status === "error" || job.status === "cancelled" || job.status === "done") return false;
    mailImportBusy = true;
    mailImportCurrentJobId = job.id;
    var progBox = document.getElementById("mail-bulk-progress");
    var cancelBtn = document.getElementById("mail-bulk-cancel");
    mailShowImportDashboard(true);
    if (progBox) progBox.hidden = false;
    if (cancelBtn) cancelBtn.hidden = !(job.status === "pending" || job.status === "running" || job.status === "cancelling");
    mailUpdateBulkFormState();
    mailSaveImportSession({
      phase: "process",
      fileName: job.filename || "",
      jobId: job.id,
      tag: job.tag || ""
    });
    if (fromResume) {
      mailToast((job.filename || "Dosya") + ": devam eden yükleme bulundu, takip ediliyor…");
    }
    mailSetImportDashboard({
      phase: job.status === "running" ? "processing" : "pending",
      title: job.filename || "İçe aktarma",
      sub: "Sunucuda devam eden iş takip ediliyor — sayfa yenilense de burada kalır.",
      showProgress: true
    });
    mailPollImportJob(job.id, function () {
      mailImportBusy = false;
      mailImportCurrentJobId = null;
      mailUpdateBulkFormState();
      mailStartNextImport();
    }, job.filename || "");
    return true;
  }

  function mailRefreshImportStatus(opts) {
    opts = opts || {};
    if (mailImportBusy && !opts.force) return Promise.resolve(false);
    if (mailImportRefreshTimer) {
      clearTimeout(mailImportRefreshTimer);
      mailImportRefreshTimer = null;
    }
    return mailApi("/api/mailing/contacts/import/jobs", { timeoutMs: 30000 }).then(function (res) {
      if (!res || !res.ok) {
        var sess = mailReadImportSession();
        if (sess && sess.jobId && !mailImportBusy) {
          mailShowImportDashboard(true);
          switchMailTab("crm");
          mailAttachToImportJob({ id: sess.jobId, filename: sess.fileName, status: "running" }, true);
          return true;
        }
        if (sess && sess.phase === "upload" && !mailImportBusy) {
          mailShowImportDashboard(true);
          switchMailTab("crm");
          var progHint = sess.pct ? ("Son ilerleme: %" + sess.pct + " · ") : "";
          mailSetImportDashboard({
            phase: "error",
            title: sess.fileName || "Yarım kalan yükleme",
            sub: progHint + "Tarayıcı yenilendi — aktarım kesildi.",
            showError: true,
            errorText: "Aynı dosyayı tekrar seç. 20MB üstü CSV otomatik ~10MB parçalara bölünerek yüklenir.",
            showDismiss: true
          });
        }
        return false;
      }
      var jobs = res.data.jobs || [];
      var hasHistory = mailRenderImportHistory(jobs);
      var active = jobs.filter(function (j) {
        return j.status === "pending" || j.status === "running" || j.status === "cancelling";
      });
      if (active.length && !mailImportBusy) {
        active.sort(function (a, b) { return (b.id || 0) - (a.id || 0); });
        var job = active[0];
        switchMailTab("crm");
        mailShowImportDashboard(true);
        mailAttachToImportJob(job, true);
        return true;
      }
      if (hasHistory) {
        mailShowImportDashboard(true);
        if (!mailImportBusy) {
          var sessUp = mailReadImportSession();
          if (sessUp && sessUp.phase === "upload") {
            var progHint = sessUp.pct ? ("Son ilerleme: %" + sessUp.pct + " · ") : "";
            mailSetImportDashboard({
              phase: "error",
              title: sessUp.fileName || "Yarım kalan yükleme",
              sub: progHint + "Dosyayı tekrar seç — büyük CSV parçalı yüklenecek.",
              showError: true,
              errorText: "Yükleme tamamlanmadan sayfa kapatıldı veya bağlantı kesildi.",
              showDismiss: true
            });
          } else {
            mailSetImportDashboard({
              phase: "idle",
              title: "Yükleme geçmişi",
              sub: "Aktif iş yok. Devam eden veya bitmiş yüklemeler aşağıda listelenir.",
              showProgress: false,
              showDismiss: true
            });
          }
        }
      }
      return false;
    });
  }

  function mailResumePendingImports() {
    return mailRefreshImportStatus({ force: true });
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
      mailRefreshImportStatus({ force: true }).then(function (hasActive) {
        var tab = "dashboard";
        try { tab = localStorage.getItem(MAIL_TAB_STORAGE_KEY) || "dashboard"; } catch (e) { /* ignore */ }
        if (hasActive || mailImportBusy) tab = "crm";
        switchMailTab(tab);
      });
    },
    setPermissions: function (perms) {
      mailPerms = perms || [];
    },
    refresh: function () {
      mailLoadTab(mailActiveTab);
    }
  };
})();
