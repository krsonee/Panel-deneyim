(function () {
  "use strict";

  var mailActiveTab = "dashboard";
  var mailPerms = [];
  var mailTemplates = [];
  var mailDomains = [];
  var mailTags = [];
  var mailTagCounts = [];
  var mailCampPollTimer = null;
  var mailLoaded = false;
  var mailTplMode = "simple";
  var mailImportQueue = [];
  var mailImportBusy = false;
  var mailImportCurrentJobId = null;
  var MAIL_IMPORT_SESSION_KEY = "makro_mail_import_v1";
  var MAIL_IMPORT_DISMISSED_KEY = "makro_mail_import_dismissed_v1";
  var MAIL_TAB_STORAGE_KEY = "makro_mail_tab";
  var mailImportPollTimer = null;
  var mailScrubPollTimer = null;
  var mailScrubJobId = null;
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
    relations: ["mailing.relations", "mailing.crm"],
    smartico: "mailing.crm",
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
    if (Array.isArray(key)) {
      for (var i = 0; i < key.length; i++) {
        if (mailPerms.indexOf(key[i]) >= 0) return true;
      }
      return false;
    }
    return mailPerms.indexOf(key) >= 0;
  }

  function mailFirstAllowedTab() {
    var order = ["dashboard", "relations", "smartico", "crm", "templates", "campaigns", "ivr", "reports", "settings"];
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
    fetchOpts.headers = Object.assign({}, fetchOpts.headers || {});
    if (window.MAIL_STANDALONE && window.MAIL_TENANT_ID) {
      fetchOpts.headers["X-Tenant-Id"] = String(window.MAIL_TENANT_ID);
    }
    if (fetchOpts.body && typeof fetchOpts.body === "object" && !(fetchOpts.body instanceof FormData)) {
      fetchOpts.headers["Content-Type"] = "application/json";
      fetchOpts.body = JSON.stringify(fetchOpts.body);
    }
    if (controller) fetchOpts.signal = controller.signal;
    fetchOpts.credentials = fetchOpts.credentials || "same-origin";
    return fetch(path, fetchOpts).then(function (r) {
      if (timer) clearTimeout(timer);
      if (r.status === 401) {
        location.href = window.MAIL_STANDALONE ? "/login" : "/admin/login";
        return null;
      }
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
    if (/\.(xlsx|xlsm)$/.test(lowerName) && file.size > MAIL_AUTO_SPLIT_BYTES) {
      return "Excel " + fmtBytes(file.size) + " çok büyük — Render timeout yapar. "
        + "Tekrarsız Mail 20m-merged.csv dosyasını kullan (parçalı yüklenir).";
    }
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
    if (cancelBtn) { cancelBtn.hidden = false; cancelBtn.textContent = "Yüklemeyi iptal"; }
    mailSetImportDashboard({
      phase: "uploading",
      title: file.name,
      sub: (/\.(xlsx|xlsm)$/i.test(file.name) && file.size > MAIL_AUTO_SPLIT_BYTES)
        ? "UYARI: Büyük Excel Render'da takılır — Tekrarsız Mail 20m-merged.csv kullan."
        : "Dosya sunucuya yükleniyor — büyük dosyalarda bu adım uzun sürebilir, sayfayı kapatma.",
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
    else if (tab === "relations") mailLoadRelations();
    else if (tab === "smartico") mailLoadSmarticoPlayers(false);
    else if (tab === "crm") {
      // Mail Rehber — açılışta refresh ile etiket sayıları canlı dolsun
      mailLoadContacts();
      mailLoadTags();
      mailLoadContactStats({ refresh: true });
    }
    else if (tab === "templates") mailLoadTemplates();
    else if (tab === "campaigns") {
      mailLoadTags().then(mailFillCampTagSelect);
      mailLoadSelects().then(mailLoadCampaigns);
    }
    else if (tab === "ivr") { mailLoadSelects().then(mailLoadIvr); }
    else if (tab === "reports") mailLoadReports();
    else if (tab === "settings") mailLoadSettings();
  }

  var mailScSearchTimer = null;
  var mailScLastRows = [];

  function mailFmtMoney(n, cur) {
    var v = Number(n || 0);
    var s = v.toLocaleString("tr-TR", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
    return cur ? (s + " " + cur) : s;
  }

  function mailLoadSmarticoPlayers(force) {
    var status = document.getElementById("mail-sc-status");
    var tbody = document.getElementById("mail-sc-table");
    var period = ((document.getElementById("mail-sc-period") || {}).value) || "30days";
    var q = ((document.getElementById("mail-sc-q") || {}).value || "").trim();
    var matched = !!(document.getElementById("mail-sc-matched") || {}).checked;
    var ftd = !!(document.getElementById("mail-sc-ftd") || {}).checked;
    var url = "/api/mailing/crm/smartico-players?period=" + encodeURIComponent(period);
    if (force) url += "&force=1";
    if (q) url += "&q=" + encodeURIComponent(q);
    if (matched) url += "&matched=1";
    if (ftd) url += "&ftd=1";
    if (status) status.textContent = "Smartico’dan çekiliyor…";
    if (tbody) tbody.innerHTML = '<tr><td colspan="11" class="empty">Yükleniyor…</td></tr>';
    return mailApi(url, { timeoutMs: 60000 }).then(function (res) {
      if (!res || !res.ok) {
        var err = (res && res.data && (res.data.message || res.data.error)) || "Smartico üyeleri alınamadı";
        if (status) status.textContent = err;
        if (tbody) tbody.innerHTML = '<tr><td colspan="11" class="empty">' + esc(err) + "</td></tr>";
        setText("mail-sc-kpi-players", "—");
        setText("mail-sc-kpi-matched", "—");
        setText("mail-sc-kpi-ftd", "—");
        setText("mail-sc-kpi-deposit", "—");
        setText("mail-sc-kpi-withdraw", "—");
        setText("mail-sc-kpi-bonus", "—");
        return;
      }
      var d = res.data || {};
      var rows = d.rows || [];
      var cur = d.currency || "";
      mailScLastRows = rows;
      var ftdSum = 0, dep = 0, wit = 0, bon = 0, matchedN = 0;
      rows.forEach(function (r) {
        ftdSum += Number(r.ftd_count || 0);
        dep += Number(r.deposit_total || 0);
        wit += Number(r.withdrawal_total || 0);
        bon += Number(r.bonus_total || 0);
        if (r.matched) matchedN += 1;
      });
      setText("mail-sc-kpi-players", fmtNum(rows.length));
      setText("mail-sc-kpi-matched", fmtNum(matchedN));
      setText("mail-sc-kpi-ftd", fmtNum(ftdSum));
      setText("mail-sc-kpi-deposit", mailFmtMoney(dep, cur));
      setText("mail-sc-kpi-withdraw", mailFmtMoney(wit, cur));
      setText("mail-sc-kpi-bonus", mailFmtMoney(bon, cur));
      var src = d.source === "cache" ? "önbellek" : "canlı";
      if (status) {
        status.textContent = rows.length + " satır · aff #" + (d.affiliate_id || "?") +
          " · " + src + (d.group_by ? (" · group " + d.group_by) : "") +
          (d.error ? (" · uyarı: " + d.error) : "");
      }
      if (!tbody) return;
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="11" class="empty">Bu dönemde üye yok — affiliate ID / API anahtarını kontrol et</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (r) {
        var tags = (r.tags || []).slice(0, 4).map(function (t) {
          return '<span class="tag">' + esc(t) + "</span>";
        }).join(" ");
        var userCell = r.username
          ? ("<strong>" + esc(r.username) + "</strong>")
          : '<span class="muted">—</span>';
        var emailCell = r.email
          ? esc(r.email)
          : (r.matched ? '<span class="muted">—</span>' : '<span class="muted">eşleşmedi</span>');
        var cid = r.contact_id != null ? r.contact_id : (r.subid || "—");
        return "<tr>" +
          "<td>" + userCell + "</td>" +
          "<td>" + emailCell + "</td>" +
          "<td>" + esc(r.first_name || "") + "</td>" +
          "<td>" + esc(r.last_name || "") + "</td>" +
          "<td><span class=\"muted\">#" + esc(String(cid)) + "</span></td>" +
          "<td>" + ((r.ftd_count || 0) > 0
            ? ('<span class="tag" style="background:rgba(34,197,94,0.18);color:#86efac;">' + fmtNum(r.ftd_count) + "</span>")
            : '<span class="muted">0</span>') + "</td>" +
          "<td>" + mailFmtMoney(r.ftd_total, cur) + "</td>" +
          "<td><strong>" + mailFmtMoney(r.deposit_total, cur) + "</strong>" +
            (r.deposit_count ? (' <span class="muted">(' + fmtNum(r.deposit_count) + ")</span>") : "") + "</td>" +
          "<td>" + mailFmtMoney(r.withdrawal_total, cur) + "</td>" +
          "<td>" + mailFmtMoney(r.bonus_total, cur) + "</td>" +
          "<td>" + (tags || '<span class="muted">—</span>') + "</td>" +
          "</tr>";
      }).join("");
    });
  }

  var mailRelContactId = null;
  var mailRelLabels = {};

  function mailLoadRelations() {
    mailApi("/api/mailing/relations/overview").then(function (res) {
      if (!res || !res.ok) return;
      var d = res.data || {};
      mailRelLabels = d.lifecycle_labels || {};
      setText("mail-rel-kpi-hot", fmtNum(d.hot_contacts));
      setText("mail-rel-kpi-tasks", fmtNum(d.open_tasks));
      setText("mail-rel-kpi-overdue", fmtNum(d.overdue_tasks));
      setText("mail-rel-kpi-notes", fmtNum(d.notes_total));
      var chips = document.getElementById("mail-rel-life-chips");
      var filter = document.getElementById("mail-rel-life-filter");
      var curFilter = filter ? filter.value : "";
      if (chips) {
        chips.innerHTML = (d.by_lifecycle || []).map(function (x) {
          return '<button type="button" class="btn btn-sm mail-rel-life-chip" data-life="' + esc(x.key) + '">' +
            esc(x.label) + " · " + fmtNum(x.count) + "</button>";
        }).join("");
      }
      if (filter) {
        filter.innerHTML = '<option value="">Tümü</option>' + (d.by_lifecycle || []).map(function (x) {
          return '<option value="' + esc(x.key) + '">' + esc(x.label) + "</option>";
        }).join("");
        filter.value = curFilter;
      }
      var lifeSel = document.getElementById("mail-rel-lifecycle");
      if (lifeSel) {
        lifeSel.innerHTML = (d.by_lifecycle || []).map(function (x) {
          return '<option value="' + esc(x.key) + '">' + esc(x.label) + "</option>";
        }).join("");
      }
    });
    mailLoadRelationsPipeline();
  }

  function mailLoadRelationsPipeline() {
    var q = (document.getElementById("mail-rel-q") || {}).value || "";
    var life = (document.getElementById("mail-rel-life-filter") || {}).value || "";
    var url = "/api/mailing/relations/pipeline?limit=100";
    if (q) url += "&q=" + encodeURIComponent(q);
    if (life) url += "&lifecycle=" + encodeURIComponent(life);
    return mailApi(url).then(function (res) {
      var tbody = document.getElementById("mail-rel-table");
      if (!tbody) return;
      if (!res || !res.ok) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.contacts || [];
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Kayıt yok — skorları yenile veya rehberden kontak ekle</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (c) {
        return "<tr>" +
          "<td><strong>" + fmtNum(c.crm_score) + "</strong></td>" +
          "<td>" + esc(c.email) + (c.name ? ('<br><span class="muted">' + esc(c.name) + "</span>") : "") + "</td>" +
          "<td>" + esc(c.lifecycle_label || c.lifecycle) + "</td>" +
          "<td>" + esc(c.crm_owner || "—") + "</td>" +
          "<td>" + esc(fmtTime(c.last_touch_at) || "—") + "</td>" +
          '<td><button type="button" class="btn btn-sm mail-rel-open" data-id="' + c.id + '">Profil</button></td>' +
          "</tr>";
      }).join("");
    });
  }

  function mailOpenRelProfile(id) {
    mailRelContactId = id;
    var card = document.getElementById("mail-rel-profile-card");
    if (card) card.hidden = false;
    mailApi("/api/mailing/relations/contacts/" + id + "?refresh=1", { timeoutMs: 30000 }).then(function (res) {
      if (!res || !res.ok) {
        mailToast((res && res.data && res.data.error) || "Profil yüklenemedi");
        return;
      }
      mailRenderRelProfile(res.data.contact);
    });
  }

  function mailRenderRelProfile(c) {
    if (!c) return;
    setText("mail-rel-profile-title", (c.name || c.email || "Profil") + " · #" + c.id);
    var life = document.getElementById("mail-rel-lifecycle");
    if (life) life.value = c.lifecycle || "lead";
    var owner = document.getElementById("mail-rel-owner");
    if (owner) owner.value = c.crm_owner || "";
    var eng = c.engagement || {};
    setText("mail-rel-eng", "Skor " + fmtNum(c.crm_score) + " · gönderim " + fmtNum(eng.sends) + " · açılma " + fmtNum(eng.opens) + " · tıklama " + fmtNum(eng.clicks));
    var notesEl = document.getElementById("mail-rel-notes");
    if (notesEl) {
      notesEl.innerHTML = (c.notes || []).length
        ? c.notes.map(function (n) {
          return '<div style="padding:0.45rem 0.55rem;border:1px solid rgba(148,163,184,0.2);border-radius:8px;">' +
            '<div class="muted" style="font-size:0.72rem;">' + esc(fmtTime(n.created_at)) + " · " + esc(n.author || "") + "</div>" +
            "<div>" + esc(n.body) + "</div></div>";
        }).join("")
        : "<span class=\"muted\">Henüz not yok</span>";
    }
    var tasksEl = document.getElementById("mail-rel-tasks");
    if (tasksEl) {
      tasksEl.innerHTML = (c.tasks || []).length
        ? c.tasks.map(function (t) {
          var done = t.status === "done";
          return '<div style="padding:0.45rem 0.55rem;border:1px solid rgba(148,163,184,0.2);border-radius:8px;display:flex;justify-content:space-between;gap:0.5rem;align-items:center;">' +
            "<div><div>" + (done ? "<s>" : "") + esc(t.title) + (done ? "</s>" : "") + "</div>" +
            '<div class="muted" style="font-size:0.72rem;">' + esc(t.status) + (t.due_at ? (" · vade " + esc(fmtTime(t.due_at))) : "") + "</div></div>" +
            (done ? "" : '<button type="button" class="btn btn-sm mail-rel-task-done" data-id="' + t.id + '">Tamam</button>') +
            "</div>";
        }).join("")
        : "<span class=\"muted\">Açık görev yok</span>";
    }
    var tl = document.getElementById("mail-rel-timeline");
    if (tl) {
      tl.innerHTML = (c.timeline || []).length
        ? c.timeline.map(function (e) {
          return '<div style="padding:0.4rem 0;border-bottom:1px solid rgba(148,163,184,0.12);">' +
            '<span class="muted">' + esc(fmtTime(e.at)) + "</span> · <strong>" + esc(e.title) + "</strong>" +
            (e.detail ? (" — " + esc(e.detail)) : "") + "</div>";
        }).join("")
        : "<span class=\"muted\">Henüz aktivite yok</span>";
    }
  }

  function mailLoadDashboard() {
    return mailApi("/api/mailing/dashboard").then(function (res) {
      if (!res || !res.ok) return;
      var k = res.data.kpi || {};
      setText("mail-kpi-contacts", fmtNum(k.contacts));
      var sub = fmtNum(k.active_contacts || 0) + " rehber";
      if (k.contacts_approx) sub += " · approx";
      if (k.suppressed) sub += " · sup " + fmtNum(k.suppressed);
      setText("mail-kpi-contacts-sub", sub);
      setText("mail-kpi-campaigns", fmtNum(k.campaigns));
      setText("mail-kpi-sent", fmtNum(k.sends_delivered));
      setText("mail-kpi-sent-sub", "kuyruk " + fmtNum(k.sends_queued || 0) + " · fail " + fmtNum(k.sends_failed || 0));
      setText("mail-kpi-ivr", fmtNum(k.ivr_events));
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

  // ── Mail Rehber ───────────────────────────────────────────
  var MAIL_SELECTED_KEY = "makro_mail_camp_selected_ids";

  function mailReadCampSelectedIds() {
    try {
      var raw = sessionStorage.getItem(MAIL_SELECTED_KEY) || "[]";
      var arr = JSON.parse(raw);
      if (!Array.isArray(arr)) return [];
      return arr.map(function (x) { return Number(x); }).filter(Boolean);
    } catch (e) {
      return [];
    }
  }

  function mailWriteCampSelectedIds(ids) {
    try {
      sessionStorage.setItem(MAIL_SELECTED_KEY, JSON.stringify(ids || []));
    } catch (e) { /* ignore */ }
    mailUpdateCampSelectedHint();
  }

  function mailUpdateCampSelectedHint() {
    var hint = document.getElementById("mail-camp-selected-hint");
    if (!hint) return;
    var ids = mailReadCampSelectedIds();
    hint.textContent = ids.length
      ? (fmtNum(ids.length) + " kontak kampanya için hazır (Mail Rehber seçimi).")
      : "Mail Rehber’de kişi seçip «Seçilileri kampanyaya» de — veya burada bekleyen seçim yok.";
  }

  function mailCampRecipientMode() {
    var el = document.querySelector('input[name="mail-camp-recipient-mode"]:checked');
    return (el && el.value) || "tag";
  }

  function mailSyncCampRecipientModeUI() {
    var mode = mailCampRecipientMode();
    var tagBox = document.getElementById("mail-camp-mode-tag");
    var selBox = document.getElementById("mail-camp-mode-selected");
    var manBox = document.getElementById("mail-camp-mode-manual");
    if (tagBox) tagBox.hidden = mode !== "tag";
    if (selBox) selBox.hidden = mode !== "selected";
    if (manBox) manBox.hidden = mode !== "manual";
    mailUpdateCampSelectedHint();
  }

  function mailLoadTags() {
    return mailApi("/api/mailing/tags").then(function (res) {
      if (!res || !res.ok) return;
      mailTags = res.data.tags || [];
      mailFillAllTagSelects();
    });
  }

  function mailTagNameList() {
    var names = {};
    (mailTags || []).forEach(function (t) { if (t && t.name) names[t.name] = true; });
    (mailTagCounts || []).forEach(function (t) { if (t && t.name) names[t.name] = true; });
    return Object.keys(names).sort(function (a, b) { return a.localeCompare(b, "tr"); });
  }

  function mailFillAllTagSelects() {
    var countMap = {};
    (mailTagCounts || []).forEach(function (t) { countMap[t.name] = t.count; });
    var list = mailTagNameList();
    var optionsWithEmpty = function (emptyLabel) {
      return '<option value="">' + esc(emptyLabel || "Etiket yok") + "</option>" +
        list.map(function (name) {
          var c = countMap[name];
          var label = c == null ? name : (name + " (" + fmtNum(c) + ")");
          return '<option value="' + esc(name) + '">' + esc(label) + "</option>";
        }).join("");
    };
    document.querySelectorAll("select.mail-tag-select").forEach(function (sel) {
      var cur = sel.value;
      var isFilter = sel.id === "mail-contact-tag-filter";
      var isScrub = sel.id === "mail-scrub-tag";
      var emptyLabel = isFilter || isScrub ? "Tüm etiketler" : "Etiket yok";
      if (isScrub) emptyLabel = "Tüm kontaklar";
      sel.innerHTML = optionsWithEmpty(emptyLabel);
      if (cur) sel.value = cur;
    });
    mailRenderTagPickLists();
    mailFillCampTagSelect();
    mailRenderTagManageList();
  }

  function mailGetMoveFromTag() {
    return ((document.getElementById("mail-tag-move-from") || {}).value || "").trim();
  }

  function mailGetMoveToTag() {
    var typed = ((document.getElementById("mail-tag-move-to-new") || {}).value || "").trim();
    if (typed) return typed;
    return ((document.getElementById("mail-tag-move-to") || {}).value || "").trim();
  }

  function mailGetMoveScope() {
    var checked = document.querySelector('input[name="mail-tag-scope"]:checked');
    return (checked && checked.value) || "selected";
  }

  function mailUpdateMoveSummary() {
    var sum = document.getElementById("mail-tag-move-summary");
    var fromLabel = document.getElementById("mail-tag-from-label");
    var toLabel = document.getElementById("mail-tag-to-label");
    var fromTag = mailGetMoveFromTag();
    var toTag = mailGetMoveToTag();
    var scope = mailGetMoveScope();
    var selectedCount = document.querySelectorAll(".mail-contact-check:checked").length;
    if (fromLabel) fromLabel.textContent = fromTag || "—";
    if (toLabel) toLabel.textContent = toTag || "—";
    if (!sum) return;
    var who = scope === "all"
      ? (fromTag ? ("«" + fromTag + "» içindeki herkes") : "kaynak etiket seçilmedi")
      : (selectedCount ? (selectedCount + " seçili kişi") : "tabloda henüz kimse işaretli değil");
    if (!fromTag && scope === "all") {
      sum.textContent = "Hazır değil — «Kaynak etiketteki herkes» için soldan kaynak seç.";
      return;
    }
    if (scope === "selected" && !selectedCount) {
      sum.textContent = "Hazır değil — alttaki tabloda kişi işaretle (veya kapsamı «herkes» yap).";
      return;
    }
    if (!toTag && !fromTag) {
      sum.textContent = "Hazır değil — soldan kaynak, sağdan hedef seç.";
      return;
    }
    sum.textContent = "Özet: " + who +
      (fromTag ? (" · kaynak «" + fromTag + "»") : "") +
      (toTag ? (" · hedef «" + toTag + "»") : " · hedef yok");
  }

  function mailRenderTagPickLists() {
    var fromBox = document.getElementById("mail-tag-from-list");
    var toBox = document.getElementById("mail-tag-to-list");
    if (!fromBox && !toBox) return;
    var countMap = {};
    (mailTagCounts || []).forEach(function (t) { countMap[t.name] = t.count; });
    var list = mailTagNameList();
    var fromCur = mailGetMoveFromTag();
    var toCur = mailGetMoveToTag();
    var emptyHtml = '<span class="muted" style="padding:0.4rem;">Önce etiket oluştur</span>';
    function itemHtml(name, active) {
      var c = countMap[name];
      var count = c == null ? "—" : fmtNum(c);
      return '<button type="button" class="mail-tag-pick-item' + (active ? " is-active" : "") +
        '" data-tag="' + esc(name) + '"><span>' + esc(name) +
        '</span><span class="mail-tag-pick-count">' + count + "</span></button>";
    }
    if (fromBox) {
      fromBox.innerHTML = list.length
        ? list.map(function (n) { return itemHtml(n, fromCur === n); }).join("")
        : emptyHtml;
    }
    if (toBox) {
      toBox.innerHTML = list.length
        ? list.map(function (n) { return itemHtml(n, !((document.getElementById("mail-tag-move-to-new") || {}).value || "").trim() && toCur === n); }).join("")
        : emptyHtml;
    }
    mailUpdateMoveSummary();
  }

  function mailRenderTagManageList() {
    var box = document.getElementById("mail-tag-manage-list");
    if (!box) return;
    var countMap = {};
    (mailTagCounts || []).forEach(function (t) { countMap[t.name] = t.count; });
    var list = mailTagNameList();
    if (!list.length) {
      box.innerHTML = '<span class="hint">Henüz etiket yok</span>';
      return;
    }
    box.innerHTML = list.map(function (name) {
      var c = countMap[name];
      if (c == null) c = 0;
      var empty = Number(c) === 0;
      return '<span class="mail-tag-manage-item' + (empty ? " is-empty" : "") + '">' +
        '<span>' + esc(name) + "</span>" +
        '<span class="mail-tag-manage-count">' + fmtNum(c) + "</span>" +
        '<button type="button" class="mail-tag-delete-btn" data-tag="' + esc(name) + '" data-count="' + c + '" title="Etiketi sil">×</button>' +
        "</span>";
    }).join("");
  }

  function mailRenderTagFilterOptions() {
    mailFillAllTagSelects();
  }

  function mailRenderTagStats(byTag, opts) {
    opts = opts || {};
    mailTagCounts = byTag || [];
    var pending = {};
    (opts.pendingRecount || []).forEach(function (n) { pending[n] = true; });
    var wrap = document.getElementById("mail-crm-tag-stats");
    var list = document.getElementById("mail-crm-tag-stats-list");
    var kpiGrid = document.getElementById("mail-crm-tag-kpi-grid");
    var filterEl = document.getElementById("mail-contact-tag-filter");
    var keepFilter = filterEl ? filterEl.value : "";
    mailRenderTagFilterOptions();
    if (filterEl && keepFilter) filterEl.value = keepFilter;
    var active = (document.getElementById("mail-contact-tag-filter") || {}).value || "";

    if (kpiGrid) {
      if (!mailTagCounts.length) {
        kpiGrid.hidden = true;
        kpiGrid.innerHTML = "";
      } else {
        kpiGrid.hidden = false;
        kpiGrid.innerHTML = mailTagCounts.map(function (t, idx) {
          var isActive = active && active === t.name;
          var isPending = !!pending[t.name] && !(t.count > 0);
          var countLabel = isPending ? "…" : fmtNum(t.count);
          return '<button type="button" class="mail-tag-kpi' +
            (isActive ? " is-active" : "") +
            (isPending ? " is-pending" : "") +
            '" data-accent="' + (idx % 6) +
            '" data-mail-tag-filter="' + esc(t.name) +
            '" title="Bu etikete göre filtrele">' +
            '<div class="mail-tag-kpi-val">' + countLabel + "</div>" +
            '<div class="mail-tag-kpi-lbl">' + esc(t.name) + "</div>" +
            '<div class="mail-tag-kpi-sub">kayıtlı mail</div>' +
            "</button>";
        }).join("");
      }
    }

    if (!wrap || !list) return;
    if (!mailTagCounts.length) {
      wrap.hidden = true;
      list.innerHTML = "";
      return;
    }
    wrap.hidden = false;
    list.innerHTML = mailTagCounts.map(function (t) {
      var isActive = active && active === t.name;
      var isPending = !!pending[t.name] && !(t.count > 0);
      return '<button type="button" class="mail-tag-stat' + (isActive ? " is-active" : "") + '" data-mail-tag-filter="' + esc(t.name) + '" title="Bu etikete göre filtrele">' +
        '<span class="mail-tag-stat-name">' + esc(t.name) + "</span>" +
        '<span class="mail-tag-stat-count">' + (isPending ? "…" : fmtNum(t.count)) + "</span>" +
        "</button>";
    }).join("");
  }

  var mailTagRecountTimer = null;
  function mailLoadContactStats(opts) {
    opts = opts || {};
    var parts = [];
    if (opts.refresh) parts.push("refresh=1");
    if (opts.syncTags) parts.push("sync_tags=1");
    var qs = parts.length ? ("?" + parts.join("&")) : "";
    var timeout = opts.refresh ? 300000 : 20000;
    setText("mail-crm-stat-total", "…");
    return mailApi("/api/mailing/contacts/stats" + qs, { timeoutMs: timeout }).then(function (res) {
      if (!res || !res.ok) {
        setText("mail-crm-stat-total", "—");
        return;
      }
      var s = res.data || {};
      setText("mail-crm-stat-total", fmtNum(s.total));
      setText("mail-crm-stat-mailed", fmtNum(s.mailed));
      setText("mail-crm-stat-never", fmtNum(s.never_mailed));
      mailRenderTagStats(s.by_tag || [], { pendingRecount: [] });
      mailFillCampTagSelect();
      // Tag listesini her stats çağrısında yeniden çekme — gereksiz DB yükü
      if (opts.refresh || opts.syncTags) mailLoadTags();
      // Otomatik recount poll kaldırıldı: milyonlarca satırda paneli kitler.
      // Etiket sayılarını yenilemek için Mail Rehber "Yenile" (refresh=1) kullanılır.
      if (mailTagRecountTimer) { clearTimeout(mailTagRecountTimer); mailTagRecountTimer = null; }
    });
  }

  var mailContactsPageTotal = 0;
  var mailContactsFilterTotal = 0;

  function mailUpdateContactSelectionCount() {
    var selected = document.querySelectorAll(".mail-contact-check:checked").length;
    var page = document.querySelectorAll(".mail-contact-check").length;
    setText("mail-contacts-selected", fmtNum(selected));
    setText("mail-contacts-page", fmtNum(page || mailContactsPageTotal));
    setText("mail-contacts-total", fmtNum(mailContactsFilterTotal));
    mailUpdateMoveSummary();
  }

  function mailLoadContacts() {
    var q = (document.getElementById("mail-contact-q") || {}).value || "";
    var tag = (document.getElementById("mail-contact-tag-filter") || {}).value || "";
    var url = "/api/mailing/contacts?limit=500";
    if (q) url += "&q=" + encodeURIComponent(q);
    if (tag) url += "&tag=" + encodeURIComponent(tag);
    // 3M + etiket filtresi: COUNT kaldırıldı ama SELECT yine sürebilir
    return mailApi(url, { timeoutMs: 60000 }).then(function (res) {
      var tbody = document.getElementById("mail-contacts-table");
      if (!tbody) return;
      if (!res || !res.ok) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Yüklenemedi</td></tr>';
        mailContactsPageTotal = 0;
        mailContactsFilterTotal = 0;
        mailUpdateContactSelectionCount();
        return;
      }
      var rows = res.data.contacts || [];
      mailContactsPageTotal = rows.length;
      mailContactsFilterTotal = Number(res.data.total != null ? res.data.total : rows.length) || 0;
      // Sayfada görünen etiketleri select listesine ekle (registry gecikmesi)
      var harvested = false;
      rows.forEach(function (c) {
        (c.tags || []).forEach(function (t) {
          if (!t) return;
          var found = (mailTagCounts || []).some(function (x) { return x && x.name === t; });
          if (!found) {
            mailTagCounts = (mailTagCounts || []).concat([{ name: t, count: null }]);
            harvested = true;
          }
        });
      });
      if (harvested) mailFillAllTagSelects();
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="empty">Kontak yok</td></tr>';
        mailUpdateContactSelectionCount();
        return;
      }
      tbody.innerHTML = rows.map(function (c) {
        var tags = (c.tags || []).map(function (t) {
          return '<span class="acc-chip"><span class="acc-chip-text">' + esc(t) + "</span></span>";
        }).join(" ");
        var vs = (c.verify_status || "").trim();
        var vd = (c.verify_detail || "").trim();
        var vLabel = vs ? esc(vs) : "—";
        if (vd) vLabel = '<span title="' + esc(vd) + '">' + vLabel + "</span>";
        return "<tr>" +
          '<td><input type="checkbox" class="mail-contact-check" value="' + c.id + '"></td>' +
          "<td>" + esc(c.email) + (c.unsubscribed ? ' <span class="muted">(unsub)</span>' : "") + "</td>" +
          "<td>" + esc(c.name) + "</td>" +
          "<td>" + vLabel + "</td>" +
          "<td>" + (tags || "—") + "</td>" +
          "<td>" + esc(c.source) + "</td>" +
          '<td style="white-space:nowrap;">' +
            '<button type="button" class="btn btn-sm mail-edit-contact" data-id="' + c.id + '">Düzenle</button> ' +
            '<button type="button" class="btn btn-sm mail-del-contact" data-id="' + c.id + '">Sil</button>' +
          "</td></tr>";
      }).join("");
      mailUpdateContactSelectionCount();
    });
  }

  function mailResetContactForm() {
    var form = document.getElementById("mail-contact-form");
    if (form) form.reset();
    var idEl = document.getElementById("mail-c-id");
    if (idEl) idEl.value = "";
    setText("mail-contact-form-title", "Kontak ekle");
    var sub = document.getElementById("mail-contact-form-sub");
    if (sub) sub.textContent = "Tek tek ekle / düzenle";
    var submit = document.getElementById("mail-c-submit");
    if (submit) submit.textContent = "Ekle";
    var cancel = document.getElementById("mail-c-cancel");
    if (cancel) cancel.hidden = true;
    var life = document.getElementById("mail-c-lifecycle");
    if (life) life.value = "lead";
  }

  function mailCollectContactFormBody() {
    var tagSelect = ((document.getElementById("mail-c-tags") || {}).value || "").trim();
    var tagText = ((document.getElementById("mail-c-tags-text") || {}).value || "").trim();
    var tags = [];
    if (tagText) {
      tagText.split(/[,;]+/).forEach(function (t) {
        t = (t || "").trim();
        if (t && tags.indexOf(t) < 0) tags.push(t);
      });
    }
    if (tagSelect && tags.indexOf(tagSelect) < 0) tags.push(tagSelect);
    return {
      email: (document.getElementById("mail-c-email").value || "").trim(),
      name: (document.getElementById("mail-c-name").value || "").trim(),
      phone: (document.getElementById("mail-c-phone").value || "").trim(),
      tags: tags,
      source: (document.getElementById("mail-c-source").value || "").trim() || "manual",
      notes: (document.getElementById("mail-c-notes").value || "").trim(),
      unsubscribed: !!(document.getElementById("mail-c-unsub") || {}).checked,
      verify_status: (document.getElementById("mail-c-verify") || {}).value || "",
      lifecycle: (document.getElementById("mail-c-lifecycle") || {}).value || "lead",
      crm_owner: (document.getElementById("mail-c-owner") || {}).value || ""
    };
  }

  function mailFillContactForm(c) {
    if (!c) return;
    document.getElementById("mail-c-id").value = c.id || "";
    document.getElementById("mail-c-email").value = c.email || "";
    document.getElementById("mail-c-name").value = c.name || "";
    document.getElementById("mail-c-phone").value = c.phone || "";
    document.getElementById("mail-c-tags-text").value = (c.tags || []).join(", ");
    document.getElementById("mail-c-tags").value = "";
    document.getElementById("mail-c-source").value = c.source || "manual";
    document.getElementById("mail-c-notes").value = c.notes || "";
    document.getElementById("mail-c-unsub").checked = !!c.unsubscribed;
    var verify = document.getElementById("mail-c-verify");
    if (verify) verify.value = c.verify_status || "";
    var life = document.getElementById("mail-c-lifecycle");
    if (life) life.value = c.lifecycle || "lead";
    var owner = document.getElementById("mail-c-owner");
    if (owner) owner.value = c.crm_owner || "";
    setText("mail-contact-form-title", "Kontak düzenle #" + c.id);
    var sub = document.getElementById("mail-contact-form-sub");
    if (sub) sub.textContent = "Düzenleme modu — kaydetince güncellenir";
    var submit = document.getElementById("mail-c-submit");
    if (submit) submit.textContent = "Güncelle";
    var cancel = document.getElementById("mail-c-cancel");
    if (cancel) cancel.hidden = false;
    try {
      document.getElementById("mail-contact-form").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) { /* ignore */ }
  }

  function mailEditContact(id) {
    mailApi("/api/mailing/contacts/" + id).then(function (res) {
      if (!res || !res.ok) {
        mailToast((res && res.data && res.data.error) || "Kontak yüklenemedi");
        return;
      }
      mailFillContactForm(res.data.contact);
    });
  }

  function mailScrubStatusText(j) {
    if (!j) return "—";
    var parts = [
      (j.processed || 0) + "/" + (j.total || "?"),
      "valid " + (j.valid_count || 0),
      "invalid " + (j.invalid_count || 0),
      "unknown " + (j.unknown_count || 0),
      "catch-all " + (j.catch_all_count || 0),
      "disp " + (j.disposable_count || 0),
      "role " + (j.role_count || 0),
      "suppressed " + (j.suppressed_count || 0)
    ];
    if (j.skipped_count) parts.push("skip " + j.skipped_count);
    return (j.status || "") + " · " + parts.join(" · ");
  }

  function mailPollScrubJob(jobId) {
    var prog = document.getElementById("mail-scrub-progress");
    var bar = document.getElementById("mail-scrub-progress-bar");
    var statusEl = document.getElementById("mail-scrub-status");
    var cancelBtn = document.getElementById("mail-scrub-cancel");
    if (prog) prog.hidden = false;
    if (cancelBtn) cancelBtn.hidden = false;
    mailScrubJobId = jobId;
    if (mailScrubPollTimer) { clearTimeout(mailScrubPollTimer); mailScrubPollTimer = null; }
    function poll() {
      mailApi("/api/mailing/contacts/scrub/status/" + jobId, { timeoutMs: 30000 }).then(function (res) {
        if (!res || !res.ok || !res.data.job) {
          mailScrubPollTimer = setTimeout(poll, 2500);
          return;
        }
        var j = res.data.job;
        var pct = j.total > 0 ? Math.min(100, Math.round((j.processed / j.total) * 100)) : 0;
        if (bar) bar.style.width = (j.total > 0 ? pct : (j.processed > 0 ? 40 : 12)) + "%";
        if (statusEl) statusEl.textContent = mailScrubStatusText(j);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") {
          if (cancelBtn) cancelBtn.hidden = true;
          mailScrubJobId = null;
          if (j.status === "done") mailToast("Liste temizliği bitti");
          else if (j.status === "error") mailToast(j.error || "Temizlik hatası");
          mailLoadContacts();
          mailLoadTags();
          return;
        }
        if (j.status === "cancelling" && statusEl) {
          statusEl.textContent = "İptal ediliyor… · " + mailScrubStatusText(j);
        }
        mailScrubPollTimer = setTimeout(poll, 1500);
      });
    }
    poll();
  }

  function mailStartScrub(opts) {
    opts = opts || {};
    var body = {};
    if (opts.contact_ids && opts.contact_ids.length) {
      body.contact_ids = opts.contact_ids;
    } else {
      body.tag_filter = (document.getElementById("mail-scrub-tag") || {}).value || "";
    }
    var n = opts.contact_ids ? opts.contact_ids.length : "filtre";
    if (!confirm("Liste temizliği başlasın mı? Kapsam: " + n)) return;
    mailApi("/api/mailing/contacts/scrub/start", { method: "POST", body: body, timeoutMs: 30000 }).then(function (res) {
      if (!res || !res.ok) {
        mailToast((res && res.data && res.data.error) || "Başlatılamadı");
        return;
      }
      mailToast("Temizlik başladı #" + res.data.job.id);
      mailPollScrubJob(res.data.job.id);
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

  var mailTplListFilter = "all";

  function mailTplIsHtml(t) {
    var h = ((t && t.html_body) || "").trim();
    if (!h) return false;
    if (/<!DOCTYPE/i.test(h) || /<html[\s>]/i.test(h) || /<table[\s>]/i.test(h)) return true;
    if (h.indexOf("<") >= 0 && h.length > 80) return true;
    return false;
  }

  function mailRenderTemplateTable() {
    var tbody = document.getElementById("mail-tpl-table");
    if (!tbody) return;
    var list = mailTemplates || [];
    if (mailTplListFilter === "html") list = list.filter(mailTplIsHtml);
    else if (mailTplListFilter === "text") list = list.filter(function (t) { return !mailTplIsHtml(t); });
    if (!list.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">' +
        (mailTemplates.length ? "Bu filtrede şablon yok" : "Şablon yok") + "</td></tr>";
      return;
    }
    tbody.innerHTML = list.map(function (t) {
      var isHtml = mailTplIsHtml(t);
      var badge = isHtml
        ? '<span class="mail-tpl-badge is-html">HTML</span>'
        : '<span class="mail-tpl-badge is-text">Yazı</span>';
      return "<tr>" +
        "<td>" + badge + "</td>" +
        "<td><strong>" + esc(t.name) + "</strong></td>" +
        "<td>" + esc(t.subject) + "</td>" +
        "<td>" + esc(fmtTime(t.updated_at)) + "</td>" +
        '<td style="white-space:nowrap;">' +
        '<button type="button" class="btn btn-sm mail-view-tpl" data-id="' + t.id + '">Görüntüle</button> ' +
        '<button type="button" class="btn btn-sm mail-edit-tpl" data-id="' + t.id + '">Düzenle</button> ' +
        '<button type="button" class="btn btn-sm mail-del-tpl" data-id="' + t.id + '">Sil</button>' +
        "</td></tr>";
    }).join("");
  }

  function mailLoadTemplates() {
    return mailApi("/api/mailing/templates").then(function (res) {
      mailTemplates = (res && res.ok && res.data.templates) || [];
      mailRenderTemplateTable();
      var nHtml = mailTemplates.filter(mailTplIsHtml).length;
      var nText = mailTemplates.length - nHtml;
      var hint = document.getElementById("mail-tpl-list-hint");
      if (hint) hint.textContent = mailTemplates.length + " şablon · " + nHtml + " HTML · " + nText + " yazı";
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

  function mailLogoPreviewUrl() {
    try {
      return (window.location.origin || "") + "/static/mailing/makrobet-logo.png";
    } catch (e) {
      return "/static/mailing/makrobet-logo.png";
    }
  }

  function mailSpamTipBannerHtml() {
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#050505;">' +
      '<tr><td align="center" style="padding:11px 18px;font-family:Urbanist,Arial,Helvetica,sans-serif;' +
      'font-size:12px;line-height:1.45;color:#ffffff;">' +
      '<span style="color:#ffd400;font-size:13px;vertical-align:middle;">⚠</span>' +
      "&nbsp;Butonların tıklanabilir olması için " +
      '<strong style="color:#ffd400;">Spam olmadığını bildir</strong> ' +
      "seçeneğine tıklayın." +
      "</td></tr></table>";
  }

  function ensureMailSpamTip(html) {
    var s = html || "";
    if (s.indexOf("Spam olmadığını bildir") >= 0) return s;
    var banner = mailSpamTipBannerHtml();
    var m = s.match(/<body[^>]*>/i);
    if (m) {
      var idx = s.indexOf(m[0]) + m[0].length;
      return s.slice(0, idx) + banner + s.slice(idx);
    }
    return banner + s;
  }

  function substituteTplPlaceholders(html) {
    var s = html || "<p class='muted'>Önizleme boş</p>";
    function linkUrl(raw) {
      return String(raw || "").trim().replace(/^sc\s*:\s*/i, "");
    }
    // Panelde barındırılan Makrobet logosu (CDN hotlink / iframe’de kırılıyordu)
    s = s.replace(/__MAIL_LOGO__/g, mailLogoPreviewUrl());
    s = ensureMailSpamTip(s);
    // href="{{link:...}}" → sadece URL; aksi halde butonlar patlıyor
    s = s.replace(/href\s*=\s*(["'])\s*\{\{\s*link\s*:\s*([^}]+)\s*\}\}\s*\1/gi, function (_m, q, raw) {
      return "href=" + q + linkUrl(raw) + q;
    });
    s = s.replace(/\{\{name\}\}/g, "Ali")
      .replace(/\{\{email\}\}/g, "ali@ornek.com")
      .replace(/\{\{phone\}\}/g, "+90555…")
      .replace(/\{\{\s*link\s*:\s*([^}]+)\s*\}\}/gi, function (_m, raw) {
        var u = linkUrl(raw);
        return '<a href="' + u + '" style="color:#ffd400;">' + u + "</a>";
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
    var raw = (bodyHtml || "").trim();
    if (!raw) {
      return "<!DOCTYPE html><html><head><meta charset='utf-8'></head>" +
        "<body style='margin:0;padding:40px;background:#f1f5f9;color:#64748b;font-family:system-ui,sans-serif;text-align:center;'>" +
        "Önizleme boş — şablonda içerik yok.</body></html>";
    }
    // Tam HTML e-posta dokümanını tekrar sarmalama — nested <html> bozuluyor / görünmüyor
    if (/<!DOCTYPE/i.test(raw) || /<html[\s>]/i.test(raw)) {
      return raw;
    }
    // Yazı / fragment: okunaklı açık kart (koyu zeminde siyah yazı sorunu)
    return "<!DOCTYPE html><html><head><meta charset='utf-8'>" +
      "<meta name='viewport' content='width=device-width, initial-scale=1.0'>" +
      "<style>" +
      "html,body{margin:0;padding:0;background:#e2e8f0;}" +
      "body{padding:28px 16px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;}" +
      ".mail-preview-shell{max-width:560px;margin:0 auto;background:#ffffff;color:#0f172a;" +
      "border-radius:12px;padding:28px 24px;box-shadow:0 8px 28px rgba(15,23,42,0.12);" +
      "font-size:15px;line-height:1.65;}" +
      ".mail-preview-shell p{margin:0 0 1em;color:#0f172a;}" +
      ".mail-preview-shell a{color:#2563eb;word-break:break-all;}" +
      "img{max-width:100%;height:auto;display:block;}" +
      "</style></head><body>" +
      "<div class='mail-preview-shell'>" + raw + "</div></body></html>";
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

  function mailCampSelectedTags() {
    var box = document.getElementById("mail-camp-tag-list");
    if (!box) return [];
    return Array.prototype.map.call(
      box.querySelectorAll('input[type="checkbox"]:checked'),
      function (el) { return el.value; }
    ).filter(Boolean);
  }

  function mailCampTagCountMap() {
    var countMap = {};
    (mailTagCounts || []).forEach(function (t) {
      if (t && t.name) countMap[t.name] = t.count;
    });
    return countMap;
  }

  function mailFormatTagBreakdown(tags, countMap, opts) {
    opts = opts || {};
    var parts = (tags || []).map(function (t) {
      var c = countMap && countMap[t];
      if (c == null && opts.allowMissing === false) return esc(t);
      if (c == null) return esc(t) + ": ?";
      return esc(t) + ": " + fmtNum(c);
    });
    return parts.join(" · ");
  }

  function mailSyncCampTagHidden() {
    var tags = mailCampSelectedTags();
    var hidden = document.getElementById("mail-camp-tag");
    if (hidden) hidden.value = tags.join(", ");
    var countMap = mailCampTagCountMap();
    var picked = document.getElementById("mail-camp-tag-picked");
    if (picked) {
      if (!tags.length) picked.textContent = "Seçim yok = tüm aktif kontaklar";
      else if (tags.length === 1) {
        var one = countMap[tags[0]];
        picked.textContent = "1 etiket: " + tags[0] + (one == null ? "" : (" (" + fmtNum(one) + ")"));
      } else {
        picked.textContent = tags.length + " etiket (birleşim)";
      }
    }
    var breakdown = document.getElementById("mail-camp-tag-breakdown");
    if (breakdown) {
      if (!tags.length) {
        breakdown.textContent = "";
      } else if (tags.length === 1) {
        var n1 = countMap[tags[0]];
        breakdown.textContent = n1 == null
          ? "Seçili etiket: " + tags[0]
          : ("Bu etiketten ≈ " + fmtNum(n1) + " mail (registry; filtreler «Kaç kişi?» ile uygulanır)");
      } else {
        var sum = 0;
        var known = 0;
        tags.forEach(function (t) {
          if (countMap[t] != null) { sum += Number(countMap[t]) || 0; known += 1; }
        });
        breakdown.innerHTML =
          "<strong>Etiket başına:</strong> " + mailFormatTagBreakdown(tags, countMap) +
          (known === tags.length
            ? (" <span class=\"muted\">· satır toplamı " + fmtNum(sum) + " (örtüşme olabilir; birleşim «Kaç kişi?»)</span>")
            : "");
      }
    }
    var box = document.getElementById("mail-camp-tag-list");
    if (box) {
      box.querySelectorAll(".mail-camp-tag-item").forEach(function (lab) {
        var inp = lab.querySelector('input[type="checkbox"]');
        lab.classList.toggle("is-checked", !!(inp && inp.checked));
      });
    }
  }

  function mailFillCampTagSelect() {
    var box = document.getElementById("mail-camp-tag-list");
    if (!box) return;
    var prev = {};
    mailCampSelectedTags().forEach(function (t) { prev[t] = true; });
    var countMap = {};
    (mailTagCounts || []).forEach(function (t) { countMap[t.name] = t.count; });
    var names = {};
    (mailTags || []).forEach(function (t) { if (t && t.name) names[t.name] = true; });
    (mailTagCounts || []).forEach(function (t) { if (t && t.name) names[t.name] = true; });
    var list = Object.keys(names).sort(function (a, b) { return a.localeCompare(b, "tr"); });
    if (!list.length) {
      box.innerHTML = '<span class="muted">Önce etiket oluştur</span>';
      mailSyncCampTagHidden();
      return;
    }
    box.innerHTML = list.map(function (name) {
      var c = countMap[name];
      var label = c == null ? name : (name + " (" + fmtNum(c) + ")");
      var checked = prev[name] ? " checked" : "";
      return '<label class="mail-camp-tag-item' + (prev[name] ? " is-checked" : "") + '">' +
        '<input type="checkbox" value="' + esc(name) + '"' + checked + "> " +
        "<span>" + esc(label) + "</span></label>";
    }).join("");
    mailSyncCampTagHidden();
  }

  function mailCampStatusLabel(status) {
    var map = {
      draft: "Taslak",
      scheduled: "Zamanlandı",
      queued: "Kuyrukta",
      sending: "Gönderiliyor",
      done: "Tamam",
      cancelling: "İptal…",
      cancelled: "İptal",
      paused: "Duraklatıldı",
      error: "Hata"
    };
    return map[status] || status || "—";
  }

  function mailCampProgressHtml(c) {
    var total = Number(c.total_count || c.recipient_count || 0);
    var sent = Number(c.sent_count || 0);
    var failed = Number(c.failed_count || 0);
    var skipped = Number(c.skipped_count || 0);
    var done = sent + failed + skipped;
    var pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : (c.status === "done" ? 100 : 0);
    return '<div class="mail-camp-progress">' +
      '<div class="mail-camp-progress-bar"><div class="mail-camp-progress-fill" style="width:' + pct + '%"></div></div>' +
      '<div class="mail-camp-progress-meta">' + fmtNum(sent) + " gönderildi" +
        (failed ? (" · " + fmtNum(failed) + " hata") : "") +
        (total ? (" / " + fmtNum(total)) : "") +
        " · %" + pct +
      "</div></div>";
  }

  function mailEnsureCampPoll(rows) {
    var need = (rows || []).some(function (c) {
      return c.status === "sending" || c.status === "queued" || c.status === "scheduled" || c.status === "cancelling";
    });
    if (need && !mailCampPollTimer) {
      mailCampPollTimer = setInterval(function () {
        if (document.hidden) return;
        var modulePane = document.getElementById("module-mailing-panel");
        if (modulePane && modulePane.hidden) return;
        var pane = document.getElementById("mail-pane-campaigns");
        if (!pane || pane.hidden) return;
        mailLoadCampaigns();
      }, 15000);
    }
    if (!need && mailCampPollTimer) {
      clearInterval(mailCampPollTimer);
      mailCampPollTimer = null;
    }
  }

  function mailLoadCampaigns() {
    return mailApi("/api/mailing/campaigns").then(function (res) {
      var tbody = document.getElementById("mail-camp-table");
      if (!tbody) return;
      if (!res || !res.ok) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Yüklenemedi</td></tr>';
        return;
      }
      var rows = res.data.campaigns || [];
      mailEnsureCampPoll(rows);
      if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty">Kampanya yok</td></tr>';
        return;
      }
      tbody.innerHTML = rows.map(function (c) {
        var actions = "";
        if (c.status === "draft" || c.status === "scheduled") {
          actions += '<button type="button" class="btn btn-sm btn-primary mail-queue-camp" data-id="' + c.id + '" data-now="1">Şimdi gönder</button> ';
        }
        if (c.status === "draft" && c.scheduled_at) {
          actions += '<button type="button" class="btn btn-sm mail-queue-camp" data-id="' + c.id + '">Zamanla</button> ';
        }
        if (c.status === "scheduled" || c.status === "queued" || c.status === "sending") {
          actions += '<button type="button" class="btn btn-sm mail-pause-camp" data-id="' + c.id + '">Duraklat</button> ';
          actions += '<button type="button" class="btn btn-sm mail-cancel-camp" data-id="' + c.id + '">İptal</button> ';
        }
        if (c.status === "paused") {
          actions += '<button type="button" class="btn btn-sm btn-primary mail-resume-camp" data-id="' + c.id + '">Devam</button> ';
          actions += '<button type="button" class="btn btn-sm mail-cancel-camp" data-id="' + c.id + '">İptal</button> ';
        }
        if (c.status === "done" || c.status === "error" || c.status === "cancelled" || c.status === "paused") {
          if (Number(c.failed_count || 0) > 0) {
            actions += '<button type="button" class="btn btn-sm mail-retry-camp" data-id="' + c.id + '">Fail retry</button> ';
          }
        }
        if (c.status === "draft" || c.status === "scheduled" || c.status === "done" || c.status === "cancelled" || c.status === "error") {
          actions += '<button type="button" class="btn btn-sm mail-del-camp" data-id="' + c.id + '">Sil</button>';
        }
        var tagLine = esc(c.tag_filter || "tümü");
        var rate = c.rate_per_minute != null ? (fmtNum(c.rate_per_minute) + "/dk") : "—";
        var when = c.scheduled_at
          ? ("⏱ " + esc(fmtTime(c.scheduled_at)))
          : esc(fmtTime(c.created_at));
        return "<tr>" +
          "<td><strong>" + esc(c.name) + "</strong>" +
            (c.error ? ('<div class="muted" style="font-size:0.68rem;color:var(--rose);">' + esc(c.error) + "</div>") : "") +
          "</td>" +
          '<td><span class="mail-camp-status ' + esc(c.status) + '">' + esc(mailCampStatusLabel(c.status)) + "</span></td>" +
          "<td>" + mailCampProgressHtml(c) + "</td>" +
          "<td>" + tagLine + '<div class="muted" style="font-size:0.68rem;">' + esc(rate) + "</div></td>" +
          "<td>" + when + "</td>" +
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

  function mailCloseCampDetailModal() {
    var modal = document.getElementById("mail-camp-detail-modal");
    if (modal) modal.classList.remove("open");
  }

  function mailOpenCampDetail(campaignId, campaignName) {
    var modal = document.getElementById("mail-camp-detail-modal");
    var title = document.getElementById("mail-camp-detail-title");
    var meta = document.getElementById("mail-camp-detail-meta");
    var tbody = document.getElementById("mail-camp-detail-table");
    if (!modal || !tbody) return;
    if (title) title.textContent = "Alıcılar — " + (campaignName || ("#" + campaignId));
    if (meta) meta.textContent = "Yükleniyor…";
    tbody.innerHTML = '<tr><td colspan="5" class="empty">Yükleniyor…</td></tr>';
    modal.classList.add("open");
    mailApi("/api/mailing/campaigns/" + campaignId + "/recipients?limit=1000", { timeoutMs: 60000 })
      .then(function (res) {
        if (!res || !res.ok) {
          var err = (res && res.data && res.data.error) || "Alıcılar alınamadı";
          if (meta) meta.textContent = err;
          tbody.innerHTML = '<tr><td colspan="5" class="empty">' + esc(err) + "</td></tr>";
          return;
        }
        var camp = res.data.campaign || {};
        var rows = res.data.recipients || [];
        var total = res.data.total != null ? res.data.total : rows.length;
        var tagFilter = (camp.tag_filter || "").trim();
        if (meta) {
          meta.textContent = fmtNum(total) + " alıcı" +
            (res.data.truncated ? " (ilk " + rows.length + " gösteriliyor)" : "") +
            (tagFilter ? (" · kampanya etiket filtresi: " + tagFilter) : " · etiket filtresi yok");
        }
        if (!rows.length) {
          tbody.innerHTML = '<tr><td colspan="5" class="empty">Alıcı yok</td></tr>';
          return;
        }
        tbody.innerHTML = rows.map(function (r) {
          var tags = (r.tags || []).map(function (t) {
            return '<span class="tag">' + esc(t) + "</span>";
          }).join(" ") || '<span class="muted">—</span>';
          var st = r.send_status || r.recipient_status || "—";
          var eng = [];
          if (r.opened_at) eng.push("açıldı");
          if (r.clicked_at) eng.push("tıkladı");
          return "<tr>" +
            "<td>" + esc(r.email || "") + "</td>" +
            "<td>" + esc(r.name || "") + "</td>" +
            "<td>" + tags + "</td>" +
            "<td>" + esc(st) + "</td>" +
            "<td>" + (eng.length ? esc(eng.join(" · ")) : '<span class="muted">—</span>') + "</td>" +
            "</tr>";
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
      mailApi(url),
      mailApi("/api/mailing/reports/campaigns")
    ]).then(function (results) {
      var dash = results[0];
      var sendsRes = results[1];
      var analyticsRes = results[2];
      if (dash && dash.ok) {
        var k = dash.data.kpi || {};
        setText("mail-rep-delivered", k.sends_delivered);
        setText("mail-rep-queued", k.sends_queued);
        setText("mail-rep-failed", k.sends_failed);
        setText("mail-rep-opened", k.opened);
      }
      var atbody = document.getElementById("mail-rep-analytics");
      if (atbody) {
        var camps = (analyticsRes && analyticsRes.ok && analyticsRes.data.campaigns) || [];
        if (!camps.length) {
          atbody.innerHTML = '<tr><td colspan="8" class="empty">Kampanya yok</td></tr>';
        } else {
          atbody.innerHTML = camps.map(function (c) {
            return "<tr>" +
              "<td>" + esc(c.name) + "</td>" +
              "<td>" + esc(mailCampStatusLabel(c.status)) + "</td>" +
              "<td>" + fmtNum(c.delivered) + "</td>" +
              "<td>" + esc(String(c.open_rate)) + "%</td>" +
              "<td>" + esc(String(c.click_rate)) + "%</td>" +
              "<td>" + fmtNum(c.failed_count) + "</td>" +
              "<td>" + fmtNum(c.skipped_count) + "</td>" +
              '<td><button type="button" class="btn btn-sm mail-camp-detail-btn" data-id="' +
              esc(String(c.id)) + '" data-name="' + esc(c.name || "") + '">Detay</button></td></tr>';
          }).join("");
        }
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
          "<td>" + esc(s.status) + (s.error ? (' <span class="muted" title="' + esc(s.error) + '">!</span>') : "") + "</td>" +
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
      var scrub = s.scrub || {};
      var elSmtp = document.getElementById("mail-scrub-smtp");
      if (elSmtp) elSmtp.checked = scrub.scrub_smtp_verify !== false && s.scrub_smtp_verify !== "0";
      var elRate = document.getElementById("mail-scrub-rate");
      if (elRate) elRate.value = scrub.scrub_rate_per_minute || s.scrub_rate_per_minute || 30;
      var elSkip = document.getElementById("mail-scrub-skip");
      if (elSkip) elSkip.value = scrub.scrub_skip_hours != null ? scrub.scrub_skip_hours : (s.scrub_skip_hours || 168);
      var elFrom = document.getElementById("mail-scrub-from");
      if (elFrom) elFrom.value = scrub.scrub_mail_from || s.scrub_mail_from || "";
      var elInv = document.getElementById("mail-scrub-suppress-invalid");
      if (elInv) elInv.checked = scrub.scrub_auto_suppress_invalid !== false && s.scrub_auto_suppress_invalid !== "0";
      var elDisp = document.getElementById("mail-scrub-suppress-disposable");
      if (elDisp) elDisp.checked = scrub.scrub_suppress_disposable !== false && s.scrub_suppress_disposable !== "0";
      var elRole = document.getElementById("mail-scrub-suppress-role");
      if (elRole) elRole.checked = !!(scrub.scrub_suppress_role || s.scrub_suppress_role === "1");
      var elCamp = document.getElementById("mail-scrub-camp-only");
      if (elCamp) elCamp.checked = !!(scrub.scrub_campaign_only_valid || s.scrub_campaign_only_valid === "1");
      var campOnly = document.getElementById("mail-camp-only-verified");
      if (campOnly && (scrub.scrub_campaign_only_valid || s.scrub_campaign_only_valid === "1")) {
        campOnly.checked = true;
      }
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
      var smtpOk = d.smtp_password_set ? "SMTP ✓" : "SMTP yok";
      return "<tr>" +
        "<td>" + esc(d.domain) + "</td>" +
        "<td>" + esc(d.from_name) + " &lt;" + esc(from) + "&gt;</td>" +
        "<td>" + esc(d.status) + "</td>" +
        "<td>" + esc(d.dns_status) + " · " + smtpOk + "</td>" +
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

    bindClick("mail-rel-refresh", mailLoadRelations);
    bindClick("mail-rel-search", mailLoadRelationsPipeline);
    bindClick("mail-rel-recompute", function () {
      mailToast("Skorlar hesaplanıyor…");
      mailApi("/api/mailing/relations/recompute", { method: "POST", body: { limit: 400 }, timeoutMs: 120000 })
        .then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Hesaplanamadı");
            return;
          }
          mailToast(res.data.message || "Tamam");
          mailLoadRelations();
        });
    });
    bindClick("mail-rel-profile-close", function () {
      mailRelContactId = null;
      var card = document.getElementById("mail-rel-profile-card");
      if (card) card.hidden = true;
    });
    bindClick("mail-rel-save-life", function () {
      if (!mailRelContactId) return;
      mailApi("/api/mailing/relations/contacts/" + mailRelContactId + "/lifecycle", {
        method: "PATCH",
        body: {
          lifecycle: (document.getElementById("mail-rel-lifecycle") || {}).value,
          crm_owner: (document.getElementById("mail-rel-owner") || {}).value || ""
        }
      }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Kaydedilemedi");
          return;
        }
        mailToast("CRM kaydı güncellendi");
        mailRenderRelProfile(res.data.contact);
        mailLoadRelationsPipeline();
      });
    });
    bindClick("mail-rel-note-btn", function () {
      if (!mailRelContactId) return;
      var body = ((document.getElementById("mail-rel-note") || {}).value || "").trim();
      if (!body) { mailToast("Not yaz"); return; }
      mailApi("/api/mailing/relations/contacts/" + mailRelContactId + "/notes", {
        method: "POST",
        body: { body: body }
      }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Not eklenemedi");
          return;
        }
        document.getElementById("mail-rel-note").value = "";
        mailToast("Not kaydedildi");
        mailRenderRelProfile(res.data.contact);
      });
    });
    bindClick("mail-rel-task-btn", function () {
      if (!mailRelContactId) return;
      var title = ((document.getElementById("mail-rel-task-title") || {}).value || "").trim();
      if (!title) { mailToast("Görev başlığı yaz"); return; }
      var due = ((document.getElementById("mail-rel-task-due") || {}).value || "").trim();
      if (due && due.length === 16) due += ":00";
      mailApi("/api/mailing/relations/contacts/" + mailRelContactId + "/tasks", {
        method: "POST",
        body: { title: title, due_at: due || null }
      }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Görev eklenemedi");
          return;
        }
        document.getElementById("mail-rel-task-title").value = "";
        mailToast("Görev eklendi");
        mailRenderRelProfile(res.data.contact);
        mailLoadRelations();
      });
    });
    document.addEventListener("click", function (e) {
      var chip = e.target.closest(".mail-rel-life-chip");
      if (chip) {
        var life = chip.getAttribute("data-life") || "";
        var filter = document.getElementById("mail-rel-life-filter");
        if (filter) filter.value = life;
        mailLoadRelationsPipeline();
        return;
      }
      var openBtn = e.target.closest(".mail-rel-open");
      if (openBtn) {
        mailOpenRelProfile(Number(openBtn.getAttribute("data-id")));
        return;
      }
      var doneBtn = e.target.closest(".mail-rel-task-done");
      if (doneBtn) {
        var tid = doneBtn.getAttribute("data-id");
        mailApi("/api/mailing/relations/tasks/" + tid, { method: "PATCH", body: { status: "done" } })
          .then(function (res) {
            if (!res || !res.ok) {
              mailToast((res && res.data && res.data.error) || "Güncellenemedi");
              return;
            }
            if (mailRelContactId) mailOpenRelProfile(mailRelContactId);
            mailLoadRelations();
          });
      }
    });
    var relQ = document.getElementById("mail-rel-q");
    if (relQ) {
      relQ.addEventListener("keydown", function (e) {
        if (e.key === "Enter") mailLoadRelationsPipeline();
      });
    }

    var cForm = document.getElementById("mail-contact-form");
    if (cForm) {
      cForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = mailCollectContactFormBody();
        if (!body.email) { mailToast("E-posta gerekli"); return; }
        var editId = (document.getElementById("mail-c-id").value || "").trim();
        var req = editId
          ? mailApi("/api/mailing/contacts/" + editId, { method: "PATCH", body: body })
          : mailApi("/api/mailing/contacts", { method: "POST", body: body });
        req.then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || (editId ? "Güncellenemedi" : "Eklenemedi"));
            return;
          }
          mailResetContactForm();
          mailToast(editId ? "Kontak güncellendi" : "Kontak eklendi");
          mailLoadContactStats();
          mailLoadContacts();
          mailLoadTags();
        });
      });
    }
    bindClick("mail-c-cancel", mailResetContactForm);

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
      if (mailImportActiveXhr) {
        try { mailImportActiveXhr.abort(); } catch (e) { /* ignore */ }
        mailImportActiveXhr = null;
        mailImportBusy = false;
        mailImportCurrentJobId = null;
        mailClearImportSession();
        mailBulkSetError("Yükleme iptal edildi.", "");
        mailUpdateBulkFormState();
        mailStartNextImport();
        mailToast("Yükleme iptal edildi");
        return;
      }
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
      mailLoadContacts();
      mailLoadTags();
      mailLoadContactStats({ refresh: true });
    });
    bindClick("mail-crm-tag-refresh", function () {
      var hint = document.getElementById("mail-crm-tag-stats-hint");
      if (hint) hint.textContent = "Özet yenileniyor…";
      mailLoadContactStats({ refresh: true }).then(function () {
        if (hint) hint.textContent = "Aynı kontak birden fazla etikette sayılabilir";
      });
    });
    bindClick("mail-contacts-select-page", function () {
      document.querySelectorAll(".mail-contact-check").forEach(function (el) { el.checked = true; });
      mailUpdateContactSelectionCount();
      var n = document.querySelectorAll(".mail-contact-check:checked").length;
      mailToast(n ? (n + " kontak seçildi") : "Seçilecek kontak yok");
    });

    var contactsTable = document.getElementById("mail-contacts-table");
    if (contactsTable) {
      contactsTable.addEventListener("change", function (e) {
        if (e.target && e.target.classList && e.target.classList.contains("mail-contact-check")) {
          mailUpdateContactSelectionCount();
        }
      });
    }

    function mailSelectedContactIds() {
      return Array.prototype.map.call(
        document.querySelectorAll(".mail-contact-check:checked"),
        function (el) { return Number(el.value); }
      ).filter(Boolean);
    }

    function mailRunBulkTag(action) {
      var statusEl = document.getElementById("mail-tag-move-status");
      var scopeMode = mailGetMoveScope();
      var fromTag = mailGetMoveFromTag();
      var toTag = mailGetMoveToTag();
      var ids = mailSelectedContactIds();
      var body = { action: action, from_tag: fromTag, to_tag: toTag };
      if (scopeMode === "all") {
        body.match_tag = fromTag || ((document.getElementById("mail-contact-tag-filter") || {}).value || "");
        if (!body.match_tag) {
          mailToast("Soldan kaynak etiket seç");
          return;
        }
        if (action === "add") body.from_tag = body.match_tag;
      } else if (ids.length) {
        body.contact_ids = ids;
      } else {
        mailToast("Alttaki tabloda kişi işaretle — veya «Kaynak etiketteki herkes»i seç");
        return;
      }
      if (action === "add" && !toTag) { mailToast("Sağdan hedef etiket seç"); return; }
      if (action === "remove" && !fromTag) { mailToast("Soldan kaldırılacak kaynak etiket seç"); return; }
      if (action === "move" && (!fromTag || !toTag)) { mailToast("Soldan kaynak, sağdan hedef seç"); return; }

      var scope = scopeMode === "all"
        ? ("«" + (body.match_tag || fromTag) + "» içindeki HERKES")
        : (ids.length + " seçili kişi");
      var label = action === "move" ? ("Taşı: " + fromTag + " → " + toTag)
        : (action === "add" ? ("Kopyala / ekle: " + toTag) : ("Kaldır: " + fromTag));
      if (!confirm(label + "\nKapsam: " + scope + "\nDevam?")) return;
      if (statusEl) statusEl.textContent = "İşleniyor…";
      mailApi("/api/mailing/contacts/tags/bulk", { method: "POST", body: body, timeoutMs: 300000 })
        .then(function (res) {
          if (!res || !res.ok) {
            var err = (res && res.data && res.data.error) || "İşlem başarısız";
            if (statusEl) statusEl.textContent = err;
            mailToast(err);
            return;
          }
          var msg = (res.data && res.data.message) || "Tamam";
          if (statusEl) statusEl.textContent = msg;
          mailToast(msg);
          mailLoadTags();
          mailLoadContactStats();
          mailLoadContacts();
        });
    }

    bindClick("mail-tag-move-btn", function () { mailRunBulkTag("move"); });
    bindClick("mail-tag-add-btn", function () { mailRunBulkTag("add"); });
    bindClick("mail-tag-remove-btn", function () { mailRunBulkTag("remove"); });

    document.querySelectorAll('input[name="mail-tag-scope"]').forEach(function (r) {
      r.addEventListener("change", mailUpdateMoveSummary);
    });
    var moveToNew = document.getElementById("mail-tag-move-to-new");
    if (moveToNew) {
      moveToNew.addEventListener("input", function () {
        var toEl = document.getElementById("mail-tag-move-to");
        if (toEl && moveToNew.value.trim()) toEl.value = "";
        mailRenderTagPickLists();
      });
    }
    document.addEventListener("click", function (e) {
      var fromItem = e.target.closest("#mail-tag-from-list .mail-tag-pick-item");
      if (fromItem) {
        var fromName = fromItem.getAttribute("data-tag") || "";
        var fromEl = document.getElementById("mail-tag-move-from");
        if (fromEl) fromEl.value = fromName;
        mailRenderTagPickLists();
        return;
      }
      var toItem = e.target.closest("#mail-tag-to-list .mail-tag-pick-item");
      if (toItem) {
        var toName = toItem.getAttribute("data-tag") || "";
        var toEl = document.getElementById("mail-tag-move-to");
        var neu = document.getElementById("mail-tag-move-to-new");
        if (toEl) toEl.value = toName;
        if (neu) neu.value = "";
        mailRenderTagPickLists();
      }
    });

    bindClick("mail-tag-cleanup-btn", function () {
      if (!confirm("0 kontaklı tüm etiketler silinsin mi?")) return;
      var st = document.getElementById("mail-tag-manage-status");
      if (st) st.textContent = "Temizleniyor…";
      mailApi("/api/mailing/tags/cleanup", { method: "POST", timeoutMs: 300000 }).then(function (res) {
        var msg = (res && res.data && res.data.message) || ((res && res.ok) ? "Tamam" : "Hata");
        if (st) st.textContent = msg;
        mailToast(msg);
        mailLoadTags();
        mailLoadContactStats();
      });
    });

    document.addEventListener("click", function (e) {
      var delTag = e.target.closest(".mail-tag-delete-btn");
      if (!delTag) return;
      var name = delTag.getAttribute("data-tag") || "";
      var count = Number(delTag.getAttribute("data-count") || 0);
      if (!name) return;
      var force = false;
      if (count > 0) {
        if (!confirm("«" + name + "» etiketinde " + fmtNum(count) + " kontak var.\nKontaklardan da kaldırıp etiketi tamamen silmek istiyor musun?")) {
          return;
        }
        force = true;
      } else if (!confirm("«" + name + "» silinsin mi?")) {
        return;
      }
      var st = document.getElementById("mail-tag-manage-status");
      if (st) st.textContent = "Siliniyor…";
      mailApi("/api/mailing/tags/delete", {
        method: "POST",
        body: { name: name, force: force },
        timeoutMs: 300000
      }).then(function (res) {
        if (!res || !res.ok) {
          var err = (res && res.data && res.data.error) || "Silinemedi";
          if (st) st.textContent = err;
          mailToast(err);
          return;
        }
        var msg = (res.data && res.data.message) || "Silindi";
        if (st) st.textContent = msg;
        mailToast(msg);
        mailLoadTags();
        mailLoadContactStats();
        mailLoadContacts();
      });
    });

    var tagCreateForm = document.getElementById("mail-tag-create-form");
    if (tagCreateForm) {
      tagCreateForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var name = (document.getElementById("mail-tag-create-name").value || "").trim();
        if (!name) return;
        mailApi("/api/mailing/tags", { method: "POST", body: { name: name } }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Etiket oluşturulamadı");
            return;
          }
          mailToast("Etiket oluşturuldu: " + name);
          document.getElementById("mail-tag-create-name").value = "";
          mailLoadTags().then(function () {
            ["mail-bulk-tag", "mail-paste-tag", "mail-c-tags", "mail-csv-tag", "mail-tag-move-to"].forEach(function (id) {
              var el = document.getElementById(id);
              if (el) el.value = name;
            });
            mailRenderTagPickLists();
          });
          mailLoadContactStats();
        });
      });
    }

    var qEl = document.getElementById("mail-contact-q");
    if (qEl) qEl.addEventListener("input", debounce(mailLoadContacts, 300));
    var tagEl = document.getElementById("mail-contact-tag-filter");
    if (tagEl) tagEl.addEventListener("change", function () {
      var selected = tagEl.value || "";
      var fromEl = document.getElementById("mail-tag-move-from");
      if (fromEl && selected) fromEl.value = selected;
      mailRenderTagPickLists();
      var list = document.getElementById("mail-crm-tag-stats-list");
      if (list) {
        list.querySelectorAll(".mail-tag-stat").forEach(function (btn) {
          var name = btn.getAttribute("data-mail-tag-filter") || "";
          if (selected && name === selected) btn.classList.add("is-active");
          else btn.classList.remove("is-active");
        });
      }
      mailLoadContacts();
    });

    document.addEventListener("click", function (e) {
      var tagBtn = e.target.closest("[data-mail-tag-filter]");
      if (tagBtn) {
        var tagName = tagBtn.getAttribute("data-mail-tag-filter") || "";
        var filterEl = document.getElementById("mail-contact-tag-filter");
        var next = "";
        if (filterEl) {
          next = (filterEl.value === tagName) ? "" : tagName;
          filterEl.value = next;
        }
        var fromEl = document.getElementById("mail-tag-move-from");
        if (fromEl && next) fromEl.value = next;
        mailRenderTagPickLists();
        var list = document.getElementById("mail-crm-tag-stats-list");
        if (list) {
          list.querySelectorAll(".mail-tag-stat").forEach(function (btn) {
            var name = btn.getAttribute("data-mail-tag-filter") || "";
            if (next && name === next) btn.classList.add("is-active");
            else btn.classList.remove("is-active");
          });
        }
        mailLoadContacts();
        return;
      }
      var editC = e.target.closest(".mail-edit-contact");
      if (editC) {
        mailEditContact(editC.getAttribute("data-id"));
        return;
      }
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
        setTplMode(mailTplIsHtml(t) ? "html" : "simple");
        refreshTplPreview();
        var editorCard = document.querySelector(".mail-tpl-editor-card");
        if (editorCard) try { editorCard.scrollIntoView({ behavior: "smooth", block: "start" }); } catch (e2) {}
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
        var sendNow = queueC.getAttribute("data-now") === "1";
        var qMsg = sendNow
          ? "Kampanya şimdi arka planda gönderilsin mi?"
          : "Kampanya zamanlanmış saatte başlasın mı?";
        if (!confirm(qMsg)) return;
        mailApi("/api/mailing/campaigns/" + queueC.getAttribute("data-id") + "/queue", {
          method: "POST",
          body: { send_now: sendNow },
          timeoutMs: 60000
        }).then(function (res) {
          mailToast((res && res.data && res.data.message) || (res && res.ok ? "Kuyruğa alındı" : ((res && res.data && res.data.error) || "Hata")));
          mailLoadCampaigns();
        });
        return;
      }
      var pauseC = e.target.closest(".mail-pause-camp");
      if (pauseC) {
        mailApi("/api/mailing/campaigns/" + pauseC.getAttribute("data-id") + "/pause", { method: "POST" })
          .then(function (res) {
            mailToast((res && res.ok) ? "Duraklatıldı" : ((res && res.data && res.data.error) || "Olmadı"));
            mailLoadCampaigns();
          });
        return;
      }
      var resumeC = e.target.closest(".mail-resume-camp");
      if (resumeC) {
        mailApi("/api/mailing/campaigns/" + resumeC.getAttribute("data-id") + "/resume", { method: "POST" })
          .then(function (res) {
            mailToast((res && res.ok) ? "Devam ediyor" : ((res && res.data && res.data.error) || "Olmadı"));
            mailLoadCampaigns();
          });
        return;
      }
      var retryC = e.target.closest(".mail-retry-camp");
      if (retryC) {
        if (!confirm("Başarısız alıcılar yeniden kuyruğa alınsın mı?")) return;
        mailApi("/api/mailing/campaigns/" + retryC.getAttribute("data-id") + "/retry-failed", { method: "POST" })
          .then(function (res) {
            mailToast((res && res.ok) ? "Retry başladı" : ((res && res.data && res.data.error) || "Olmadı"));
            mailLoadCampaigns();
          });
        return;
      }
      var cancelC = e.target.closest(".mail-cancel-camp");
      if (cancelC) {
        if (!confirm("Kampanya iptal edilsin mi? Devam eden gönderimler durur.")) return;
        mailApi("/api/mailing/campaigns/" + cancelC.getAttribute("data-id") + "/cancel", { method: "POST" })
          .then(function (res) {
            mailToast((res && res.ok) ? "İptal isteği alındı" : ((res && res.data && res.data.error) || "İptal edilemedi"));
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
        var fromName = prompt("From adı", d.from_name || d.domain || "");
        if (fromName === null) return;
        var fromLocal = prompt("From local (örn. info)", d.from_local || "info");
        if (fromLocal === null) return;
        var smtpHint = d.smtp_password_set
          ? "DirectMail SMTP şifresi (boş = değiştirme)"
          : "DirectMail SMTP şifresi (info@" + d.domain + " için zorunlu)";
        var smtpPw = prompt(smtpHint, "");
        if (smtpPw === null) return;
        var body = { from_name: fromName, from_local: fromLocal, status: "active", dns_status: "verified" };
        if ((smtpPw || "").trim()) body.smtp_password = smtpPw.trim();
        mailApi("/api/mailing/domains/" + did, {
          method: "PATCH",
          body: body
        }).then(function (res) {
          if (!res || !res.ok) {
            mailToast((res && res.data && res.data.error) || "Domain kaydedilemedi");
            return;
          }
          mailToast("Domain güncellendi");
          mailLoadSettings();
        });
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
    bindClick("mail-tpl-reseed", function () {
      mailToast("Makrobet şablonları güncelleniyor…");
      mailApi("/api/mailing/templates/reseed", { method: "POST", timeoutMs: 30000 }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Yüklenemedi");
          return;
        }
        mailToast((res.data && res.data.message) || "Tamam");
        mailLoadTemplates();
      });
    });
    document.querySelectorAll(".mail-tpl-filter").forEach(function (btn) {
      btn.addEventListener("click", function () {
        mailTplListFilter = btn.getAttribute("data-tpl-filter") || "all";
        document.querySelectorAll(".mail-tpl-filter").forEach(function (b) {
          b.classList.toggle("is-active", b === btn);
        });
        mailRenderTemplateTable();
      });
    });
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
      var rateEl = document.getElementById("mail-camp-rate");
      var rateVal = rateEl && rateEl.value ? Number(rateEl.value) : 120;
      var onlyV = document.getElementById("mail-camp-only-verified");
      var mode = mailCampRecipientMode();
      var tags = mode === "tag" ? mailCampSelectedTags() : [];
      var body = {
        recipient_mode: mode,
        tag_filter: tags.join(", "),
        tag_filters: tags,
        max_recipients: maxVal,
        rate_per_minute: rateVal || 120,
        scheduled_at: (document.getElementById("mail-camp-schedule").value || "").trim(),
        exclude_previously_sent: document.getElementById("mail-camp-exclude-sent").checked,
        only_verified: onlyV ? !!onlyV.checked : false
      };
      if (mode === "selected") {
        body.contact_ids = mailReadCampSelectedIds();
      }
      if (mode === "manual") {
        body.manual_emails = (document.getElementById("mail-camp-manual-emails") || {}).value || "";
      }
      return body;
    }

    document.querySelectorAll('input[name="mail-camp-recipient-mode"]').forEach(function (radio) {
      radio.addEventListener("change", mailSyncCampRecipientModeUI);
    });
    mailSyncCampRecipientModeUI();

    var campTagList = document.getElementById("mail-camp-tag-list");
    if (campTagList) {
      campTagList.addEventListener("change", function (e) {
        if (e.target && e.target.matches('input[type="checkbox"]')) mailSyncCampTagHidden();
      });
    }
    bindClick("mail-camp-tag-all", function () {
      var box = document.getElementById("mail-camp-tag-list");
      if (!box) return;
      box.querySelectorAll('input[type="checkbox"]').forEach(function (el) { el.checked = true; });
      mailSyncCampTagHidden();
    });
    bindClick("mail-camp-tag-none", function () {
      var box = document.getElementById("mail-camp-tag-list");
      if (!box) return;
      box.querySelectorAll('input[type="checkbox"]').forEach(function (el) { el.checked = false; });
      mailSyncCampTagHidden();
    });

    bindClick("mail-contacts-to-campaign", function () {
      var ids = mailSelectedContactIds();
      if (!ids.length) {
        mailToast("Önce listeden kontak seç");
        return;
      }
      mailWriteCampSelectedIds(ids);
      mailToast(fmtNum(ids.length) + " kontak kampanyaya hazır");
      var modeSel = document.querySelector('input[name="mail-camp-recipient-mode"][value="selected"]');
      if (modeSel) {
        modeSel.checked = true;
        mailSyncCampRecipientModeUI();
      }
      switchMailTab("campaigns");
    });

    var campForm = document.getElementById("mail-camp-form");
    if (campForm) {
      campForm.addEventListener("submit", function (e) {
        e.preventDefault();
        var body = mailCampSelectionPayload();
        body.name = document.getElementById("mail-camp-name").value.trim();
        body.template_id = Number(document.getElementById("mail-camp-tpl").value);
        body.domain_id = Number(document.getElementById("mail-camp-domain").value);
        body.notes = document.getElementById("mail-camp-notes").value.trim();
        if (!body.template_id || !body.domain_id) {
          mailToast("Şablon ve domain seçin");
          return;
        }
        mailApi("/api/mailing/campaigns", { method: "POST", body: body, timeoutMs: 120000 }).then(function (res) {
          if (!res || !res.ok) {
            var errMsg = (res && res.data && res.data.error) || "";
            if (!errMsg && !res) errMsg = "Bağlantı/oturum hatası — sayfayı yenile, tenant seç, tekrar dene";
            if (!errMsg) errMsg = "Oluşturulamadı" + (res && res.status ? (" (HTTP " + res.status + ")") : "");
            if (window.MAIL_STANDALONE && window.MAIL_IS_SUPERADMIN && !window.MAIL_TENANT_ID) {
              errMsg = "Üstten Aktif tenant seç (örn. makro), sonra tekrar dene";
            }
            mailToast(errMsg);
            return;
          }
          var camp = res.data.campaign || {};
          var toastMsg = "Kampanya oluşturuldu · " + fmtNum(camp.recipient_count || 0) + " alıcı";
          var tb = camp.tag_breakdown || [];
          if (tb.length) {
            toastMsg += " · " + tb.map(function (x) {
              return (x.tag || "") + ": " + fmtNum(x.count || 0);
            }).join(", ");
          }
          mailToast(toastMsg);
          if (mailCampRecipientMode() === "selected") mailWriteCampSelectedIds([]);
          campForm.reset();
          document.getElementById("mail-camp-exclude-sent").checked = true;
          document.getElementById("mail-camp-rate").value = "120";
          var modeTag = document.querySelector('input[name="mail-camp-recipient-mode"][value="tag"]');
          if (modeTag) modeTag.checked = true;
          mailSyncCampRecipientModeUI();
          mailFillCampTagSelect();
          var hint = document.getElementById("mail-camp-preview-hint");
          if (hint) hint.textContent = "";
          mailLoadCampaigns();
        });
      });
    }
    bindClick("mail-camp-preview", function () {
      var hint = document.getElementById("mail-camp-preview-hint");
      if (hint) hint.textContent = "Hesaplanıyor…";
      mailApi("/api/mailing/campaigns/select-preview", { method: "POST", body: mailCampSelectionPayload(), timeoutMs: 60000 })
        .then(function (res) {
          if (!hint) return;
          if (!res || !res.ok) {
            hint.textContent = (res && res.data && res.data.error) || "Hesaplanamadı — üstten tenant (makro) seçili mi?";
            return;
          }
          var total = res.data.matching_count || 0;
          var willAttach = res.data.will_attach != null ? res.data.will_attach : total;
          var tags = res.data.tag_filters || [];
          var breakdown = res.data.tag_breakdown || [];
          var approxBit = res.data.approx ? " (yaklaşık)" : "";
          var html = "Filtreye uyan: <strong>" + fmtNum(total) + "</strong>" + approxBit +
            " kişi · eklenecek: <strong>" + fmtNum(willAttach) + "</strong> kişi";
          if (breakdown.length) {
            var map = {};
            var anyApprox = false;
            breakdown.forEach(function (x) {
              map[x.tag] = x.count;
              if (x.approx) anyApprox = true;
            });
            html += "<br><strong>Etiket başına:</strong> " + mailFormatTagBreakdown(
              breakdown.map(function (x) { return x.tag; }),
              map
            );
            if (tags.length > 1) {
              html += ' <span class="muted">· birleşim (OR)' +
                (anyApprox ? ", etiket sayıları yaklaşık olabilir" : "") +
                "; aynı kişi birden fazla etikette olabilir</span>";
            }
          } else if (tags.length) {
            html += " · etiket: " + esc(tags.join(", "));
          }
          hint.innerHTML = html;
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
    bindClick("mail-rep-analytics-refresh", mailLoadReports);
    bindClick("mail-camp-detail-close", mailCloseCampDetailModal);
    var campDetailModal = document.getElementById("mail-camp-detail-modal");
    if (campDetailModal) {
      campDetailModal.addEventListener("click", function (e) {
        if (e.target === campDetailModal) mailCloseCampDetailModal();
      });
    }
    document.addEventListener("click", function (e) {
      var btn = e.target.closest(".mail-camp-detail-btn");
      if (!btn) return;
      var id = Number(btn.getAttribute("data-id"));
      if (!id) return;
      mailOpenCampDetail(id, btn.getAttribute("data-name") || "");
    });
    bindClick("mail-contacts-export", function () {
      var tag = (document.getElementById("mail-contact-tag-filter") || {}).value || "";
      var url = "/api/mailing/contacts/export?limit=50000";
      if (tag) url += "&tag=" + encodeURIComponent(tag);
      window.open(url, "_blank");
    });
    bindClick("mail-scrub-start", function () { mailStartScrub({}); });
    bindClick("mail-scrub-selected", function () {
      var ids = Array.prototype.map.call(
        document.querySelectorAll(".mail-contact-check:checked"),
        function (el) { return Number(el.value); }
      ).filter(Boolean);
      if (!ids.length) { mailToast("Önce kontak seç"); return; }
      mailStartScrub({ contact_ids: ids });
    });
    bindClick("mail-scrub-cancel", function () {
      if (!mailScrubJobId) return;
      mailApi("/api/mailing/contacts/scrub/cancel/" + mailScrubJobId, { method: "POST" }).then(function (res) {
        if (!res || !res.ok) mailToast((res && res.data && res.data.error) || "İptal edilemedi");
        else mailToast("İptal isteniyor…");
      });
    });
    var scrubForm = document.getElementById("mail-scrub-settings-form");
    if (scrubForm) {
      scrubForm.addEventListener("submit", function (e) {
        e.preventDefault();
        mailApi("/api/mailing/settings", {
          method: "PATCH",
          body: {
            scrub_smtp_verify: document.getElementById("mail-scrub-smtp").checked,
            scrub_rate_per_minute: String(document.getElementById("mail-scrub-rate").value || 30),
            scrub_skip_hours: String(document.getElementById("mail-scrub-skip").value || 168),
            scrub_mail_from: (document.getElementById("mail-scrub-from").value || "").trim(),
            scrub_auto_suppress_invalid: document.getElementById("mail-scrub-suppress-invalid").checked,
            scrub_suppress_disposable: document.getElementById("mail-scrub-suppress-disposable").checked,
            scrub_suppress_role: document.getElementById("mail-scrub-suppress-role").checked,
            scrub_campaign_only_valid: document.getElementById("mail-scrub-camp-only").checked
          }
        }).then(function (res) {
          if (!res || !res.ok) { mailToast("Kaydedilemedi"); return; }
          mailToast("Temizleme ayarları kaydedildi");
          mailLoadSettings();
        });
      });
    }
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
        if (mailActiveTab === "smartico") mailLoadSmarticoPlayers(true);
      });
    });
    bindClick("mail-sc-refresh", function () { mailLoadSmarticoPlayers(true); });
    bindClick("mail-sc-sync", function () {
      mailToast("Smartico segmentleri güncelleniyor…");
      mailApi("/api/mailing/crm/sync-smartico", { method: "POST", timeoutMs: 30000 }).then(function (res) {
        if (!res || !res.ok) {
          mailToast((res && res.data && res.data.error) || "Güncellenemedi");
          return;
        }
        mailToast(res.data.message || "Segmentler güncellendi");
        mailLoadSmarticoPlayers(true);
      });
    });
    var scPeriod = document.getElementById("mail-sc-period");
    if (scPeriod) scPeriod.addEventListener("change", function () { mailLoadSmarticoPlayers(false); });
    ["mail-sc-matched", "mail-sc-ftd"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", function () { mailLoadSmarticoPlayers(false); });
    });
    var scQ = document.getElementById("mail-sc-q");
    if (scQ) {
      scQ.addEventListener("input", function () {
        clearTimeout(mailScSearchTimer);
        mailScSearchTimer = setTimeout(function () { mailLoadSmarticoPlayers(false); }, 350);
      });
    }
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
      var tab = "dashboard";
      try { tab = localStorage.getItem(MAIL_TAB_STORAGE_KEY) || "dashboard"; } catch (e) { /* ignore */ }
      switchMailTab(tab);
      mailRefreshImportStatus({ force: true });
    },
    onHide: function () {
      if (mailCampPollTimer) {
        clearInterval(mailCampPollTimer);
        mailCampPollTimer = null;
      }
      if (mailImportPollTimer) {
        clearTimeout(mailImportPollTimer);
        mailImportPollTimer = null;
      }
    },
    setPermissions: function (perms) {
      mailPerms = perms || [];
    },
    refresh: function () {
      mailLoadTab(mailActiveTab);
    }
  };
})();
