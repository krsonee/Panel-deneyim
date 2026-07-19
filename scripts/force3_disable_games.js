/**
 * Bizzocazino — Forcelab Api -3 oyunlarını toplu kapat
 *
 * KULLANIM:
 * 1) Admin panelde Oyunlar sayfasına gir
 * 2) İstediğin filtreleri uygula (Source = Forcelab Api -3 vb.)
 * 3) Bu dosyanın tamamını kopyala → tarayıcıda F12 → Console → yapıştır → Enter
 * 4) Sağ altta çıkan "Force3 Kapat — BAŞLAT" butonuna bas
 * 5) Durdurmak için "DURDUR"
 *
 * Ne yapar (her eşleşen satır):
 *   kalem (Edit) → Status/Mobile/Featured/... açık toggle'ları KAPAT → Save Changes
 *   sonra sonraki satır / sonraki sayfa
 */
(function () {
  "use strict";

  const CFG = {
    sourceMatch: /forcelab\s*api\s*-?\s*3/i,
    // Modal içindeki kapatılacak switch etiketleri (2. görseldeki kutu)
    toggleLabels: ["Featured", "Status", "Freespins", "Lobby", "Tables", "Mobile"],
    delayMs: 700, // yavaşlatmak için artır (1000–1500)
    maxPages: 200,
  };

  let STOP = false;
  let RUNNING = false;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function log(...a) {
    console.log("%c[Force3]", "color:#a78bfa;font-weight:bold", ...a);
    const el = document.getElementById("f3-status");
    if (el) el.textContent = a.map(String).join(" ");
  }

  function visible(el) {
    if (!el) return false;
    const s = getComputedStyle(el);
    return s.display !== "none" && s.visibility !== "hidden" && el.offsetParent !== null;
  }

  function textOf(el) {
    return (el?.innerText || el?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function findModal() {
    const nodes = [
      ...document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Dialog"]'),
    ].filter(visible);
    for (const n of nodes) {
      if (/edit\s*game/i.test(textOf(n))) return n;
    }
    // başlıkta Edit Game geçen en yakın panel
    for (const h of document.querySelectorAll("h1,h2,h3,h4,.modal-title,[class*='title']")) {
      if (/edit\s*game/i.test(textOf(h))) {
        return (
          h.closest('[role="dialog"]') ||
          h.closest(".modal") ||
          h.closest('[class*="Modal"]') ||
          h.parentElement?.parentElement
        );
      }
    }
    return null;
  }

  function clickEl(el) {
    if (!el) return false;
    el.scrollIntoView({ block: "center", inline: "nearest" });
    el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
    if (typeof el.click === "function") el.click();
    return true;
  }

  function isSwitchOn(el) {
    if (!el) return false;
    if (el.getAttribute("aria-checked") === "true") return true;
    if (el.getAttribute("aria-checked") === "false") return false;
    if (el.type === "checkbox") return !!el.checked;
    if (el.classList.contains("bg-primary") || el.classList.contains("checked")) return true;
    // mor/aktif görünüm: genelde translate-x veya peer-checked
    const kn = el.querySelector('[class*="translate"], span, div');
    const cls = (el.className || "") + " " + (kn?.className || "");
    if (/translate-x-(4|5|6|full)|bg-(primary|purple|violet|indigo)/i.test(cls)) return true;
    return false;
  }

  function findTogglesInModal(modal) {
    const found = [];
    const scope = modal || document;

    // 1) role=switch
    for (const sw of scope.querySelectorAll('[role="switch"]')) {
      if (!visible(sw)) continue;
      const label =
        sw.getAttribute("aria-label") ||
        textOf(sw.closest("label") || sw.parentElement) ||
        "";
      found.push({ el: sw, label });
    }

    // 2) checkbox input'lar (toggle stil)
    for (const inp of scope.querySelectorAll('input[type="checkbox"]')) {
      if (!visible(inp) && inp.offsetParent === null) continue;
      const label =
        (inp.id && textOf(scope.querySelector(`label[for="${inp.id}"]`))) ||
        textOf(inp.closest("label") || inp.parentElement) ||
        "";
      found.push({ el: inp, label });
    }

    // 3) Etiket metnine göre yanındaki buton/input
    for (const name of CFG.toggleLabels) {
      const re = new RegExp(`^\\s*${name}\\s*$`, "i");
      for (const node of scope.querySelectorAll("label, span, div, p, h3, h4")) {
        if (!re.test(textOf(node).split("\n")[0])) continue;
        const row = node.closest("div") || node.parentElement;
        if (!row) continue;
        const sw =
          row.querySelector('[role="switch"]') ||
          row.querySelector('input[type="checkbox"]') ||
          row.querySelector("button");
        if (sw && !found.some((f) => f.el === sw)) found.push({ el: sw, label: name });
      }
    }
    return found;
  }

  async function turnOffToggles(modal) {
    const toggles = findTogglesInModal(modal);
    let clicked = 0;
    for (const { el, label } of toggles) {
      const hit = CFG.toggleLabels.some((t) => new RegExp(t, "i").test(label || textOf(el.parentElement)));
      if (!hit && CFG.toggleLabels.length) {
        // Etiket eşleşmezse yine de modal içindeki açık switch'leri kapat (güvenli alan)
        if (!isSwitchOn(el)) continue;
      } else if (!isSwitchOn(el)) {
        continue;
      }
      log("Toggle OFF:", label || "?");
      clickEl(el);
      clicked++;
      await sleep(CFG.delayMs / 2);
    }
    // İkinci geçiş: hâlâ açıksa tekrar dene
    for (const { el, label } of findTogglesInModal(modal)) {
      if (!isSwitchOn(el)) continue;
      const hit = CFG.toggleLabels.some((t) => new RegExp(t, "i").test(label || ""));
      if (!hit) continue;
      clickEl(el);
      clicked++;
      await sleep(200);
    }
    return clicked;
  }

  function findSaveButton(modal) {
    const scope = modal || document;
    const buttons = [...scope.querySelectorAll("button, a, [role='button']")].filter(visible);
    return (
      buttons.find((b) => /save\s*changes/i.test(textOf(b))) ||
      buttons.find((b) => /^save$/i.test(textOf(b))) ||
      buttons.find((b) => /kaydet/i.test(textOf(b)))
    );
  }

  function tableRows() {
    const rows = [
      ...document.querySelectorAll("table tbody tr, [role='row']"),
    ].filter((r) => visible(r) && r.querySelector("td, [role='cell']"));
    return rows;
  }

  function rowSourceText(row) {
    return textOf(row);
  }

  function findEditButton(row) {
    // kalem / edit
    const cands = [
      ...row.querySelectorAll("a, button, [role='button'], svg"),
    ];
    for (const el of cands) {
      const t = (
        el.getAttribute("title") ||
        el.getAttribute("aria-label") ||
        el.getAttribute("data-tooltip") ||
        ""
      ).toLowerCase();
      if (/edit|düzenle|pencil|kalem/.test(t)) {
        return el.closest("a, button, [role='button']") || el;
      }
    }
    // ACTIONS sütununda genelde ilk aksiyon = edit (trash değil)
    const actions =
      row.querySelector("td:last-child") ||
      [...row.querySelectorAll("td")].at(-1);
    if (!actions) return null;
    const btns = [...actions.querySelectorAll("a, button")].filter(visible);
    // trash olanı ele
    const edit = btns.find((b) => {
      const s = (
        b.innerHTML +
        (b.getAttribute("aria-label") || "") +
        (b.className || "")
      ).toLowerCase();
      return !/trash|delete|sil|remove/.test(s);
    });
    return edit || btns[0] || null;
  }

  function findNextPageButton() {
    const all = [...document.querySelectorAll("a, button, [role='button']")].filter(visible);
    // aria-label Next
    let btn = all.find((b) => /next|sonraki/i.test(b.getAttribute("aria-label") || ""));
    if (btn && !btn.disabled && !btn.getAttribute("aria-disabled")) return btn;
    // » veya › veya Next text
    btn = all.find((b) => {
      const t = textOf(b);
      return /^(next|sonraki|›|»|>)$/i.test(t) || t === "›" || t === "»";
    });
    if (btn && !btn.disabled) return btn;
    // pagination: aktif sayfadan sonraki numara
    const active =
      document.querySelector(".pagination .active, [aria-current='page'], .page-item.active");
    if (active) {
      const next = active.nextElementSibling?.querySelector("a, button") || active.nextElementSibling;
      if (next && visible(next) && !/disabled/.test(next.className || "")) return next;
    }
    return null;
  }

  async function waitFor(fn, timeout = 15000) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeout) {
      if (STOP) return null;
      const v = fn();
      if (v) return v;
      await sleep(150);
    }
    return null;
  }

  async function waitModalClose(prev) {
    const t0 = Date.now();
    while (Date.now() - t0 < 20000) {
      if (STOP) return;
      const m = findModal();
      if (!m || !visible(m)) return;
      // aynı modal hâlâ açıksa bekle
      await sleep(200);
    }
  }

  async function processRow(row, index) {
    const name = textOf(row.querySelector("td:nth-child(2)") || row);
    log(`#${index} Edit: ${name.slice(0, 60)}`);
    const edit = findEditButton(row);
    if (!edit) {
      log("Kalem bulunamadı, atlanıyor");
      return false;
    }
    clickEl(edit);
    const modal = await waitFor(() => findModal());
    if (!modal) {
      log("Edit modal açılmadı");
      return false;
    }
    await sleep(CFG.delayMs);
    const n = await turnOffToggles(modal);
    log(`Kapatılan toggle: ${n}`);
    const save = findSaveButton(modal);
    if (!save) {
      log("Save butonu yok — Cancel'a basıp çık");
      const cancel = [...modal.querySelectorAll("button")].find((b) =>
        /cancel|iptal/i.test(textOf(b))
      );
      if (cancel) clickEl(cancel);
      return false;
    }
    clickEl(save);
    await waitModalClose(modal);
    await sleep(CFG.delayMs);
    return true;
  }

  async function run() {
    if (RUNNING) return;
    RUNNING = true;
    STOP = false;
    let ok = 0;
    let fail = 0;
    let page = 1;

    log("Başladı. Filtreler senin seçtiğin gibi kalacak.");
    try {
      while (!STOP && page <= CFG.maxPages) {
        const rows = tableRows().filter((r) => CFG.sourceMatch.test(rowSourceText(r)));
        log(`Sayfa ${page}: ${rows.length} satır (Forcelab Api -3)`);

        if (!rows.length) {
          // Filtre zaten sadece bunları gösteriyorsa tüm satırları işle
          const all = tableRows();
          if (all.length) {
            log(`Source metni bulunamadı; sayfadaki ${all.length} satır işlenecek (filtreye güven)`);
            for (let i = 0; i < all.length; i++) {
              if (STOP) break;
              // Her seferinde satırları yeniden al (DOM yenilenir)
              const live = tableRows();
              const row = live[i];
              if (!row) break;
              const good = await processRow(row, ok + fail + 1);
              good ? ok++ : fail++;
            }
          }
        } else {
          // Eşleşenleri baştan sona; her kayıtta DOM değişebilir → her turda yeniden bul
          let safety = 0;
          while (!STOP && safety < 50) {
            safety++;
            const match = tableRows().filter((r) => CFG.sourceMatch.test(rowSourceText(r)));
            if (!match.length) break;
            const good = await processRow(match[0], ok + fail + 1);
            good ? ok++ : fail++;
            // Status kapanınca satır listeden düşebilir veya Inactive olur — devam
          }
        }

        if (STOP) break;
        const next = findNextPageButton();
        if (!next || next.disabled || /disabled|aria-disabled="true"/.test(next.outerHTML)) {
          log("Son sayfa.");
          break;
        }
        log("Sonraki sayfa…");
        clickEl(next);
        page++;
        await sleep(CFG.delayMs * 2);
        await waitFor(() => tableRows().length > 0, 10000);
      }
    } catch (e) {
      console.error(e);
      log("Hata:", e.message || e);
    } finally {
      RUNNING = false;
      log(`BİTTİ. OK=${ok} FAIL=${fail}`);
      const btn = document.getElementById("f3-start");
      if (btn) {
        btn.textContent = "Force3 Kapat — BAŞLAT";
        btn.disabled = false;
      }
    }
  }

  function mountUI() {
    document.getElementById("f3-panel")?.remove();
    const box = document.createElement("div");
    box.id = "f3-panel";
    box.innerHTML = `
      <div style="position:fixed;right:16px;bottom:16px;z-index:2147483647;font:13px/1.4 system-ui,sans-serif;
        background:#111827;color:#f9fafb;border:1px solid #a78bfa;border-radius:12px;padding:12px 14px;
        box-shadow:0 10px 40px rgba(0,0,0,.45);width:260px">
        <div style="font-weight:700;margin-bottom:6px;color:#c4b5fd">Forcelab Api -3</div>
        <div id="f3-status" style="opacity:.85;margin-bottom:10px;min-height:32px">Filtreleri seç → BAŞLAT</div>
        <div style="display:flex;gap:8px">
          <button id="f3-start" style="flex:1;background:#7c3aed;color:#fff;border:0;border-radius:8px;padding:8px 10px;cursor:pointer;font-weight:600">BAŞLAT</button>
          <button id="f3-stop" style="background:#374151;color:#fff;border:0;border-radius:8px;padding:8px 10px;cursor:pointer">DURDUR</button>
        </div>
      </div>`;
    document.body.appendChild(box);
    document.getElementById("f3-start").onclick = () => {
      if (RUNNING) return;
      document.getElementById("f3-start").textContent = "Çalışıyor…";
      document.getElementById("f3-start").disabled = true;
      run();
    };
    document.getElementById("f3-stop").onclick = () => {
      STOP = true;
      log("Durduruluyor…");
    };
  }

  mountUI();
  log("Hazır. Filtreleri uygula, BAŞLAT'a bas.");
})();
