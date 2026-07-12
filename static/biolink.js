(function () {
  "use strict";

  var blLoaded = false;
  var blPerms = [];
  var blPages = [];
  var blThemes = [];
  var blTypes = [];
  var blCurrentPage = null;
  var blComposerType = "link";
  var blEmojiTarget = null;

  var BL_EMOJIS = [
    "🔗", "💬", "✈️", "📸", "🎁", "🏆", "⚡", "🔥", "💎", "🎯",
    "📣", "🎰", "🃏", "⚽", "🏀", "💰", "🚀", "⭐", "✅", "🆕",
    "📞", "🛟", "💳", "🎉", "👑", "🦁", "🎮", "📱", "🌐", "❤️",
    "💚", "💙", "🟡", "🔴", "🟢", "▶️", "🎵", "📺", "🎫", "🤑"
  ];

  var BL_PRESETS = {
    whatsapp: {
      label: "WhatsApp", color: "#25D366", icon: "💬",
      defaults: { label: "WhatsApp Destek", icon: "💬" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "WhatsApp Destek Hattı", full: false },
        { key: "url", label: "Telefon (ülke kodu ile)", placeholder: "905551234567", full: false },
        { key: "badge_text", label: "Ön mesaj (opsiyonel)", placeholder: "Merhaba, destek almak istiyorum", full: true },
      ],
    },
    telegram: {
      label: "Telegram", color: "#229ED9", icon: "✈️",
      defaults: { label: "Telegram Kanalı", icon: "✈️" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "Telegram VIP Grubu", full: false },
        { key: "url", label: "Kullanıcı adı (@ olmadan)", placeholder: "makrovip", full: false },
      ],
    },
    instagram: {
      label: "Instagram", color: "#E4405F", icon: "📸",
      defaults: { label: "Instagram", icon: "📸" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "Instagram'da Takip Et", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    twitter: {
      label: "X (Twitter)", color: "#e7e9ea", icon: "𝕏",
      defaults: { label: "X / Twitter", icon: "𝕏" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "X'te Takip Et", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    tiktok: {
      label: "TikTok", color: "#fe2c55", icon: "🎵",
      defaults: { label: "TikTok", icon: "🎵" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "TikTok'ta İzle", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    youtube: {
      label: "YouTube", color: "#FF0000", icon: "▶️",
      defaults: { label: "YouTube", icon: "▶️" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "YouTube Kanalı", full: false },
        { key: "url", label: "Kanal linki veya @kullanıcı", placeholder: "https://youtube.com/@makrovip", full: true },
      ],
    },
    bonus: {
      label: "Bonus / Promo", color: "#f5c451", icon: "🎁",
      defaults: { label: "3.000 TL Deneme Bonusu", icon: "🎁", badge_text: "YENİ", highlight: true },
      fields: [
        { key: "label", label: "Promo başlığı", placeholder: "500.000 TL Slot Turnuvası", full: false },
        { key: "badge_text", label: "Etiket / tutar", placeholder: "3.000 TL", full: false },
        { key: "url", label: "Promo linki", placeholder: "https://makrobet804.com/…", full: true },
      ],
    },
    link: {
      label: "Özel Link", color: "#6366f1", icon: "🔗",
      defaults: { label: "Siteye Git", icon: "🔗" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "Resmi Site", full: false },
        { key: "url", label: "URL", placeholder: "https://makrogir.com", full: true },
      ],
    },
    heading: {
      label: "Bölüm Başlığı", color: "#94a3b8", icon: "📌",
      defaults: { label: "🏆 Aktif Etkinlikler" },
      fields: [
        { key: "label", label: "Başlık metni", placeholder: "🏆 Aktif Etkinlikler", full: true },
      ],
    },
  };

  function blHas(key) {
    if (!blPerms || !blPerms.length) return true;
    if (blPerms.indexOf("*") >= 0) return true;
    if (blPerms.indexOf("module.biolink") >= 0) return true;
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
    }).catch(function () { return null; });
  }

  function blToast(msg) {
    var el = document.getElementById("toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(function () { el.classList.remove("show"); }, 2400);
  }

  function blEsc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function blPreset(type) {
    return BL_PRESETS[type] || BL_PRESETS.link;
  }

  function blTypeMeta(type) {
    var p = blPreset(type);
    return { key: type, label: p.label, color: p.color, icon: p.icon };
  }

  function blThemeSwatchColor(key) {
    var t = blThemes.find(function (x) { return x.key === key; });
    return t ? t.accent : "#888";
  }

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

  function loadPages() {
    if (!blHas("biolink.pages")) return Promise.resolve();
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
      return "<tr>" +
        "<td><strong>" + blEsc(p.title) + "</strong></td>" +
        '<td><a href="/p/' + blEsc(p.slug) + '" target="_blank" rel="noopener">/p/' + blEsc(p.slug) + "</a></td>" +
        '<td><span class="biolink-theme-swatch" style="background:' + swatch + ';"></span>' + blEsc((blThemes.find(function (t) { return t.key === p.theme; }) || {}).name || p.theme) + "</td>" +
        "<td>" + (p.view_count || 0) + "</td>" +
        "<td>" + (p.button_count || 0) + " blok / " + (p.total_clicks || 0) + " tık</td>" +
        '<td><span class="biolink-status-pill ' + statusCls + '">' + (p.is_active ? "Yayında" : "Pasif") + "</span></td>" +
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
        if (!confirm("Bu sayfayı ve tüm bloklarını silmek istediğinize emin misiniz?")) return;
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

  function openEditorById(id) {
    blApi("/api/biolink/pages/" + id).then(function (r) {
      if (r && r.ok) openEditor(r.data.page);
    });
  }

  function openEditor(page) {
    blCurrentPage = page;
    var box = document.getElementById("biolink-editor");
    if (box) box.style.display = "";
    document.getElementById("biolink-editor-title").textContent = "Studio — " + page.title;
    document.getElementById("bl-title").value = page.title || "";
    document.getElementById("bl-slug").value = page.slug || "";
    document.getElementById("bl-theme").value = page.theme || "makrovip";
    document.getElementById("bl-shape").value = page.button_shape || "pill";
    document.getElementById("bl-subtitle").value = page.subtitle || "";
    document.getElementById("bl-avatar").value = page.avatar_url || "";
    document.getElementById("bl-accent").value = page.accent_color || "#d4af37";
    document.getElementById("bl-ga4-id").value = page.ga4_measurement_id || "";
    document.getElementById("bl-ga4-secret").value = "";
    document.getElementById("bl-is-active").checked = !!page.is_active;
    var link = document.getElementById("biolink-preview-link");
    if (link) link.href = "/p/" + page.slug;
    renderQuickPalette();
    setComposerType(blComposerType);
    renderButtonsList(page.buttons || []);
    refreshPreview();
    loadStats(page.id);
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeEditor() {
    blCurrentPage = null;
    var box = document.getElementById("biolink-editor");
    if (box) box.style.display = "none";
    hideEmojiPopover();
  }

  function refreshPreview() {
    if (!blCurrentPage) return;
    var frame = document.getElementById("biolink-preview-frame");
    if (frame) frame.src = "/p/" + blCurrentPage.slug + "?_=" + Date.now();
  }

  function createNewPage() {
    blApi("/api/biolink/pages", { method: "POST", body: { title: "Yeni Sayfa", theme: "makrovip" } }).then(function (r) {
      if (r && r.ok) {
        blToast("Sayfa oluşturuldu");
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
        document.getElementById("biolink-editor-title").textContent = "Studio — " + blCurrentPage.title;
        refreshPreview();
        loadPages();
      } else if (r) alert((r.data && r.data.error) || "Kaydedilemedi");
    });
  }

  // ── Quick palette & composer ─────────────────────────────
  function renderQuickPalette() {
    var box = document.getElementById("bl-quick-palette");
    if (!box) return;
    var order = ["whatsapp", "telegram", "instagram", "twitter", "bonus", "link", "youtube", "tiktok", "heading"];
    box.innerHTML = order.map(function (key) {
      var p = blPreset(key);
      var active = key === blComposerType ? " active" : "";
      return '<button type="button" class="bl-quick-chip' + active + '" data-bl-quick="' + key + '" style="--chip-color:' + p.color + '">' +
        '<span class="bl-q-icon">' + p.icon + '</span>' +
        '<span class="bl-q-label">' + blEsc(p.label) + "</span></button>";
    }).join("");
    box.querySelectorAll("[data-bl-quick]").forEach(function (btn) {
      btn.onclick = function () { setComposerType(btn.getAttribute("data-bl-quick")); };
    });
  }

  function setComposerType(type) {
    blComposerType = type || "link";
    renderQuickPalette();
    var p = blPreset(blComposerType);
    var labelEl = document.getElementById("bl-composer-type-label");
    var hintEl = document.getElementById("bl-composer-hint");
    if (labelEl) labelEl.textContent = p.label;
    if (hintEl) {
      hintEl.textContent = blComposerType === "heading" ? "Sayfada ayraç / bölüm başlığı"
        : blComposerType === "bonus" ? "Promo kartı — etiket + link"
        : blComposerType === "whatsapp" ? "wa.me linki otomatik oluşturulur"
        : "Hedef otomatik formatlanır";
    }
    renderComposerFields();
  }

  function renderComposerFields() {
    var box = document.getElementById("bl-composer-fields");
    if (!box) return;
    var p = blPreset(blComposerType);
    var defs = p.defaults || {};
    var html = "";
    if (blComposerType !== "heading") {
      html += '<div class="bl-field"><label>Emoji</label><div class="bl-emoji-row">' +
        '<input id="bl-new-icon" value="' + blEsc(defs.icon || p.icon) + '" maxlength="8" placeholder="🎁">' +
        '<button type="button" class="bl-emoji-btn" data-bl-emoji-target="bl-new-icon">😀</button></div></div>';
    }
    p.fields.forEach(function (f) {
      var val = defs[f.key] || "";
      var cls = f.full ? "bl-field full" : "bl-field";
      html += '<div class="' + cls + '"><label>' + blEsc(f.label) + '</label>' +
        '<input id="bl-new-' + f.key + '" value="' + blEsc(val) + '" placeholder="' + blEsc(f.placeholder || "") + '"></div>';
    });
    box.innerHTML = html;
    box.querySelectorAll("[data-bl-emoji-target]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        openEmojiPopover(btn.getAttribute("data-bl-emoji-target"), btn);
      };
    });
  }

  function readComposerPayload() {
    var p = blPreset(blComposerType);
    var body = { button_type: blComposerType };
    if (blComposerType !== "heading") {
      var iconEl = document.getElementById("bl-new-icon");
      body.icon = iconEl ? iconEl.value.trim() : p.icon;
    }
    p.fields.forEach(function (f) {
      var el = document.getElementById("bl-new-" + f.key);
      body[f.key] = el ? el.value.trim() : "";
    });
    if (blComposerType === "bonus") body.highlight = true;
    return body;
  }

  function addButton() {
    if (!blCurrentPage) return;
    var body = readComposerPayload();
    if (!body.label) { alert("Başlık / etiket gerekli."); return; }
    if (blComposerType !== "heading" && !body.url) {
      alert("Hedef alanı gerekli.");
      return;
    }
    blApi("/api/biolink/pages/" + blCurrentPage.id + "/buttons", { method: "POST", body: body }).then(function (r) {
      if (r && r.ok) {
        blCurrentPage.buttons = blCurrentPage.buttons || [];
        blCurrentPage.buttons.push(r.data.button);
        renderButtonsList(blCurrentPage.buttons);
        renderComposerFields();
        refreshPreview();
        loadPages();
        loadStats(blCurrentPage.id);
        blToast("Blok eklendi");
      } else if (r) alert((r.data && r.data.error) || "Eklenemedi");
    });
  }

  // ── Emoji popover ────────────────────────────────────────
  function openEmojiPopover(targetId, anchor) {
    blEmojiTarget = targetId;
    var pop = document.getElementById("bl-emoji-popover");
    if (!pop) return;
    pop.innerHTML = BL_EMOJIS.map(function (em) {
      return '<button type="button" data-bl-em="' + em + '">' + em + "</button>";
    }).join("");
    pop.hidden = false;
    var rect = anchor.getBoundingClientRect();
    pop.style.top = Math.min(rect.bottom + 6, window.innerHeight - 230) + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 290) + "px";
    pop.querySelectorAll("[data-bl-em]").forEach(function (btn) {
      btn.onclick = function () {
        var el = document.getElementById(blEmojiTarget);
        if (el) el.value = btn.getAttribute("data-bl-em");
        hideEmojiPopover();
      };
    });
  }

  function hideEmojiPopover() {
    var pop = document.getElementById("bl-emoji-popover");
    if (pop) pop.hidden = true;
    blEmojiTarget = null;
  }

  // ── Block list ───────────────────────────────────────────
  function fieldLabel(type, key) {
    var p = blPreset(type);
    var f = (p.fields || []).find(function (x) { return x.key === key; });
    return f ? f.label : key;
  }

  function renderButtonsList(buttons) {
    var box = document.getElementById("biolink-buttons-list");
    if (!box) return;
    if (!buttons.length) {
      box.innerHTML = '<p class="muted-sm">Henüz blok eklenmedi. Yukarıdan platform seçip ekleyin.</p>';
      return;
    }
    box.innerHTML = buttons.map(function (b, idx) {
      var meta = blTypeMeta(b.button_type || "link");
      var isHeading = b.button_type === "heading";
      var cardCls = isHeading ? "bl-block-card heading-card" : "bl-block-card";
      var order = '<div class="bl-block-order">' +
        '<button type="button" data-bl-up="' + b.id + '" ' + (idx === 0 ? "disabled" : "") + '>▲</button>' +
        '<button type="button" data-bl-down="' + b.id + '" ' + (idx === buttons.length - 1 ? "disabled" : "") + ">▼</button></div>";

      if (isHeading) {
        return '<div class="' + cardCls + '" style="--bl-color:' + meta.color + '">' + order +
          '<div class="bl-block-main">' +
          '<span class="bl-block-type-badge">' + meta.icon + " " + blEsc(meta.label) + "</span>" +
          '<div class="bl-block-fields heading-fields">' +
          '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Bölüm başlığı">' +
          "</div></div>" +
          '<div class="bl-block-actions">' +
          '<label class="bl-toggle-pill"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"> Aktif</label>' +
          '<button type="button" class="btn btn-danger btn-sm" data-bl-btn-del="' + b.id + '">Sil</button></div></div>';
      }

      var urlLabel = fieldLabel(b.button_type, "url");
      var badgeField = (b.button_type === "whatsapp" || b.button_type === "bonus")
        ? '<input value="' + blEsc(b.badge_text || "") + '" data-bl-field="badge_text" data-bl-id="' + b.id + '" placeholder="' + blEsc(fieldLabel(b.button_type, "badge_text")) + '">'
        : "";

      return '<div class="' + cardCls + '" style="--bl-color:' + meta.color + '">' + order +
        '<div class="bl-block-main">' +
        '<span class="bl-block-type-badge">' + meta.icon + " " + blEsc(meta.label) + "</span>" +
        '<div class="bl-block-fields">' +
        '<div class="bl-icon-cell"><input value="' + blEsc(b.icon || meta.icon) + '" maxlength="8" data-bl-field="icon" data-bl-id="' + b.id + '">' +
        '<button type="button" data-bl-emoji-inline="' + b.id + '">😀</button></div>' +
        '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Başlık">' +
        '<input value="' + blEsc(b.url || "") + '" data-bl-field="url" data-bl-id="' + b.id + '" placeholder="' + blEsc(urlLabel) + '" style="grid-column:1/-1">' +
        (badgeField ? badgeField.replace('style="grid-column:1/-1"', 'style="grid-column:1/-1"') : "") +
        "</div>" +
        (b.resolved_url ? '<div class="bl-block-meta">→ ' + blEsc(b.resolved_url) + "</div>" : "") +
        "</div>" +
        '<div class="bl-block-actions">' +
        '<div class="bl-block-toggles">' +
        '<label class="bl-toggle-pill" title="Öne çıkar"><input type="checkbox" ' + (b.highlight ? "checked" : "") + ' data-bl-field="highlight" data-bl-id="' + b.id + '"> ⭐</label>' +
        '<label class="bl-toggle-pill"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"> Aktif</label>' +
        "</div>" +
        '<button type="button" class="btn btn-danger btn-sm" data-bl-btn-del="' + b.id + '">Sil</button></div></div>';
    }).join("");

    bindBlockEvents(box);
  }

  function bindBlockEvents(box) {
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
            if (field === "url" || field === "badge_text" || field === "label") {
              renderButtonsList(blCurrentPage.buttons);
            }
            refreshPreview();
            loadStats(blCurrentPage.id);
          } else if (r) alert((r.data && r.data.error) || "Güncellenemedi");
        });
      });
    });
    box.querySelectorAll("[data-bl-btn-del]").forEach(function (btn) {
      btn.onclick = function () {
        blApi("/api/biolink/buttons/" + btn.getAttribute("data-bl-btn-del"), { method: "DELETE" }).then(function (r) {
          if (r && r.ok) {
            blCurrentPage.buttons = blCurrentPage.buttons.filter(function (b) {
              return String(b.id) !== String(btn.getAttribute("data-bl-btn-del"));
            });
            renderButtonsList(blCurrentPage.buttons);
            refreshPreview();
            loadPages();
            loadStats(blCurrentPage.id);
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
    box.querySelectorAll("[data-bl-emoji-inline]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var id = btn.getAttribute("data-bl-emoji-inline");
        blEmojiTarget = "inline-" + id;
        var pop = document.getElementById("bl-emoji-popover");
        if (!pop) return;
        pop.innerHTML = BL_EMOJIS.map(function (em) {
          return '<button type="button" data-bl-em="' + em + '">' + em + "</button>";
        }).join("");
        pop.hidden = false;
        var rect = btn.getBoundingClientRect();
        pop.style.top = Math.min(rect.bottom + 6, window.innerHeight - 230) + "px";
        pop.style.left = Math.min(rect.left, window.innerWidth - 290) + "px";
        pop.querySelectorAll("[data-bl-em]").forEach(function (emBtn) {
          emBtn.onclick = function () {
            blApi("/api/biolink/buttons/" + id, { method: "PUT", body: { icon: emBtn.getAttribute("data-bl-em") } }).then(function (r) {
              if (r && r.ok) {
                updateLocalButton(r.data.button);
                renderButtonsList(blCurrentPage.buttons);
                refreshPreview();
              }
            });
            hideEmojiPopover();
          };
        });
      };
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

  function loadStats(pageId) {
    blApi("/api/biolink/pages/" + pageId + "/stats").then(function (r) {
      var box = document.getElementById("biolink-stats");
      if (!box) return;
      if (!r || !r.ok) { box.innerHTML = '<p class="muted-sm">Yüklenemedi.</p>'; return; }
      var s = r.data;
      var html = '<div class="biolink-stats-grid">' +
        '<div class="biolink-stat-card"><div class="lbl">Görüntülenme</div><div class="val">' + (s.view_count || 0) + "</div></div>" +
        '<div class="biolink-stat-card"><div class="lbl">Toplam tıklama</div><div class="val">' + (s.total_clicks || 0) + "</div></div></div>";
      if (s.buttons && s.buttons.length) {
        html += '<div class="biolink-stat-rows">' + s.buttons.map(function (b) {
          return '<div class="biolink-stat-row"><span>' + blEsc(b.label) + '</span><span class="val">' + b.click_count + "</span></div>";
        }).join("") + "</div>";
      }
      box.innerHTML = html;
    });
  }

  function bindEvents() {
    document.getElementById("btn-biolink-new").onclick = createNewPage;
    document.getElementById("btn-biolink-refresh").onclick = loadPages;
    document.getElementById("btn-biolink-save").onclick = savePage;
    document.getElementById("btn-biolink-close").onclick = closeEditor;
    document.getElementById("btn-biolink-add-button").onclick = addButton;
    document.addEventListener("click", function (e) {
      if (!e.target.closest("#bl-emoji-popover") && !e.target.closest(".bl-emoji-btn") && !e.target.closest("[data-bl-emoji-inline]")) {
        hideEmojiPopover();
      }
    });
  }

  window.MakroBiolink = {
    init: function () {
      if (blLoaded) return;
      blLoaded = true;
      bindEvents();
      renderQuickPalette();
      setComposerType("whatsapp");
      loadThemes();
    },
    onShow: function () {
      if (!blLoaded) this.init();
      loadPages();
    },
    setPermissions: function (perms) { blPerms = perms || []; },
    refresh: loadPages,
  };
})();
