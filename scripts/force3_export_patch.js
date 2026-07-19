/**
 * Çalışan işleme eklenti — kapatılan oyunları kaydet + Excel indir
 * (Ana script zaten çalışıyorsa bunu console'a yapıştır)
 */
(function () {
  window.__dupClosed = window.__dupClosed || [];

  window.exportDupClosedExcel = function () {
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
        [r.name, r.provider, r.source, r.otherSources, r.prevStatus, r.action, r.closedAt]
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
    return rows.length;
  };

  const live = document.getElementById("duplive");
  if (live && !window.__dupObserver) {
    window.__dupObserver = new MutationObserver(() => {
      const t = live.textContent || "";
      const m = t.match(/^Kapat:\s*(.+)$/);
      if (!m) return;
      const name = m[1].trim();
      if (window.__dupClosed.some((x) => x.name === name && x.closedAt)) return;
      const now = new Date().toLocaleString("tr-TR");
      window.__dupClosed.push({
        name,
        provider: "",
        source: "Forcelab Api -3",
        otherSources: "(Force1/2 mevcut)",
        prevStatus: "Active",
        action: "Status → Inactive",
        closedAt: now,
      });
    });
    window.__dupObserver.observe(live, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  if (!document.getElementById("dupexport")) {
    const btn = document.createElement("button");
    btn.id = "dupexport";
    btn.textContent = "EXCEL İNDİR";
    btn.style.cssText =
      "background:#0891b2;color:#fff;border:0;padding:6px 10px;border-radius:6px;cursor:pointer;margin-left:6px";
    btn.onclick = () => {
      const n = window.exportDupClosedExcel();
      alert("İndirildi: " + n + " oyun");
    };
    const panel = document.getElementById("duppanel");
    if (panel) panel.querySelector("div:last-child")?.appendChild(btn);
  }

  if (!window.__dupAutoExport) {
    window.__dupAutoExport = setInterval(() => {
      if (!window.__dupRunning && (window.__dupClosed || []).length) {
        clearInterval(window.__dupAutoExport);
        window.exportDupClosedExcel();
        console.log("[DupF3] Otomatik Excel indirildi:", window.__dupClosed.length);
      }
    }, 3000);
  }

  console.log("[DupF3] Export eklentisi aktif. Manuel: exportDupClosedExcel()");
})();
