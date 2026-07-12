(function () {
  "use strict";

  var blLoaded = false;
  var blPerms = [];
  var blPages = [];
  var blThemes = [];
  var blCurrentPage = null;

  function blHas(key) {
    if (!blPerms || !blPerms.length) return true;
    if (blPerms.indexOf("*") >= 0) return true;
    if (blPerms.indexOf("module.tracking") >= 0) return true;
    return blPerms.indexOf(key) >= 0;
  }

  function blApi(path, opts) {
    opts = opts || {};
    var fetchOpts = Object.assign({ headers: {} }, opts);
    if (fetchOpts.body && typeof fetchOpts.body === "object") {
      fetchOpts.headers["Content-Type"] = "application/json";
      fetchOpts.body = JSON.stringify(fetchOpts.body);
    }
    return fetch(path, fetchOpts).then(function (r) {
      if (r.status === 401) { location.href = "/admin/login"; return null; }
      return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; }).catch(function () {
        return { ok: r.ok, status: r.status, data: {} };
      });
    }).catch(function () {
      return null;
    });
  }

  function blToast(msg) {
    var el = document.getElementById("toast");
    if (!el) { return; }
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(function () { el.classList.remove("show"); }, 2400);
  }

  function blEsc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function blFmtDate(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      return d.toLocaleString("tr-TR", { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch (e) { return iso; }
  }

  function blThemeSwatchColor(key) {
    var t = blThemes.find(function (x) { return x.key === key; });
    return t ? t.accent : "#888";
  }

  // ── Tema listesi ─────────────────────────────────────────
  function loadThemes() {
    return blApi("/api/biolink/themes").then(function (r) {
      if (!r || !r.ok) return;
      blThemes = r.data.themes || [];
      var sel = document.getElementById("bl-theme");
      if (sel) {
        sel.innerHTML = blThemes.map(function (t) {
          return '<option value="' + blEsc(t.key) + '">' + blEsc(t.name) + "</option>";
        }).join("");
      }
    });
  }

  // ── Sayfa listesi ────────────────────────────────────────
  function loadPages() {
    if (!blHas("tracking.biolink")) return Promise.resolve();
    return blApi("/api/biolink/pages").then(function (r) {
      if (!r || !r.ok) return;
      blPages = r.data.pages || [];
      renderPagesTable();
      var upd = document.getElementById("biolink-updated");
      if (upd) upd.textContent = "Son: " + new Date().toLocaleTimeString("tr-TR");
    });
  }

  function renderPagesTable() {
    var tb = document.getElementById("biolink-pages-table");
    if (!tb) return;
    if (!blPages.length) {
      tb.innerHTML = '<tr><td colspan="7" class="empty">Henüz sayfa yok</td></tr>';
      return;
    }
    tb.innerHTML = blPages.map(function (p) {
      var swatch = blThemeSwatchColor(p.theme);
      var statusCls = p.is_active ? "active" : "inactive";
      var statusLabel = p.is_active ? "Yayında" : "Pasif";
      return "<tr>" +
        "<td><strong>" + blEsc(p.title) + "</strong></td>" +
        '<td><a href="/p/' + blEsc(p.slug) + '" target="_blank" rel="noopener">/p/' + blEsc(p.slug) + "</a></td>" +
        '<td><span class="biolink-theme-swatch" style="background:' + swatch + ';"></span>' + blEsc((blThemes.find(function(t){return t.key===p.theme;})||{}).name || p.theme) + "</td>" +
        "<td>" + (p.view_count || 0) + "</td>" +
        "<td>" + (p.button_count || 0) + " buton / " + (p.total_clicks || 0) + " tık</td>" +
        '<td><span class="biolink-status-pill ' + statusCls + '">' + statusLabel + "</span></td>" +
        '<td style="white-space:nowrap;">' +
        '<button type="button" class="btn btn-sm" data-bl-edit="' + p.id + '">Düzenle</button> ' +
        '<button type="button" class="btn btn-sm" data-bl-dup="' + p.id + '">Kopyala</button> ' +
        '<button type="button" class="btn btn-danger btn-sm" data-bl-del="' + p.id + '">Sil</button>' +
        "</td></tr>";
    }).join("");

    tb.querySelectorAll("[data-bl-edit]").forEach(function (btn) {
      btn.onclick = function () { openEditorById(parseInt(btn.getAttribute("data-bl-edit"), 10)); };
    });
    tb.querySelectorAll("[data-bl-dup]").forEach(function (btn) {
      btn.onclick = function () {
        blApi("/api/biolink/pages/" + btn.getAttribute("data-bl-dup") + "/duplicate", { method: "POST" }).then(function (r) {
          if (r && r.ok) { blToast("Sayfa kopyalandı"); loadPages(); }
          else if (r) alert((r.data && r.data.error) || "Hata");
        });
      };
    });
    tb.querySelectorAll("[data-bl-del]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Bu sayfayı ve tüm butonlarını silmek istediğinize emin misiniz?")) return;
        var id = btn.getAttribute("data-bl-del");
        blApi("/api/biolink/pages/" + id, { method: "DELETE" }).then(function (r) {
          if (r && r.ok) {
            blToast("Sayfa silindi");
            if (blCurrentPage && String(blCurrentPage.id) === String(id)) closeEditor();
            loadPages();
          }
        });
      };
    });
  }

  // ── Editör ───────────────────────────────────────────────
  function openEditorById(id) {
    blApi("/api/biolink/pages/" + id).then(function (r) {
      if (r && r.ok) openEditor(r.data.page);
    });
  }

  function openEditor(page) {
    blCurrentPage = page;
    var box = document.getElementById("biolink-editor");
    if (box) box.style.display = "";
    document.getElementById("biolink-editor-title").textContent = "Sayfa Düzenle — " + page.title;
    document.getElementById("bl-title").value = page.title || "";
    document.getElementById("bl-slug").value = page.slug || "";
    document.getElementById("bl-theme").value = page.theme || "carbon";
    document.getElementById("bl-shape").value = page.button_shape || "pill";
    document.getElementById("bl-subtitle").value = page.subtitle || "";
    document.getElementById("bl-avatar").value = page.avatar_url || "";
    document.getElementById("bl-accent").value = page.accent_color || "#22d3a8";
    document.getElementById("bl-ga4-id").value = page.ga4_measurement_id || "";
    document.getElementById("bl-ga4-secret").value = "";
    document.getElementById("bl-is-active").checked = !!page.is_active;
    var link = document.getElementById("biolink-preview-link");
    if (link) link.href = "/p/" + page.slug;
    renderButtonsList(page.buttons || []);
    refreshPreview();
    loadStats(page.id);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeEditor() {
    blCurrentPage = null;
    var box = document.getElementById("biolink-editor");
    if (box) box.style.display = "none";
  }

  function refreshPreview() {
    if (!blCurrentPage) return;
    var frame = document.getElementById("biolink-preview-frame");
    if (frame) frame.src = "/p/" + blCurrentPage.slug + "?_=" + Date.now();
  }

  function createNewPage() {
    blApi("/api/biolink/pages", { method: "POST", body: { title: "Yeni Sayfa" } }).then(function (r) {
      if (r && r.ok) {
        blToast("Sayfa oluşturuldu, şimdi düzenleyebilirsiniz");
        loadPages();
        openEditor(r.data.page);
      } else if (r) alert((r.data && r.data.error) || "Oluşturulamadı");
    });
  }

  function savePage() {
    if (!blCurrentPage) return;
    var payload = {
      title: document.getElementById("bl-title").value.trim(),
      slug: document.getElementById("bl-slug").value.trim(),
      theme: document.getElementById("bl-theme").value,
      button_shape: document.getElementById("bl-shape").value,
      subtitle: document.getElementById("bl-subtitle").value,
      avatar_url: document.getElementById("bl-avatar").value.trim(),
      accent_color: document.getElementById("bl-accent").value,
      ga4_measurement_id: document.getElementById("bl-ga4-id").value.trim(),
      is_active: document.getElementById("bl-is-active").checked,
    };
    var secret = document.getElementById("bl-ga4-secret").value.trim();
    if (secret) payload.ga4_api_secret = secret;
    blApi("/api/biolink/pages/" + blCurrentPage.id, { method: "PUT", body: payload }).then(function (r) {
      if (r && r.ok) {
        blToast("Kaydedildi");
        blCurrentPage = r.data.page;
        document.getElementById("biolink-preview-link").href = "/p/" + blCurrentPage.slug;
        document.getElementById("biolink-editor-title").textContent = "Sayfa Düzenle — " + blCurrentPage.title;
        refreshPreview();
        loadPages();
      } else if (r) alert((r.data && r.data.error) || "Kaydedilemedi");
    });
  }

  // ── Butonlar ─────────────────────────────────────────────
  function renderButtonsList(buttons) {
    var box = document.getElementById("biolink-buttons-list");
    if (!box) return;
    if (!buttons.length) {
      box.innerHTML = '<p class="muted-sm">Henüz buton eklenmedi.</p>';
      return;
    }
    box.innerHTML = buttons.map(function (b, idx) {
      if (b.button_type === "heading") {
        return '<div class="biolink-btn-row heading-row" data-bl-btn="' + b.id + '">' +
          '<span class="drag-order"><button type="button" data-bl-up="' + b.id + '" ' + (idx === 0 ? "disabled" : "") + '>▲</button><button type="button" data-bl-down="' + b.id + '" ' + (idx === buttons.length - 1 ? "disabled" : "") + '>▼</button></span>' +
          '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Başlık / Ayraç yazısı">' +
          '<label style="font-size:0.72rem;display:flex;align-items:center;gap:0.25rem;"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"> Aktif</label>' +
          '<button type="button" class="btn btn-danger btn-sm" data-bl-btn-del="' + b.id + '">Sil</button>' +
          "</div>";
      }
      return '<div class="biolink-btn-row" data-bl-btn="' + b.id + '">' +
        '<span class="drag-order"><button type="button" data-bl-up="' + b.id + '" ' + (idx === 0 ? "disabled" : "") + '>▲</button><button type="button" data-bl-down="' + b.id + '" ' + (idx === buttons.length - 1 ? "disabled" : "") + '>▼</button></span>' +
        '<input value="' + blEsc(b.icon) + '" maxlength="4" data-bl-field="icon" data-bl-id="' + b.id + '" placeholder="🎁">' +
        '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Buton yazısı">' +
        '<input value="' + blEsc(b.url) + '" data-bl-field="url" data-bl-id="' + b.id + '" placeholder="https://…">' +
        '<label style="font-size:0.68rem;display:flex;align-items:center;gap:0.2rem;" title="Vurgulu (öne çıkan)"><input type="checkbox" ' + (b.highlight ? "checked" : "") + ' data-bl-field="highlight" data-bl-id="' + b.id + '"> ⭐</label>' +
        '<label style="font-size:0.72rem;display:flex;align-items:center;gap:0.25rem;"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"> Aktif</label>' +
        '<button type="button" class="btn btn-danger btn-sm" data-bl-btn-del="' + b.id + '">Sil</button>' +
        "</div>";
    }).join("");

    box.querySelectorAll("[data-bl-field]").forEach(function (input) {
      var evt = input.type === "checkbox" ? "change" : "blur";
      input.addEventListener(evt, function () {
        var id = input.getAttribute("data-bl-id");
        var field = input.getAttribute("data-bl-field");
        var value = input.type === "checkbox" ? input.checked : input.value;
        var payload = {};
        payload[field] = value;
        blApi("/api/biolink/buttons/" + id, { method: "PUT", body: payload }).then(function (r) {
          if (r && r.ok) {
            updateLocalButton(r.data.button);
            refreshPreview();
          } else if (r) { alert((r.data && r.data.error) || "Güncellenemedi"); }
        });
      });
    });
    box.querySelectorAll("[data-bl-btn-del]").forEach(function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute("data-bl-btn-del");
        blApi("/api/biolink/buttons/" + id, { method: "DELETE" }).then(function (r) {
          if (r && r.ok) {
            blCurrentPage.buttons = blCurrentPage.buttons.filter(function (b) { return String(b.id) !== String(id); });
            renderButtonsList(blCurrentPage.buttons);
            refreshPreview();
            loadPages();
          }
        });
      };
    });
    box.querySelectorAll("[data-bl-up]").forEach(function (btn) {
      btn.onclick = function () { moveButton(parseInt(btn.getAttribute("data-bl-up"), 10), -1); };
    });
    box.querySelectorAll("[data-bl-down]").forEach(function (btn) {
      btn.onclick = function () { moveButton(parseInt(btn.getAttribute("data-bl-down"), 10), 1); };
    });
  }

  function updateLocalButton(updated) {
    if (!blCurrentPage || !updated) return;
    blCurrentPage.buttons = (blCurrentPage.buttons || []).map(function (b) {
      return String(b.id) === String(updated.id) ? updated : b;
    });
  }

  function moveButton(buttonId, dir) {
    if (!blCurrentPage) return;
    var list = blCurrentPage.buttons.slice();
    var idx = list.findIndex(function (b) { return b.id === buttonId; });
    var newIdx = idx + dir;
    if (idx < 0 || newIdx < 0 || newIdx >= list.length) return;
    var tmp = list[idx];
    list[idx] = list[newIdx];
    list[newIdx] = tmp;
    blCurrentPage.buttons = list;
    renderButtonsList(list);
    blApi("/api/biolink/pages/" + blCurrentPage.id + "/buttons/reorder", {
      method: "POST",
      body: { order: list.map(function (b) { return b.id; }) },
    }).then(function () { refreshPreview(); loadPages(); });
  }

  function addButton() {
    if (!blCurrentPage) return;
    var type = document.getElementById("bl-new-btn-type").value;
    var icon = document.getElementById("bl-new-btn-icon").value.trim();
    var label = document.getElementById("bl-new-btn-label").value.trim();
    var url = document.getElementById("bl-new-btn-url").value.trim();
    if (!label) { alert("Buton yazısı gerekli."); return; }
    if (type === "link" && !url) { alert("Link butonu için URL gerekli."); return; }
    blApi("/api/biolink/pages/" + blCurrentPage.id + "/buttons", {
      method: "POST",
      body: { button_type: type, icon: icon, label: label, url: url },
    }).then(function (r) {
      if (r && r.ok) {
        blCurrentPage.buttons = blCurrentPage.buttons || [];
        blCurrentPage.buttons.push(r.data.button);
        renderButtonsList(blCurrentPage.buttons);
        document.getElementById("bl-new-btn-icon").value = "";
        document.getElementById("bl-new-btn-label").value = "";
        document.getElementById("bl-new-btn-url").value = "";
        refreshPreview();
        loadPages();
        blToast("Buton eklendi");
      } else if (r) alert((r.data && r.data.error) || "Eklenemedi");
    });
  }

  // ── İstatistikler ────────────────────────────────────────
  function loadStats(pageId) {
    blApi("/api/biolink/pages/" + pageId + "/stats").then(function (r) {
      var box = document.getElementById("biolink-stats");
      if (!box) return;
      if (!r || !r.ok) { box.innerHTML = '<p class="muted-sm">Yüklenemedi.</p>'; return; }
      var s = r.data;
      var rows = '<div class="biolink-stat-row"><span>Toplam görüntülenme</span><span class="val">' + (s.view_count || 0) + "</span></div>" +
        '<div class="biolink-stat-row"><span>Toplam tıklama</span><span class="val">' + (s.total_clicks || 0) + "</span></div>";
      if (s.buttons && s.buttons.length) {
        rows += s.buttons.map(function (b) {
          return '<div class="biolink-stat-row"><span>' + blEsc(b.label) + '</span><span class="val">' + b.click_count + "</span></div>";
        }).join("");
      }
      box.innerHTML = rows;
    });
  }

  // ── Event binding ────────────────────────────────────────
  function bindEvents() {
    var btnNew = document.getElementById("btn-biolink-new");
    if (btnNew) btnNew.onclick = createNewPage;
    var btnRefresh = document.getElementById("btn-biolink-refresh");
    if (btnRefresh) btnRefresh.onclick = loadPages;
    var btnSave = document.getElementById("btn-biolink-save");
    if (btnSave) btnSave.onclick = savePage;
    var btnClose = document.getElementById("btn-biolink-close");
    if (btnClose) btnClose.onclick = closeEditor;
    var btnAddBtn = document.getElementById("btn-biolink-add-button");
    if (btnAddBtn) btnAddBtn.onclick = addButton;
    var typeSel = document.getElementById("bl-new-btn-type");
    if (typeSel) {
      typeSel.onchange = function () {
        var urlInput = document.getElementById("bl-new-btn-url");
        var iconInput = document.getElementById("bl-new-btn-icon");
        var isHeading = typeSel.value === "heading";
        urlInput.style.display = isHeading ? "none" : "";
        iconInput.style.display = isHeading ? "none" : "";
      };
    }
  }

  window.MakroBiolink = {
    init: function () {
      if (blLoaded) return;
      blLoaded = true;
      bindEvents();
      loadThemes().then(loadPages);
    },
    setPermissions: function (perms) {
      blPerms = perms || [];
    },
    refresh: function () {
      loadPages();
    },
  };
})();
