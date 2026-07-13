(function () {
  "use strict";

  var blLoaded = false;
  var blPerms = [];
  var blPages = [];
  var blThemes = [];
  var blHeadingStyles = [];
  var blComposerHeadingStyle = "classic";
  var blTypes = [];
  var blAssets = { logos: [], banners: [], default_logo: "/static/biolink/logo/logo-400.png", default_banner: "/static/biolink/banners/banner-468x60.gif" };
  var blCurrentPage = null;
  var blComposerType = "link";
  var blEmojiTarget = null;
  var blPreviewTimer = null;
  var blStatsTimer = null;
  var blBlockSaveTimers = {};
  var blBlockLastSaved = {};
  var blBlockEventsBound = false;
  var BL_NONE = "__none__";

  var BL_EMOJIS = [
    "🔗", "💬", "✈️", "📸", "🎁", "🏆", "⚡", "🔥", "💎", "🎯",
    "📣", "🎰", "🃏", "⚽", "🏀", "💰", "🚀", "⭐", "✅", "🆕",
    "📞", "🛟", "💳", "🎉", "👑", "🦁", "🎮", "📱", "🌐", "❤️",
    "💚", "💙", "🟡", "🔴", "🟢", "▶️", "🎵", "📺", "🎫", "🤑"
  ];

  var BL_BRAND_TYPES = ["whatsapp", "telegram", "instagram", "twitter", "tiktok", "youtube"];

  var BL_SVG = {
    whatsapp: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>',
    telegram: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 0C8.741 0 8.333.014 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"/></svg>',
    twitter: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>',
    tiktok: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z"/></svg>',
    youtube: '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><path fill="currentColor" d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/></svg>',
  };

  function blPlatformIconHtml(type) {
    return BL_SVG[type] || "";
  }

  function blIsBrandType(type) {
    return BL_BRAND_TYPES.indexOf(type) >= 0;
  }

  var BL_PRESETS = {
    whatsapp: {
      label: "WhatsApp", color: "#25D366", icon: "",
      defaults: { label: "WhatsApp Destek", icon: "" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "WhatsApp Destek Hattı", full: false },
        { key: "url", label: "Telefon (ülke kodu ile)", placeholder: "905551234567", full: false },
        { key: "badge_text", label: "Ön mesaj (opsiyonel)", placeholder: "Merhaba, destek almak istiyorum", full: true },
      ],
    },
    telegram: {
      label: "Telegram", color: "#229ED9", icon: "",
      defaults: { label: "Telegram Kanalı", icon: "" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "Telegram VIP Grubu", full: false },
        { key: "url", label: "Kullanıcı adı (@ olmadan)", placeholder: "makrovip", full: false },
      ],
    },
    instagram: {
      label: "Instagram", color: "#E4405F", icon: "",
      defaults: { label: "Instagram", icon: "" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "Instagram'da Takip Et", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    twitter: {
      label: "X (Twitter)", color: "#ffffff", icon: "",
      defaults: { label: "X / Twitter", icon: "" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "X'te Takip Et", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    tiktok: {
      label: "TikTok", color: "#fe2c55", icon: "",
      defaults: { label: "TikTok", icon: "" },
      fields: [
        { key: "label", label: "Buton yazısı", placeholder: "TikTok'ta İzle", full: false },
        { key: "url", label: "Kullanıcı adı", placeholder: "makrovip", full: false },
      ],
    },
    youtube: {
      label: "YouTube", color: "#FF0000", icon: "",
      defaults: { label: "YouTube", icon: "" },
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

  function blSlugify(text) {
    text = String(text || "").trim().toLowerCase();
    text = text.replace(/ı/g, "i").replace(/ğ/g, "g").replace(/ü/g, "u")
      .replace(/ş/g, "s").replace(/ö/g, "o").replace(/ç/g, "c");
    text = text.replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    return text.slice(0, 64) || "sayfa";
  }

  function blHas(key) {
    if (!blPerms || !blPerms.length) return true;
    if (blPerms.indexOf("*") >= 0) return true;
    return blPerms.indexOf(key) >= 0 || blPerms.indexOf("module.biolink") >= 0;
  }

  function blApi(path, opts) {
    opts = opts || {};
    var fetchOpts = Object.assign({ headers: {} }, opts);
    if (fetchOpts.body instanceof FormData) {
      /* multipart — Content-Type tarayıcı ayarlar */
    } else if (fetchOpts.body && typeof fetchOpts.body === "object") {
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
      blHeadingStyles = r.data.heading_styles || [];
      var catSel = document.getElementById("bl-theme-cat");
      if (catSel) {
        var cats = [];
        blThemes.forEach(function (t) {
          if (t.category && cats.indexOf(t.category) < 0) cats.push(t.category);
        });
        var cur = catSel.value || "";
        catSel.innerHTML = '<option value="">Tüm kategoriler</option>' + cats.map(function (c) {
          return '<option value="' + blEsc(c) + '">' + blEsc(c) + "</option>";
        }).join("");
        catSel.value = cur;
        catSel.onchange = function () { renderThemeGallery(); };
      }
      renderThemeGallery();
    });
  }

  function renderThemeGallery() {
    var box = document.getElementById("bl-theme-gallery");
    var hidden = document.getElementById("bl-theme");
    var countEl = document.getElementById("bl-theme-count");
    var catSel = document.getElementById("bl-theme-cat");
    if (!box) return;
    var selected = (hidden && hidden.value) || "makrobet";
    var cat = catSel ? catSel.value : "";
    var list = blThemes.filter(function (t) { return !cat || t.category === cat; });
    if (countEl) countEl.textContent = list.length + " / " + blThemes.length + " tema";
    box.innerHTML = list.map(function (t) {
      var active = t.key === selected ? " active" : "";
      var a2 = t.accent2 || t.accent;
      return '<button type="button" class="bl-theme-card' + active + '" data-bl-theme-pick="' + blEsc(t.key) + '" title="' + blEsc(t.name) + '">' +
        '<span class="bl-theme-preview" style="background:' + blEsc(t.bg || "#111") + '">' +
        '<span class="bl-theme-btn-demo" style="background:' + blEsc(t.accent) + ';box-shadow:0 0 0 1px ' + blEsc(a2) + ';"></span>' +
        '<span class="bl-theme-btn-demo soft" style="border-color:' + blEsc(t.accent) + ';"></span>' +
        "</span>" +
        '<span class="bl-theme-name">' + blEsc(t.name) + "</span>" +
        '<span class="bl-theme-meta">' + blEsc(t.style || "classic") + (t.animated ? " · ★" : "") + "</span>" +
        "</button>";
    }).join("");
    box.querySelectorAll("[data-bl-theme-pick]").forEach(function (btn) {
      btn.onclick = function () {
        if (hidden) hidden.value = btn.getAttribute("data-bl-theme-pick");
        renderThemeGallery();
        schedulePreviewRefresh();
      };
    });
  }

  function blHeadingStyleName(key) {
    var h = blHeadingStyles.find(function (x) { return x.key === key; });
    return h ? h.name : key;
  }

  function renderHeadingStylePicker(selected, attrs) {
    attrs = attrs || "";
    var sel = selected || "classic";
    return '<div class="bl-heading-style-scroll" ' + attrs + '>' +
      blHeadingStyles.map(function (h) {
        var active = h.key === sel ? " active" : "";
        return '<button type="button" class="bl-hs-chip' + active + '" data-hs="' + blEsc(h.key) + '" title="' + blEsc(h.category) + '">' +
          '<span class="heading bl-hs-preview hs-' + blEsc(h.key) + '"><span class="hs-inner">Örnek</span></span>' +
          '<span class="bl-hs-label">' + blEsc(h.name) + "</span></button>";
      }).join("") +
      "</div>";
  }

  function loadAssets() {
    return blApi("/api/biolink/assets").then(function (r) {
      if (!r || !r.ok) return;
      blAssets = r.data || blAssets;
      renderAssetPickers();
    });
  }

  function blNoneAsset(kind) {
    return {
      key: "none",
      label: kind === "logo" ? "Logo yok" : "Banner yok",
      url: BL_NONE,
      custom: false,
      isNone: true,
    };
  }

  function blAssetChipHtml(a, type) {
    var isBanner = type === "banner";
    var val = isBanner
      ? ((document.getElementById("bl-banner") || {}).value || "")
      : ((document.getElementById("bl-avatar") || {}).value || "");
    var active = val === a.url ? " active" : "";
    var customCls = a.custom ? " custom" : "";
    var dataAttr = isBanner ? "data-bl-banner" : "data-bl-logo";
    var delBtn = a.custom
      ? '<button type="button" class="bl-asset-del" data-bl-asset-del="' + a.id + '" title="Sil">×</button>'
      : "";
    if (a.isNone || a.url === BL_NONE) {
      return '<div class="bl-asset-chip-wrap">' +
        '<button type="button" class="bl-asset-chip none' + (isBanner ? " banner" : "") + active + '" ' +
        dataAttr + '="' + BL_NONE + '" title="' + blEsc(a.label) + '">' +
        '<span class="bl-asset-none-icon">∅</span>' +
        '<span>' + blEsc(a.label) + "</span></button></div>";
    }
    return '<div class="bl-asset-chip-wrap">' +
      '<button type="button" class="bl-asset-chip' + (isBanner ? " banner" : "") + active + customCls + '" ' +
      dataAttr + '="' + blEsc(a.url) + '" title="' + blEsc(a.label) + '">' +
      '<img src="' + blEsc(a.url) + '" alt="">' +
      '<span>' + blEsc(a.label) + "</span></button>" + delBtn + "</div>";
  }

  function blBindAssetPickers(logoBox, bannerBox) {
    if (logoBox) {
      logoBox.querySelectorAll("[data-bl-logo]").forEach(function (btn) {
        btn.onclick = function () {
          document.getElementById("bl-avatar").value = btn.getAttribute("data-bl-logo");
          renderAssetPickers();
          schedulePreviewRefresh();
        };
      });
      logoBox.querySelectorAll("[data-bl-asset-del]").forEach(function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          blDeleteAsset(btn.getAttribute("data-bl-asset-del"), "logo");
        };
      });
    }
    if (bannerBox) {
      bannerBox.querySelectorAll("[data-bl-banner]").forEach(function (btn) {
        btn.onclick = function () {
          document.getElementById("bl-banner").value = btn.getAttribute("data-bl-banner");
          var layoutEl = document.getElementById("bl-banner-layout");
          if (layoutEl && btn.getAttribute("data-bl-banner") === BL_NONE) {
            layoutEl.value = "none";
          } else if (layoutEl && layoutEl.value === "none") {
            layoutEl.value = "top";
          }
          renderAssetPickers();
          schedulePreviewRefresh();
        };
      });
      bannerBox.querySelectorAll("[data-bl-asset-del]").forEach(function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          blDeleteAsset(btn.getAttribute("data-bl-asset-del"), "banner");
        };
      });
    }
  }

  function blUploadAsset(kind, file) {
    if (!file) return;
    var statusEl = document.getElementById(kind === "logo" ? "bl-logo-upload-status" : "bl-banner-upload-status");
    if (statusEl) statusEl.textContent = "Yükleniyor…";
    var fd = new FormData();
    fd.append("kind", kind);
    fd.append("file", file);
    fd.append("label", file.name || "Yüklediğim");
    blApi("/api/biolink/assets/upload", { method: "POST", body: fd }).then(function (r) {
      if (statusEl) statusEl.textContent = "";
      if (r && r.ok && r.data && r.data.asset) {
        blToast("Dosya yüklendi");
        var asset = r.data.asset;
        if (kind === "logo") document.getElementById("bl-avatar").value = asset.url;
        else document.getElementById("bl-banner").value = asset.url;
        return loadAssets().then(function () { schedulePreviewRefresh(); });
      }
      if (r) alert((r.data && r.data.error) || "Yüklenemedi");
    });
  }

  function blDeleteAsset(assetId, kind) {
    if (!assetId) return;
    if (!confirm("Bu yüklediğin dosya silinsin mi?")) return;
    blApi("/api/biolink/assets/" + assetId, { method: "DELETE" }).then(function (r) {
      if (!r || !r.ok) {
        if (r) alert((r.data && r.data.error) || "Silinemedi");
        return;
      }
      blToast("Silindi");
      var fieldId = kind === "logo" ? "bl-avatar" : "bl-banner";
      var field = document.getElementById(fieldId);
      var deletedUrl = "";
      (blAssets.logos || []).concat(blAssets.banners || []).forEach(function (a) {
        if (a.custom && String(a.id) === String(assetId)) deletedUrl = a.url;
      });
      if (field && field.value === deletedUrl) {
        field.value = kind === "logo" ? (blAssets.default_logo || "") : (blAssets.default_banner || "");
      }
      loadAssets().then(function () { schedulePreviewRefresh(); });
    });
  }

  function renderAssetPickers() {
    var logoBox = document.getElementById("bl-logo-picks");
    var bannerBox = document.getElementById("bl-banner-picks");

    if (logoBox) {
      logoBox.innerHTML = [blNoneAsset("logo")].concat(blAssets.logos || []).map(function (a) {
        return blAssetChipHtml(a, "logo");
      }).join("");
    }

    if (bannerBox) {
      bannerBox.innerHTML = [blNoneAsset("banner")].concat(blAssets.banners || []).map(function (a) {
        return blAssetChipHtml(a, "banner");
      }).join("");
    }

    blBindAssetPickers(logoBox, bannerBox);
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
    document.getElementById("bl-theme").value = page.theme || "makrobet";
    document.getElementById("bl-shape").value = page.button_shape || "pill";
    renderThemeGallery();
    document.getElementById("bl-subtitle").value = page.subtitle || "";
    document.getElementById("bl-avatar").value = page.hide_logo ? BL_NONE : (page.avatar_url || page.logo_url || blAssets.default_logo || "");
    var bannerEl = document.getElementById("bl-banner");
    if (bannerEl) bannerEl.value = page.hide_banner ? BL_NONE : (page.banner_url || blAssets.default_banner || "");
    var layoutEl = document.getElementById("bl-banner-layout");
    if (layoutEl) layoutEl.value = page.banner_layout || "top";
    document.getElementById("bl-accent").value = page.accent_color || "#ffd53e";
    document.getElementById("bl-ga4-id").value = page.ga4_measurement_id || "";
    document.getElementById("bl-ga4-secret").value = "";
    document.getElementById("bl-is-active").checked = !!page.is_active;
    var link = document.getElementById("biolink-preview-link");
    if (link) link.href = "/p/" + page.slug;
    renderAssetPickers();
    renderQuickPalette();
    setComposerType(blComposerType);
    renderButtonsList(page.buttons || []);
        refreshPreview();
        scheduleLoadStats();
    box.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function closeEditor() {
    blCurrentPage = null;
    var box = document.getElementById("biolink-editor");
    if (box) box.style.display = "none";
    hideEmojiPopover();
  }

  function blPreviewDraftParams() {
    var q = new URLSearchParams();
    q.set("preview", "1");
    var el;
    el = document.getElementById("bl-theme");
    if (el && el.value) q.set("theme", el.value);
    el = document.getElementById("bl-shape");
    if (el && el.value) q.set("button_shape", el.value);
    el = document.getElementById("bl-title");
    if (el) q.set("title", el.value);
    el = document.getElementById("bl-subtitle");
    if (el) q.set("subtitle", el.value);
    el = document.getElementById("bl-avatar");
    if (el) q.set("avatar_url", (el.value || "").trim());
    el = document.getElementById("bl-banner");
    if (el) q.set("banner_url", (el.value || "").trim());
    el = document.getElementById("bl-banner-layout");
    if (el && el.value) q.set("banner_layout", el.value);
    el = document.getElementById("bl-accent");
    if (el && el.value) q.set("accent_color", el.value);
    return q;
  }

  function schedulePreviewRefresh() {
    clearTimeout(blPreviewTimer);
    blPreviewTimer = setTimeout(refreshPreview, 500);
  }

  function scheduleLoadStats() {
    clearTimeout(blStatsTimer);
    blStatsTimer = setTimeout(function () {
      if (blCurrentPage) loadStats(blCurrentPage.id);
    }, 900);
  }

  function patchBlockCard(updated) {
    if (!updated) return false;
    var card = document.querySelector('.bl-block-card[data-bl-id="' + updated.id + '"]');
    if (!card) return false;
    var meta = card.querySelector(".bl-block-meta");
    if (updated.resolved_url) {
      var txt = "→ " + updated.resolved_url;
      if (meta) meta.textContent = txt;
      else {
        var main = card.querySelector(".bl-block-main");
        if (!main) return false;
        meta = document.createElement("div");
        meta.className = "bl-block-meta";
        meta.textContent = txt;
        main.appendChild(meta);
      }
    } else if (meta) {
      meta.remove();
    }
    return true;
  }

  function saveBlockField(id, field, value, input, isToggle) {
    var saveKey = id + ":" + field;
    if (!isToggle && blBlockLastSaved[saveKey] === value) return;
    var payload = {};
    payload[field] = value;
    blApi("/api/biolink/buttons/" + id, { method: "PUT", body: payload }).then(function (r) {
      if (r && r.ok) {
        blBlockLastSaved[saveKey] = value;
        updateLocalButton(r.data.button);
        if (field === "url" || field === "badge_text" || field === "label") {
          if (!patchBlockCard(r.data.button)) renderButtonsList(blCurrentPage.buttons);
        }
        schedulePreviewRefresh();
        scheduleLoadStats();
      } else {
        if (isToggle && input) input.checked = !input.checked;
        if (r) alert((r.data && r.data.error) || "Güncellenemedi");
      }
    });
  }

  function handleBlockFieldInput(input) {
    var id = input.getAttribute("data-bl-id");
    var field = input.getAttribute("data-bl-field");
    var value = input.type === "checkbox" ? input.checked : input.value;
    if (blCurrentPage && blCurrentPage.buttons) {
      blCurrentPage.buttons.forEach(function (b) {
        if (String(b.id) === String(id)) b[field] = value;
      });
    }
    if (input.type === "checkbox") {
      saveBlockField(id, field, value, input, true);
      schedulePreviewRefresh();
      return;
    }
    var key = id + ":" + field;
    clearTimeout(blBlockSaveTimers[key]);
    blBlockSaveTimers[key] = setTimeout(function () {
      saveBlockField(id, field, value, input, false);
    }, 450);
    schedulePreviewRefresh();
  }

  function refreshPreview() {
    if (!blCurrentPage) return;
    var frame = document.getElementById("biolink-preview-frame");
    if (!frame) return;
    var editor = document.getElementById("biolink-editor");
    if (editor && editor.style.display === "none") return;
    var q = blPreviewDraftParams();
    q.set("_", String(Date.now()));
    frame.src = "/p/" + encodeURIComponent(blCurrentPage.slug) + "?" + q.toString();
  }

  function createNewPage() {
    blApi("/api/biolink/pages", { method: "POST", body: { title: "Yeni Sayfa", theme: "makrobet" } }).then(function (r) {
      if (r && r.ok) {
        blToast("Sayfa oluşturuldu");
        loadPages();
        openEditor(r.data.page);
      } else if (r) alert((r.data && r.data.error) || "Oluşturulamadı");
    });
  }

  function savePage() {
    if (!blCurrentPage) return;
    var slugInput = document.getElementById("bl-slug");
    var rawSlug = slugInput ? slugInput.value.trim() : "";
    var slug = blSlugify(rawSlug);
    if (slugInput && rawSlug && slug !== rawSlug) {
      slugInput.value = slug;
      blToast("URL slug düzenlendi: " + slug);
    }
    var payload = {
      title: document.getElementById("bl-title").value.trim(),
      slug: slug,
      theme: document.getElementById("bl-theme").value,
      button_shape: document.getElementById("bl-shape").value,
      subtitle: document.getElementById("bl-subtitle").value,
      avatar_url: document.getElementById("bl-avatar").value.trim(),
      banner_url: (document.getElementById("bl-banner") || {}).value.trim(),
      banner_layout: (document.getElementById("bl-banner-layout") || {}).value || "top",
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
      var iconInner = blPlatformIconHtml(key) || ("<span>" + blEsc(p.icon || "🔗") + "</span>");
      return '<button type="button" class="bl-quick-chip' + active + '" data-bl-quick="' + key + '" style="--chip-color:' + p.color + '">' +
        '<span class="bl-q-icon">' + iconInner + '</span>' +
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
    if (!blIsBrandType(blComposerType) && blComposerType !== "heading") {
      html += '<div class="bl-field"><label>Emoji (opsiyonel)</label><div class="bl-emoji-row">' +
        '<input id="bl-new-icon" value="' + blEsc(defs.icon || p.icon || "") + '" maxlength="8" placeholder="🎁">' +
        '<button type="button" class="bl-emoji-btn" data-bl-emoji-target="bl-new-icon">😀</button></div></div>';
    } else if (blIsBrandType(blComposerType)) {
      html += '<div class="bl-field full"><p class="muted-sm" style="margin:0;font-size:0.75rem;">Resmi ' + blEsc(p.label) + ' ikonu otomatik kullanılır.</p></div>';
    }
    p.fields.forEach(function (f) {
      var val = defs[f.key] || "";
      var cls = f.full ? "bl-field full" : "bl-field";
      html += '<div class="' + cls + '"><label>' + blEsc(f.label) + '</label>' +
        '<input id="bl-new-' + f.key + '" value="' + blEsc(val) + '" placeholder="' + blEsc(f.placeholder || "") + '"></div>';
    });
    if (blComposerType === "heading") {
      html += '<div class="bl-field full"><label>Ayırıcı stili (' + blHeadingStyles.length + ')</label>' +
        renderHeadingStylePicker(blComposerHeadingStyle, 'id="bl-composer-hs"') + "</div>";
    }
    box.innerHTML = html;
    box.querySelectorAll("[data-bl-emoji-target]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        openEmojiPopover(btn.getAttribute("data-bl-emoji-target"), btn);
      };
    });
    var hsBox = document.getElementById("bl-composer-hs");
    if (hsBox) {
      hsBox.querySelectorAll("[data-hs]").forEach(function (btn) {
        btn.onclick = function () {
          blComposerHeadingStyle = btn.getAttribute("data-hs");
          renderComposerFields();
        };
      });
    }
  }

  function readComposerPayload() {
    var p = blPreset(blComposerType);
    var body = { button_type: blComposerType };
    if (blComposerType !== "heading") {
      var iconEl = document.getElementById("bl-new-icon");
      body.icon = iconEl ? iconEl.value.trim() : (p.icon || "");
    } else {
      body.heading_style = blComposerHeadingStyle || "classic";
    }
    if (blIsBrandType(blComposerType)) body.icon = "";
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
        schedulePreviewRefresh();
        loadPages();
        scheduleLoadStats();
        blToast("Blok eklendi");
      } else if (r) alert((r.data && r.data.error) || "Eklenemedi");
    });
  }

  function bindBlockListEvents() {
    if (blBlockEventsBound) return;
    var box = document.getElementById("biolink-buttons-list");
    if (!box) return;
    blBlockEventsBound = true;

    box.addEventListener("change", function (e) {
      var input = e.target.closest("[data-bl-field]");
      if (!input || input.type !== "checkbox") return;
      handleBlockFieldInput(input);
    });

    box.addEventListener("focusout", function (e) {
      var input = e.target.closest("[data-bl-field]");
      if (!input || input.type === "checkbox") return;
      var id = input.getAttribute("data-bl-id");
      var field = input.getAttribute("data-bl-field");
      var key = id + ":" + field;
      clearTimeout(blBlockSaveTimers[key]);
      if (blBlockLastSaved[key] === input.value) return;
      saveBlockField(id, field, input.value, input, false);
    });

    box.addEventListener("click", function (e) {
      var delBtn = e.target.closest("[data-bl-btn-del]");
      if (delBtn) {
        blApi("/api/biolink/buttons/" + delBtn.getAttribute("data-bl-btn-del"), { method: "DELETE" }).then(function (r) {
          if (r && r.ok) {
            blCurrentPage.buttons = blCurrentPage.buttons.filter(function (b) {
              return String(b.id) !== String(delBtn.getAttribute("data-bl-btn-del"));
            });
            renderButtonsList(blCurrentPage.buttons);
            schedulePreviewRefresh();
            loadPages();
            scheduleLoadStats();
          }
        });
        return;
      }
      var upBtn = e.target.closest("[data-bl-up]");
      if (upBtn) { moveButton(parseInt(upBtn.getAttribute("data-bl-up"), 10), -1); return; }
      var downBtn = e.target.closest("[data-bl-down]");
      if (downBtn) { moveButton(parseInt(downBtn.getAttribute("data-bl-down"), 10), 1); return; }

      var hsChip = e.target.closest("[data-bl-hs-for] [data-hs]");
      if (hsChip) {
        var scroller = hsChip.closest("[data-bl-hs-for]");
        var bid = scroller.getAttribute("data-bl-hs-for");
        var style = hsChip.getAttribute("data-hs");
        blApi("/api/biolink/buttons/" + bid, { method: "PUT", body: { heading_style: style } }).then(function (r) {
          if (r && r.ok) {
            updateLocalButton(r.data.button);
            renderButtonsList(blCurrentPage.buttons);
            schedulePreviewRefresh();
          } else if (r) alert((r.data && r.data.error) || "Stil güncellenemedi");
        });
        return;
      }

      var emojiBtn = e.target.closest("[data-bl-emoji-inline]");
      if (emojiBtn) {
        e.stopPropagation();
        var emId = emojiBtn.getAttribute("data-bl-emoji-inline");
        blEmojiTarget = "inline-" + emId;
        var pop = document.getElementById("bl-emoji-popover");
        if (!pop) return;
        pop.innerHTML = BL_EMOJIS.map(function (em) {
          return '<button type="button" data-bl-em="' + em + '">' + em + "</button>";
        }).join("");
        pop.hidden = false;
        var rect = emojiBtn.getBoundingClientRect();
        pop.style.top = Math.min(rect.bottom + 6, window.innerHeight - 230) + "px";
        pop.style.left = Math.min(rect.left, window.innerWidth - 290) + "px";
        pop.querySelectorAll("[data-bl-em]").forEach(function (emBtn) {
          emBtn.onclick = function () {
            blApi("/api/biolink/buttons/" + emId, { method: "PUT", body: { icon: emBtn.getAttribute("data-bl-em") } }).then(function (r) {
              if (r && r.ok) {
                updateLocalButton(r.data.button);
                var card = document.querySelector('.bl-block-card[data-bl-id="' + emId + '"] input[data-bl-field="icon"]');
                if (card) card.value = r.data.button.icon || "";
                schedulePreviewRefresh();
              }
            });
            hideEmojiPopover();
          };
        });
      }
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
        var hs = b.heading_style || "classic";
        return '<div class="' + cardCls + '" data-bl-id="' + b.id + '" style="--bl-color:' + meta.color + '">' + order +
          '<div class="bl-block-content">' +
          '<div class="bl-block-main">' +
          '<span class="bl-block-type-badge">' + meta.icon + " " + blEsc(meta.label) +
          ' · <em>' + blEsc(blHeadingStyleName(hs)) + "</em></span>" +
          '<div class="bl-block-fields heading-fields">' +
          '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Bölüm başlığı">' +
          '<div class="full"><label class="muted-sm">Ayırıcı stili</label>' +
          renderHeadingStylePicker(hs, 'data-bl-hs-for="' + b.id + '"') +
          "</div></div>" +
          (b.resolved_url ? '<div class="bl-block-meta">→ ' + blEsc(b.resolved_url) + "</div>" : "") +
          "</div>" +
          '<div class="bl-block-actions">' +
          '<label class="bl-toggle-pill"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"><span>Aktif</span></label>' +
          '<button type="button" class="btn btn-danger btn-sm bl-block-del" data-bl-btn-del="' + b.id + '">Sil</button>' +
          "</div></div></div>";
      }

      var urlLabel = fieldLabel(b.button_type, "url");
      var preset = blPreset(b.button_type);
      var fieldsHtml = "";

      if (blIsBrandType(b.button_type)) {
        fieldsHtml = '<div class="bl-block-fields brand">' +
          '<div class="bl-block-icon-col bl-brand-icon">' + blPlatformIconHtml(b.button_type) + "</div>" +
          '<div class="bl-block-input-stack">';
        (preset.fields || []).forEach(function (f) {
          var val = f.key === "label" ? b.label : f.key === "url" ? (b.url || "") : f.key === "badge_text" ? (b.badge_text || "") : "";
          fieldsHtml += '<div class="bl-block-field-row"><label class="bl-block-field-lbl">' + blEsc(f.label) + "</label>" +
            '<input value="' + blEsc(val) + '" data-bl-field="' + f.key + '" data-bl-id="' + b.id + '" placeholder="' + blEsc(f.placeholder || "") + '"></div>';
        });
        fieldsHtml += "</div></div>";
      } else {
        var badgeField = b.button_type === "bonus"
          ? '<input class="bl-field-span" value="' + blEsc(b.badge_text || "") + '" data-bl-field="badge_text" data-bl-id="' + b.id + '" placeholder="' + blEsc(fieldLabel(b.button_type, "badge_text")) + '">'
          : "";
        var iconCell = '<div class="bl-icon-cell"><input value="' + blEsc(b.icon || meta.icon) + '" maxlength="8" data-bl-field="icon" data-bl-id="' + b.id + '">' +
          '<button type="button" data-bl-emoji-inline="' + b.id + '">😀</button></div>';
        fieldsHtml = '<div class="bl-block-fields">' +
          iconCell +
          '<input value="' + blEsc(b.label) + '" data-bl-field="label" data-bl-id="' + b.id + '" placeholder="Başlık">' +
          badgeField +
          '<input class="bl-field-span" value="' + blEsc(b.url || "") + '" data-bl-field="url" data-bl-id="' + b.id + '" placeholder="' + blEsc(urlLabel) + '">' +
          "</div>";
      }

      var badgeIcon = blPlatformIconHtml(b.button_type) || blEsc(meta.icon || "🔗");
      return '<div class="' + cardCls + '" data-bl-id="' + b.id + '" style="--bl-color:' + meta.color + '">' + order +
        '<div class="bl-block-content">' +
        '<div class="bl-block-main">' +
        '<span class="bl-block-type-badge">' + badgeIcon + " " + blEsc(meta.label) + "</span>" +
        fieldsHtml +
        (b.resolved_url ? '<div class="bl-block-meta">→ ' + blEsc(b.resolved_url) + "</div>" : "") +
        "</div>" +
        '<div class="bl-block-actions">' +
        '<label class="bl-toggle-pill" title="Öne çıkar"><input type="checkbox" ' + (b.highlight ? "checked" : "") + ' data-bl-field="highlight" data-bl-id="' + b.id + '"><span>⭐ Öne çıkar</span></label>' +
        '<label class="bl-toggle-pill"><input type="checkbox" ' + (b.is_active ? "checked" : "") + ' data-bl-field="is_active" data-bl-id="' + b.id + '"><span>Aktif</span></label>' +
        '<button type="button" class="btn btn-danger btn-sm bl-block-del" data-bl-btn-del="' + b.id + '">Sil</button>' +
        "</div></div></div>";
    }).join("");

    bindBlockListEvents();
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
    }).then(function () { schedulePreviewRefresh(); loadPages(); });
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
    var logoFile = document.getElementById("bl-logo-file");
    var bannerFile = document.getElementById("bl-banner-file");
    var btnLogoUp = document.getElementById("btn-bl-upload-logo");
    var btnBannerUp = document.getElementById("btn-bl-upload-banner");
    if (btnLogoUp && logoFile) btnLogoUp.onclick = function () { logoFile.click(); };
    if (btnBannerUp && bannerFile) btnBannerUp.onclick = function () { bannerFile.click(); };
    if (logoFile) {
      logoFile.addEventListener("change", function () {
        if (logoFile.files && logoFile.files[0]) blUploadAsset("logo", logoFile.files[0]);
        logoFile.value = "";
      });
    }
    if (bannerFile) {
      bannerFile.addEventListener("change", function () {
        if (bannerFile.files && bannerFile.files[0]) blUploadAsset("banner", bannerFile.files[0]);
        bannerFile.value = "";
      });
    }
    ["bl-title", "bl-subtitle", "bl-avatar", "bl-banner", "bl-accent"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", function () {
        if (id === "bl-avatar" || id === "bl-banner") renderAssetPickers();
        schedulePreviewRefresh();
      });
    });
    var shapeEl = document.getElementById("bl-shape");
    if (shapeEl) shapeEl.addEventListener("change", schedulePreviewRefresh);
    var layoutEl = document.getElementById("bl-banner-layout");
    if (layoutEl) {
      layoutEl.addEventListener("change", function () {
        var bannerEl = document.getElementById("bl-banner");
        if (layoutEl.value === "none" && bannerEl) {
          bannerEl.value = BL_NONE;
        } else if (layoutEl.value !== "none" && bannerEl && bannerEl.value === BL_NONE) {
          bannerEl.value = blAssets.default_banner || "";
        }
        renderAssetPickers();
        schedulePreviewRefresh();
      });
    }
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
      bindBlockListEvents();
      renderQuickPalette();
      setComposerType("whatsapp");
      loadThemes();
      loadAssets();
    },
    onShow: function () {
      if (!blLoaded) this.init();
      loadPages();
    },
    setPermissions: function (perms) { blPerms = perms || []; },
    refresh: loadPages,
  };
})();
