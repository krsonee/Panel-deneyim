/**
 * Bizzocazino — Sadece çift kayıtlı Force3 oyunlarını Inactive yap + Excel listesi
 *
 * KURAL:
 *  - Force1/2'de de var + Force3'te var → Force3 Status OFF
 *  - Sadece Force3'te var → dokunma
 *
 * Bittiğinde otomatik CSV indirir (Excel'de açılır).
 * Manuel indir: exportDupClosedExcel()
 */
(function () {
  "use strict";

  window.__force3Stop = false;
  if (window.__dupRunning) {
    console.warn("Zaten çalışıyor");
    return;
  }
  window.__dupRunning = true;
  window.__dupClosed = window.__dupClosed || [];
  window.__dupIndex = window.__dupIndex || null;

  window.__dupStats = {
    phase: "init",
    pages: 0,
    indexed: 0,
    targets: 0,
    ok: 0,
    skip: 0,
    fail: 0,
  };

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const forceNum = (s) => {
    const m = /forcelab\s*api\s*-\s*(\d+)/i.exec((s || "").trim());
    return m ? +m[1] : 0;
  };

  window.exportDupClosedExcel = function exportDupClosedExcel() {
    const rows = window.__dupClosed || [];
    const header = [
      "oyun_adi",
      "provider",
      "kaynak",
      "diger_kaynaklar",
      "onceki_durum",
      "islem",
      "tarih",
    ];
    const esc = (v) => {
      const s = String(v ?? "").replace(/"/g, '""');
      return /[;"\n]/.test(s) ? `"${s}"` : s;
    };
    const lines = [
      header.join(";"),
      ...rows.map((r) =>
        [
          r.name,
          r.provider,
          r.source,
          r.otherSources,
          r.prevStatus,
          r.action,
          r.closedAt,
        ]
          .map(esc)
          .join(";")
      ),
    ];
    const blob = new Blob(["\ufeff" + lines.join("\n")], {
      type: "text/csv;charset=utf-8",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download =
      "force3_kapatilan_oyunlar_" +
      new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") +
      ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
    console.log("[DupF3] İndirildi:", rows.length, "satır");
    return rows.length;
  };

  function log(m) {
    console.log("[DupF3]", m);
    window.__dupStats.msg = m;
    let p = document.getElementById("duppanel");
    if (!p) {
      p = document.createElement("div");
      p.id = "duppanel";
      p.style.cssText =
        "position:fixed;right:12px;bottom:12px;z-index:2147483647;background:#111;color:#fff;padding:12px;border-radius:10px;font:12px sans-serif;border:1px solid #22d3ee;width:320px";
      p.innerHTML =
        '<b style="color:#67e8f9">Dup Force3 → Inactive</b>' +
        '<div id="duplive" style="margin:8px 0;min-height:48px"></div>' +
        '<div style="display:flex;gap:6px;flex-wrap:wrap">' +
        '<button id="dupstop" style="background:#444;color:#fff;border:0;padding:6px 10px;border-radius:6px;cursor:pointer">DURDUR</button>' +
        '<button id="dupexport" style="background:#0891b2;color:#fff;border:0;padding:6px 10px;border-radius:6px;cursor:pointer">EXCEL İNDİR</button>' +
        "</div>";
      document.body.appendChild(p);
      document.getElementById("dupstop").onclick = () => {
        window.__force3Stop = true;
        log("durduruluyor");
      };
      document.getElementById("dupexport").onclick = () =>
        window.exportDupClosedExcel();
    }
    const el = document.getElementById("duplive");
    if (el) el.textContent = m;
  }

  function readRows() {
    return [...document.querySelectorAll("table tbody tr")]
      .filter((r) => r.querySelectorAll("td").length > 5)
      .map((r) => {
        const c = [...r.querySelectorAll("td")].map((td) =>
          td.innerText.replace(/\s+/g, " ").trim()
        );
        return {
          row: r,
          name: c[1],
          provider: c[4],
          source: c[5],
          status: c[7],
        };
      });
  }

  async function goFirst() {
    for (let i = 0; i < 3000; i++) {
      const prev = document.querySelector('button[aria-label="Previous page"]');
      if (!prev || prev.disabled) break;
      prev.click();
      await sleep(60);
    }
  }

  async function nextPage() {
    const btn = document.querySelector('button[aria-label="Next page"]');
    if (!btn || btn.disabled) return false;
    btn.click();
    await sleep(220);
    return true;
  }

  function getDialog() {
    return document.querySelector(".v-overlay--active .v-card");
  }

  async function waitFor(fn, t = 12000) {
    const t0 = Date.now();
    while (Date.now() - t0 < t) {
      if (window.__force3Stop) return null;
      const v = fn();
      if (v) return v;
      await sleep(100);
    }
    return null;
  }

  async function statusOffOnly(dialog) {
    for (const sw of dialog.querySelectorAll(".v-switch")) {
      const label = sw.innerText.replace(/\s+/g, " ").trim();
      if (!/^Status$/i.test(label)) continue;
      const input = sw.querySelector('input[type=checkbox]');
      if (input && input.checked) {
        (sw.querySelector(".v-selection-control__input") || sw).click();
        await sleep(180);
        return true;
      }
      return false;
    }
    return false;
  }

  async function disableRow(item, otherSources) {
    log("Kapat: " + item.name);
    const edit = item.row.querySelectorAll("button")[0];
    if (!edit) throw new Error("edit yok");
    edit.click();
    const dialog = await waitFor(() => getDialog());
    if (!dialog) throw new Error("modal yok");
    await sleep(300);
    await statusOffOnly(dialog);
    const save = [...dialog.querySelectorAll("button")].find((b) =>
      /save\s*changes/i.test(b.innerText)
    );
    if (!save) throw new Error("save yok");
    save.click();
    await waitFor(() => !getDialog(), 12000);
    await sleep(350);

    window.__dupClosed.push({
      name: item.name,
      provider: item.provider || "",
      source: item.source || "Forcelab Api -3",
      otherSources: otherSources || "",
      prevStatus: item.status || "Active",
      action: "Status → Inactive",
      closedAt: new Date().toLocaleString("tr-TR"),
    });
  }

  (async () => {
    try {
      log("1/2 Index taranıyor (~18k oyun)...");
      window.__dupStats.phase = "index";
      await goFirst();
      const index = new Map();

      for (let page = 0; page < 2500 && !window.__force3Stop; page++) {
        window.__dupStats.pages = page + 1;
        for (const { name, source } of readRows()) {
          if (!name) continue;
          if (!index.has(name)) index.set(name, new Set());
          if (source) index.get(name).add(source);
          window.__dupStats.indexed++;
        }
        if (page % 50 === 0)
          log(`Index sayfa ${page + 1} — ${index.size} benzersiz oyun`);
        if (!(await nextPage())) break;
      }
      window.__dupIndex = index;

      const targets = new Map();
      for (const [name, srcs] of index) {
        const nums = [...srcs].map(forceNum).filter(Boolean);
        if (nums.includes(3) && (nums.includes(1) || nums.includes(2))) {
          const others = [...srcs]
            .filter((s) => forceNum(s) === 1 || forceNum(s) === 2)
            .join(" | ");
          targets.set(name, others);
        }
      }
      window.__dupStats.targets = targets.size;
      window.__dupStats.phase = "process";
      log(`2/2 ${targets.size} çift kayıt — Force3 kapatılıyor`);

      await goFirst();
      for (let page = 0; page < 2500 && !window.__force3Stop; page++) {
        window.__dupStats.pages = page + 1;
        for (const item of readRows()) {
          if (window.__force3Stop) break;
          if (forceNum(item.source) !== 3) continue;
          if (!targets.has(item.name)) {
            window.__dupStats.skip++;
            continue;
          }
          if (!/\bActive\b/i.test(item.status || "")) {
            window.__dupStats.skip++;
            targets.delete(item.name);
            continue;
          }
          try {
            await disableRow(item, targets.get(item.name));
            window.__dupStats.ok++;
            targets.delete(item.name);
          } catch (e) {
            window.__dupStats.fail++;
            log("FAIL " + item.name + ": " + (e.message || e));
            const d = getDialog();
            if (d) {
              const c = [...d.querySelectorAll("button")].find((b) =>
                /cancel/i.test(b.innerText)
              );
              if (c) c.click();
              await sleep(300);
            }
          }
        }
        if (targets.size === 0) {
          log("Tüm hedefler işlendi");
          break;
        }
        if (page % 20 === 0)
          log(
            `İşlem sayfa ${page + 1} OK=${window.__dupStats.ok} kalan=${targets.size}`
          );
        if (!(await nextPage())) break;
      }
    } finally {
      window.__dupRunning = false;
      const s = window.__dupStats;
      const n = (window.__dupClosed || []).length;
      log(`BİTTİ OK=${s.ok} skip=${s.skip} fail=${s.fail} | liste=${n}`);
      if (n > 0) {
        setTimeout(() => window.exportDupClosedExcel(), 800);
        log(`Excel indiriliyor (${n} oyun)...`);
      }
    }
  })();

  console.log("Dup Force3 script başladı — bitince Excel iner");
})();
