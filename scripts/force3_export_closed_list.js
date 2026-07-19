/**
 * İşlem bittikten sonra — kapatılmış Force3 çift kayıtlarının TAM listesini Excel indir
 * (Tüm Force3 Inactive + aynı isimde Force1/2 var)
 *
 * Oyunlar sayfasında F12 → Console → yapıştır
 */
(function () {
  "use strict";

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const forceNum = (s) => {
    const m = /forcelab\s*api\s*-\s*(\d+)/i.exec((s || "").trim());
    return m ? +m[1] : 0;
  };

  window.__exportListRunning = true;
  window.__exportListRows = [];

  function log(m) {
    console.log("[ExportList]", m);
    const el = document.getElementById("exportlive");
    if (el) el.textContent = m;
  }

  function readRows() {
    return [...document.querySelectorAll("table tbody tr")]
      .filter((r) => r.querySelectorAll("td").length > 5)
      .map((r) => {
        const c = [...r.querySelectorAll("td")].map((td) =>
          td.innerText.replace(/\s+/g, " ").trim()
        );
        return { name: c[1], provider: c[4], source: c[5], status: c[7] };
      });
  }

  async function goFirst() {
    for (let i = 0; i < 3000; i++) {
      const prev = document.querySelector('button[aria-label="Previous page"]');
      if (!prev || prev.disabled) break;
      prev.click();
      await sleep(50);
    }
  }

  async function nextPage() {
    const btn = document.querySelector('button[aria-label="Next page"]');
    if (!btn || btn.disabled) return false;
    btn.click();
    await sleep(200);
    return true;
  }

  function downloadCsv(rows) {
    const header = [
      "oyun_adi",
      "provider",
      "force3_kaynak",
      "force3_durum",
      "diger_kaynaklar",
      "not",
    ];
    const esc = (v) => {
      const s = String(v ?? "").replace(/"/g, '""');
      return /[;"\n]/.test(s) ? `"${s}"` : s;
    };
    const lines = [
      header.join(";"),
      ...rows.map((r) =>
        [r.name, r.provider, r.source, r.status, r.otherSources, r.note]
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
      "force3_kapatilan_tam_liste_" +
      new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-") +
      ".csv";
    a.click();
    URL.revokeObjectURL(a.href);
  }

  if (!document.getElementById("exportpanel")) {
    const d = document.createElement("div");
    d.id = "exportpanel";
    d.style.cssText =
      "position:fixed;left:12px;bottom:12px;z-index:2147483647;background:#111;color:#fff;padding:12px;border-radius:10px;font:12px sans-serif;border:1px solid #34d399;width:280px";
    d.innerHTML =
      '<b style="color:#6ee7b7">Liste export</b><div id="exportlive" style="margin:8px 0;min-height:36px">Başlıyor...</div>';
    document.body.appendChild(d);
  }

  (async () => {
    try {
      log("Index taranıyor...");
      await goFirst();
      const index = new Map();
      for (let page = 0; page < 2500; page++) {
        for (const { name, source } of readRows()) {
          if (!name) continue;
          if (!index.has(name)) index.set(name, new Set());
          if (source) index.get(name).add(source);
        }
        if (page % 100 === 0) log(`Index ${page + 1}...`);
        if (!(await nextPage())) break;
      }

      const dupNames = new Set();
      for (const [name, srcs] of index) {
        const nums = [...srcs].map(forceNum).filter(Boolean);
        if (nums.includes(3) && (nums.includes(1) || nums.includes(2)))
          dupNames.add(name);
      }

      log(`${dupNames.size} çift kayıt — Force3 Inactive aranıyor...`);
      await goFirst();
      const out = [];
      for (let page = 0; page < 2500; page++) {
        for (const item of readRows()) {
          if (forceNum(item.source) !== 3) continue;
          if (!dupNames.has(item.name)) continue;
          if (!/\bInactive\b/i.test(item.status || "")) continue;
          const others = [...(index.get(item.name) || [])]
            .filter((s) => forceNum(s) === 1 || forceNum(s) === 2)
            .join(" | ");
          out.push({
            name: item.name,
            provider: item.provider,
            source: item.source,
            status: item.status,
            otherSources: others,
            note: "Force1/2 mevcut — Force3 kapatıldı",
          });
        }
        if (page % 100 === 0) log(`Tarama ${page + 1} — ${out.length} bulundu`);
        if (!(await nextPage())) break;
      }

      window.__exportListRows = out;
      downloadCsv(out);
      log(`BİTTİ — ${out.length} oyun Excel indirildi`);
    } finally {
      window.__exportListRunning = false;
    }
  })();
})();
