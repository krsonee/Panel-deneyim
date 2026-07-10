(function () {
  "use strict";

  var ACC_PAGE = 10;
  var accPeriod = localStorage.getItem("acc_period") || "";
  var accPeriodMode = localStorage.getItem("acc_period_mode") || "pick";
  var accActiveTab = "dashboard";
  var accPaymentMethods = [];
  var accCategories = [];
  var accEmployeeDepartments = [];
  var accSalaryCategories = [];
  var accEmpFilterCat = "";
  var accEmpFilterDept = "";
  var accDisplayCurrency = localStorage.getItem("acc_display_currency") || "TRY";
  var accEmpCurrencyView = localStorage.getItem("acc_emp_currency_view") || accDisplayCurrency;
  var accRates = { usd_try: null, eur_try: null, date: null, source: null, fetched_at: null };
  var accRatesPollId = null;
  var ACC_RATES_POLL_MS = 30000;
  var ACC_SYMBOLS = { TRY: "₺", USD: "$", EUR: "€" };

  var accCanViewOfficeSalaries = false;

  var accData = {
    "acc-tx": { rows: [], expanded: false, sortKey: "tx_date", sortDir: "desc" },
    "acc-exp": { rows: [], expanded: false, sortKey: "expense_date", sortDir: "desc" },
    "acc-vault": { rows: [], expanded: false, sortKey: "tx_date", sortDir: "desc" },
    "acc-emp": { rows: [], expanded: false, sortKey: "name", sortDir: "asc" }
  };

  function accSetOfficeSalaryAccess(canView) {
    accCanViewOfficeSalaries = !!canView;
    document.querySelectorAll(".acc-col-office").forEach(function (el) {
      el.hidden = !accCanViewOfficeSalaries;
    });
    var note = document.getElementById("acc-payroll-office-note");
    if (note) note.hidden = accCanViewOfficeSalaries;
  }

  function accHiddenMoney() {
    return '<span class="muted">Gizli</span>';
  }

  function accApplyPermissionsMeta(data) {
    if (data && typeof data.can_view_office_salaries !== "undefined") {
      accSetOfficeSalaryAccess(data.can_view_office_salaries);
    }
  }

  function accApi(path, opts) {
    opts = opts || {};
    return fetch(path, opts).then(function (r) {
      if (r.status === 401) { location.href = "/admin/login"; return null; }
      return r.json().then(function (d) { return { ok: r.ok, status: r.status, data: d }; });
    });
  }

  function accEsc(s) {
    var d = document.createElement("div");
    d.textContent = s == null ? "" : s;
    return d.innerHTML;
  }

  function accMoney(n, currency) {
    currency = currency || accDisplayCurrency;
    n = parseFloat(n) || 0;
    var sym = ACC_SYMBOLS[currency] || currency + " ";
    return sym + n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function accMoneyIn(row, field) {
    if (!row) return 0;
    var cur = accDisplayCurrency;
    var key = field + "_" + cur.toLowerCase();
    if (row[key] != null && row[key] !== "") return row[key];
    if (field === "amount" && row.currency === cur) return row.amount;
    if (field === "salary" && row.currency === cur) return row.salary;
    if (field === "commission_amount" && row.currency === cur) return row.commission_amount;
    return row[field + "_try"] != null ? row[field + "_" + cur.toLowerCase()] : (row[field] || 0);
  }

  function accMoneyCellHtml(row, field) {
    var valField = field === "salary" ? "salary" : (field === "commission_amount" ? "commission_amount" : "amount");
    var cur = row.currency || "USD";
    var main = accMoney(row[valField] || 0, cur);
    var tryV, usdV, eurV;
    if (field === "salary") {
      tryV = row.salary_try; usdV = row.salary_usd; eurV = row.salary_eur;
    } else if (field === "commission_amount") {
      tryV = row.commission_amount_try; usdV = row.commission_amount_usd; eurV = row.commission_amount_eur;
    } else {
      tryV = row.amount_try; usdV = row.amount_usd; eurV = row.amount_eur;
    }
    if (tryV == null && usdV == null) return "<strong>" + main + "</strong>";
    return "<strong>" + main + '</strong><br><small class="muted">≈ ' +
      accMoney(tryV, "TRY") + " · " + accMoney(usdV, "USD") + " · " + accMoney(eurV, "EUR") + "</small>";
  }

  function accFxPreviewText(amount, currency, rateUsd, rateEur) {
    amount = parseFloat(amount);
    if (!amount || amount <= 0) return Promise.resolve("");
    var body = { amount: amount, currency: currency };
    if (rateUsd && rateEur) {
      body.rate_usd_try = rateUsd;
      body.rate_eur_try = rateEur;
    } else {
      body.auto_rate = true;
    }
    return accApi("/api/accounting/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    }).then(function (res) {
      if (!res || !res.ok) return "";
      var c = res.data.converted;
      return "≈ " + accMoney(c.TRY, "TRY") + " · " + accMoney(c.USD, "USD") + " · " + accMoney(c.EUR, "EUR");
    });
  }

  function accBindFxPreview(amountId, currencyId, previewId, rateUsdId, rateEurId) {
    var amountEl = document.getElementById(amountId);
    var curEl = document.getElementById(currencyId);
    var previewEl = document.getElementById(previewId);
    var rateUsdEl = rateUsdId ? document.getElementById(rateUsdId) : null;
    var rateEurEl = rateEurId ? document.getElementById(rateEurId) : null;
    if (!amountEl || !curEl || !previewEl) return;
    var timer = null;
    function update() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        accFxPreviewText(
          amountEl.value,
          curEl.value,
          rateUsdEl ? rateUsdEl.value : "",
          rateEurEl ? rateEurEl.value : ""
        ).then(function (txt) {
          previewEl.textContent = txt || "";
        });
      }, 250);
    }
    amountEl.addEventListener("input", update);
    curEl.addEventListener("change", update);
    if (rateUsdEl) rateUsdEl.addEventListener("input", update);
    if (rateEurEl) rateEurEl.addEventListener("input", update);
  }

  function accReadFormRates(usdId, eurId) {
    var usdEl = document.getElementById(usdId);
    var eurEl = document.getElementById(eurId);
    var body = {};
    if (usdEl && usdEl.value.trim() && eurEl && eurEl.value.trim()) {
      body.rate_usd_try = usdEl.value.trim();
      body.rate_eur_try = eurEl.value.trim();
    } else {
      body.auto_rate = true;
    }
    return body;
  }

  function accClearFormRates(usdId, eurId) {
    var usdEl = document.getElementById(usdId);
    var eurEl = document.getElementById(eurId);
    if (usdEl) usdEl.value = "";
    if (eurEl) eurEl.value = "";
  }

  function accFormatRate(n) {
    if (n == null || n === "") return "?";
    return parseFloat(n).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }

  function accApplyRates(data) {
    if (!data || !data.usd_try || !data.eur_try) return;
    accRates = data;
    accUpdateRatePlaceholders();
  }

  function accRateTimeLabel() {
    if (!accRates.fetched_at) return "";
    try {
      return " · " + new Date(accRates.fetched_at).toLocaleTimeString("tr-TR", {
        hour: "2-digit", minute: "2-digit", second: "2-digit"
      });
    } catch (e) {
      return "";
    }
  }

  function accUpdateRatePlaceholders() {
    var usd = accFormatRate(accRates.usd_try);
    var eur = accFormatRate(accRates.eur_try);
    var suffix = accRates.source && accRates.source !== "fallback" ? accRateTimeLabel() : " (yükleniyor…)";
    document.querySelectorAll(".acc-form-rate").forEach(function (el) {
      el.placeholder = "Boş = kayıt anı kuru (" + usd + " / " + eur + ")" + suffix;
    });
    var badge = document.getElementById("acc-live-rates-badge");
    if (badge) {
      badge.textContent = accRates.usd_try && accRates.eur_try
        ? "Yeni kayıt referans · USD/TL " + accFormatRate(accRates.usd_try) + " · EUR/TL " + accFormatRate(accRates.eur_try) + accRateTimeLabel()
        : "Kur yükleniyor…";
    }
  }

  function accLoadRates() {
    return accApi("/api/accounting/exchange-rates").then(function (res) {
      if (!res || !res.ok) return;
      accApplyRates(res.data);
    });
  }

  function accStartRatesPolling() {
    if (accRatesPollId) clearInterval(accRatesPollId);
    accRatesPollId = setInterval(function () {
      if (document.hidden) return;
      accLoadRates();
    }, ACC_RATES_POLL_MS);
  }

  function accRatesSummary(rates) {
    rates = rates || accRates;
    if (!rates.usd_try || !rates.eur_try) return "Kur yükleniyor…";
    var usd = parseFloat(rates.usd_try).toFixed(2);
    var eur = parseFloat(rates.eur_try).toFixed(2);
    return "USD/TL: " + usd + " · EUR/TL: " + eur;
  }

  function accSavedToast(msg, rates) {
    accToast(msg + " · " + accRatesSummary(rates));
    if (rates) {
      accRates.usd_try = rates.usd_try;
      accRates.eur_try = rates.eur_try;
      accUpdateRatePlaceholders();
    }
  }

  function accToast(msg) {
    if (typeof window.toast === "function") window.toast(msg);
    else alert(msg);
  }

  function accToday() {
    return new Date().toISOString().slice(0, 10);
  }

  function accCurrentMonth() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
  }

  function accResolvePeriod() {
    var modeEl = document.getElementById("acc-filter-period");
    var monthEl = document.getElementById("acc-filter-month");
    var mode = modeEl ? modeEl.value : accPeriodMode;
    if (mode === "all" || mode === "30days" || mode === "today") {
      if (monthEl) monthEl.disabled = true;
      accPeriod = mode;
    } else {
      if (monthEl) {
        monthEl.disabled = false;
        if (!monthEl.value) monthEl.value = accCurrentMonth();
        accPeriod = monthEl.value || accCurrentMonth();
      } else {
        accPeriod = accCurrentMonth();
      }
    }
    accPeriodMode = mode;
    localStorage.setItem("acc_period", accPeriod);
    localStorage.setItem("acc_period_mode", accPeriodMode);
    return accPeriod;
  }

  function accUpdatePeriodLabel(label) {
    var el = document.getElementById("acc-period-label");
    if (el && label) el.textContent = "· " + label;
  }

  function accPeriodQuery() {
    var p = accResolvePeriod();
    return p ? "?period=" + encodeURIComponent(p) : "";
  }

  function accCompare(a, b, dir) {
    var m = dir === "asc" ? 1 : -1;
    if (a == null && b == null) return 0;
    if (a == null) return 1;
    if (b == null) return -1;
    if (typeof a === "number" && typeof b === "number") return (a - b) * m;
    return String(a).localeCompare(String(b), "tr", { numeric: true }) * m;
  }

  function accSortRows(key, rows, getters) {
    var st = accData[key];
    var list = (rows || []).slice();
    var getter = getters[st.sortKey] || function (r) { return r[st.sortKey]; };
    list.sort(function (a, b) { return accCompare(getter(a), getter(b), st.sortDir); });
    if (!st.expanded && list.length > ACC_PAGE) return list.slice(0, ACC_PAGE);
    return list;
  }

  function accUpdateFoot(key, total, label) {
    var foot = document.getElementById(key + "-table-foot");
    var countEl = document.getElementById(key + "-table-count");
    var scroll = document.getElementById(key + "-table-scroll");
    var st = accData[key];
    if (!foot) return;
    if (!total || total <= ACC_PAGE) {
      foot.style.display = "none";
      if (scroll) scroll.classList.remove("scrollable");
      return;
    }
    foot.style.display = "flex";
    var btn = foot.querySelector("[data-acc-toggle]");
    if (btn) {
      btn.textContent = st.expanded
        ? "▲ Daha az göster"
        : "▼ Tümünü göster (" + (total - ACC_PAGE) + " " + label + " daha)";
    }
    if (countEl) {
      countEl.textContent = st.expanded
        ? total + " " + label + " listeleniyor"
        : "İlk " + ACC_PAGE + " / " + total + " " + label;
    }
    if (scroll) scroll.classList.toggle("scrollable", st.expanded);
  }

  function accUpdateSortHeaders(key) {
    var st = accData[key];
    document.querySelectorAll('[data-acc-sort="' + key + '"]').forEach(function (th) {
      var sk = th.getAttribute("data-sort");
      th.classList.toggle("sorted-asc", sk === st.sortKey && st.sortDir === "asc");
      th.classList.toggle("sorted-desc", sk === st.sortKey && st.sortDir === "desc");
    });
  }

  function accToggleSort(key, sortKey) {
    var st = accData[key];
    if (st.sortKey === sortKey) st.sortDir = st.sortDir === "asc" ? "desc" : "asc";
    else { st.sortKey = sortKey; st.sortDir = "desc"; }
    accRerenderTable(key);
  }

  function accToggleExpand(key) {
    accData[key].expanded = !accData[key].expanded;
    accRerenderTable(key);
  }

  function accRerenderTable(key) {
    if (key === "acc-tx") accRenderTransactions();
    else if (key === "acc-exp") accRenderExpenses();
    else if (key === "acc-vault") accRenderVault();
    else if (key === "acc-emp") accRenderEmployees();
  }

  function accTxTypeLabel(t) {
    return t === "deposit" ? "Yatırım" : "Çekim";
  }

  function accRefreshTxPaymentSelect() {
    var sel = document.getElementById("acc-tx-payment");
    var typeEl = document.getElementById("acc-tx-type");
    if (!sel || !typeEl) return;
    var txType = typeEl.value;
    var filtered = accPaymentMethods.filter(function (p) {
      return !p.tx_type || p.tx_type === txType;
    });
    sel.innerHTML = filtered.length
      ? filtered.map(function (p) {
          return '<option value="' + p.id + '">' + accEsc(p.name) + " (%" + p.commission_rate + ")</option>";
        }).join("")
      : '<option value="">Bu tür için payment ekleyin (' + accTxTypeLabel(txType) + ')</option>';
  }

  function accVaultTypeLabel(t) {
    return t === "in" ? "Giriş" : "Çıkış";
  }

  function accStatusLabel(s) {
    return s === "active" ? "Aktif Çalışıyor" : "Ayrıldı";
  }

  function accCategoryLabel(cat) {
    var row = accSalaryCategories.find(function (c) { return c.slug === cat; });
    return row ? row.name : (cat || "—");
  }

  function accIsOfficeCategory(slug) {
    var row = accSalaryCategories.find(function (c) { return c.slug === slug; });
    return !!(row && row.is_office);
  }

  function accApplySalaryCategories(categories) {
    if (categories && categories.length) accSalaryCategories = categories;
    accRenderSalaryCatChips();
    accBuildPayrollTableHead();
    accRefreshEmpSelects();
    accRefreshEmpFilters();
  }

  function accApplyDepartments(departments) {
    if (departments && departments.length) accEmployeeDepartments = departments;
    accRenderDeptChips();
    accRefreshEmpSelects();
    accRefreshEmpFilters();
  }

  function accRefreshEmpSelects() {
    var catSel = document.getElementById("acc-emp-category");
    if (catSel) {
      var prevCat = catSel.value;
      catSel.innerHTML = accSalaryCategories.length
        ? accSalaryCategories.map(function (c) {
            return '<option value="' + accEsc(c.slug) + '" data-office="' + (c.is_office ? "1" : "0") + '">' +
              accEsc(c.name) + "</option>";
          }).join("")
        : '<option value="">Kategori ekleyin</option>';
      if (prevCat && accSalaryCategories.some(function (c) { return c.slug === prevCat; })) {
        catSel.value = prevCat;
      } else if (accSalaryCategories.length) {
        var def = accSalaryCategories.find(function (c) { return c.slug === "turkey"; });
        catSel.value = def ? def.slug : accSalaryCategories[0].slug;
      }
    }
    var deptSel = document.getElementById("acc-emp-dept");
    if (deptSel) {
      var prevDept = deptSel.value;
      deptSel.innerHTML = accEmployeeDepartments.length
        ? accEmployeeDepartments.map(function (d) {
            return '<option value="' + accEsc(d.name) + '">' + accEsc(d.name) + "</option>";
          }).join("")
        : '<option value="">Departman ekleyin</option>';
      if (prevDept && accEmployeeDepartments.some(function (d) { return d.name === prevDept; })) {
        deptSel.value = prevDept;
      }
    }
    accUpdateEmpFormUi();
  }

  function accRenderDeptChips() {
    var chips = document.getElementById("acc-dept-chips");
    var countEl = document.getElementById("acc-dept-count");
    if (!chips) return;
    var rows = accEmployeeDepartments.slice().sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "tr");
    });
    if (countEl) countEl.textContent = rows.length + " kayıt";
    chips.innerHTML = rows.length
      ? rows.map(function (d) {
          return '<span class="acc-chip" title="' + accEsc(d.name) + '"><span class="acc-chip-text">' + accEsc(d.name) +
            '</span> <button type="button" data-del-dept="' + d.id + '" title="Sil">×</button></span>';
        }).join("")
      : '<span class="acc-chip-empty">Henüz departman yok</span>';
    chips.querySelectorAll("[data-del-dept]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Departman silinsin mi?")) return;
        accApi("/api/accounting/employee-departments/" + btn.getAttribute("data-del-dept"), { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) { accLoadEmpOptions(); accToast("Silindi"); }
            else if (r) alert(r.data.error || "Hata");
          });
      };
    });
  }

  function accRenderSalaryCatChips() {
    var chips = document.getElementById("acc-salary-cat-chips");
    var countEl = document.getElementById("acc-salary-cat-count");
    if (!chips) return;
    var rows = accSalaryCategories.slice().sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "tr");
    });
    if (countEl) countEl.textContent = rows.length + " kayıt";
    chips.innerHTML = rows.length
      ? rows.map(function (c) {
          var tag = c.is_office ? ' <small class="muted">(ofis)</small>' : "";
          var label = c.name + (c.is_office ? " (ofis)" : "");
          return '<span class="acc-chip" title="' + accEsc(label) + '"><span class="acc-chip-text">' + accEsc(c.name) + '</span>' + tag +
            ' <button type="button" data-del-salary-cat="' + c.id + '" title="Sil">×</button></span>';
        }).join("")
      : '<span class="acc-chip-empty">Henüz kategori yok</span>';
    chips.querySelectorAll("[data-del-salary-cat]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Kategori silinsin mi?")) return;
        accApi("/api/accounting/salary-categories/" + btn.getAttribute("data-del-salary-cat"), { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) { accLoadEmpOptions(); accLoadEmployees(); accLoadDashboard(); accToast("Silindi"); }
            else if (r) alert(r.data.error || "Hata");
          });
      };
    });
  }

  function accBuildPayrollTableHead() {
    var head = document.getElementById("acc-payroll-daily-head");
    var footLabel = document.getElementById("acc-payroll-daily-foot-label");
    if (!head) return;
    var cols = accSalaryCategories.length ? accSalaryCategories : [
      { slug: "office", name: "Ofis", is_office: true },
      { slug: "turkey", name: "Türkiye", is_office: false },
      { slug: "crypto", name: "Kripto", is_office: false }
    ];
    var html = "<th>Tarih</th><th>Personel</th>";
    cols.forEach(function (c) {
      html += '<th' + (c.is_office ? ' class="acc-col-office"' : "") + ">" + accEsc(c.name) + "</th>";
    });
    html += "<th>Günlük Toplam</th>";
    head.innerHTML = html;
    if (footLabel) footLabel.colSpan = 2 + cols.length;
    accSetOfficeSalaryAccess(accCanViewOfficeSalaries);
  }

  function accPayrollColspan() {
    return 3 + (accSalaryCategories.length || 3);
  }

  function accLoadEmpOptions() {
    return Promise.all([
      accApi("/api/accounting/employee-departments"),
      accApi("/api/accounting/salary-categories")
    ]).then(function (results) {
      var deptRes = results[0];
      var catRes = results[1];
      if (deptRes && deptRes.ok) {
        accEmployeeDepartments = deptRes.data.departments || [];
        accRenderDeptChips();
      }
      if (catRes && catRes.ok) {
        accSalaryCategories = catRes.data.salary_categories || [];
        accRenderSalaryCatChips();
      }
      accRefreshEmpSelects();
    });
  }

  function accAccrualValue(row) {
    if (!row || !row.accrual) return 0;
    var cur = accEmpCurrencyView;
    return row.accrual[cur] != null ? row.accrual[cur] : 0;
  }

  function accNetAccrualValue(row) {
    if (!row || !row.net_accrual) return accAccrualValue(row);
    var cur = accEmpCurrencyView;
    return row.net_accrual[cur] != null ? row.net_accrual[cur] : 0;
  }

  function accAdvanceDisplay(row) {
    if (!row) return 0;
    if (row.advance_by_currency && row.advance_by_currency[accEmpCurrencyView] != null) {
      return row.advance_by_currency[accEmpCurrencyView];
    }
    return row.advance_amount || 0;
  }

  function accUsdt(n) {
    n = parseFloat(n) || 0;
    return "USDT " + n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function accPayrollTriCurCellHtml(map, hidden) {
    if (hidden) return accHiddenMoney();
    if (!map) return accHiddenMoney();
    var tryAmt = map.TRY != null ? map.TRY : 0;
    var usdAmt = map.USD != null ? map.USD : 0;
    return '<div class="acc-emp-tri-cur">' +
      '<div><span class="acc-cur-tag">TL</span><span>' + accMoney(tryAmt, "TRY") + "</span></div>" +
      '<div><span class="acc-cur-tag">USD</span><span>' + accMoney(usdAmt, "USD") + "</span></div>" +
      '<div><span class="acc-cur-tag">USDT</span><span>' + accUsdt(usdAmt) + "</span></div>" +
      "</div>";
  }

  function accMultiCurCellHtml(map, hidden) {
    if (hidden) return accHiddenMoney();
    if (!map) return accHiddenMoney();
    var cur = accEmpCurrencyView;
    var main = accMoney(map[cur] != null ? map[cur] : 0, cur);
    var others = ["TRY", "USD", "EUR"].filter(function (c) { return c !== cur; });
    var sub = others.map(function (c) { return accMoney(map[c] || 0, c); }).join(" · ");
    return "<strong>" + main + '</strong><br><small class="muted">' + sub + "</small>";
  }

  function accFilteredEmployees() {
    return (accData["acc-emp"].rows || []).filter(function (r) {
      if (accEmpFilterCat && r.salary_category !== accEmpFilterCat) return false;
      if (accEmpFilterDept && r.department !== accEmpFilterDept) return false;
      return true;
    });
  }

  function accRefreshEmpFilters() {
    var catSel = document.getElementById("acc-emp-filter-cat");
    var deptSel = document.getElementById("acc-emp-filter-dept");
    var curSel = document.getElementById("acc-emp-currency-view");
    if (catSel) {
      var prev = accEmpFilterCat || catSel.value;
      catSel.innerHTML = '<option value="">Tüm kategoriler</option>' +
        accSalaryCategories.map(function (c) {
          return '<option value="' + accEsc(c.slug) + '">' + accEsc(c.name) + "</option>";
        }).join("");
      catSel.value = prev || "";
      accEmpFilterCat = catSel.value;
    }
    if (deptSel) {
      var prevD = accEmpFilterDept || deptSel.value;
      deptSel.innerHTML = '<option value="">Tüm departmanlar</option>' +
        accEmployeeDepartments.map(function (d) {
          return '<option value="' + accEsc(d.name) + '">' + accEsc(d.name) + "</option>";
        }).join("");
      deptSel.value = prevD || "";
      accEmpFilterDept = deptSel.value;
    }
    if (curSel) {
      curSel.value = accEmpCurrencyView;
    }
  }

  function accUpdateEmpPayrollTotals(rows) {
    rows = rows || accFilteredEmployees();
    var cur = accEmpCurrencyView;
    var gross = 0;
    var net = 0;
    var advance = 0;
    rows.forEach(function (r) {
      if (r.salary_hidden) return;
      gross += accAccrualValue(r);
      net += accNetAccrualValue(r);
      advance += accAdvanceDisplay(r);
    });
    var totalEl = document.getElementById("acc-payroll-total");
    var subEl = document.getElementById("acc-payroll-total-sub");
    if (totalEl) totalEl.textContent = accMoney(net, cur);
    if (subEl) {
      subEl.textContent = "Hak ediş: " + accMoney(gross, cur) +
        " · Avans: " + accMoney(advance, cur) +
        " · Net: " + accMoney(net, cur);
    }
  }

  function accRenderPayrollDaily(payrollDaily) {
    var tbody = document.getElementById("acc-payroll-daily-table");
    var totalEl = document.getElementById("acc-payroll-daily-total");
    var subEl = document.getElementById("acc-payroll-daily-sub");
    if (!tbody) return;
    var hideOffice = payrollDaily && payrollDaily.office_totals_hidden;
    if (typeof payrollDaily !== "undefined" && payrollDaily && typeof payrollDaily.office_totals_hidden !== "undefined") {
      accSetOfficeSalaryAccess(!payrollDaily.office_totals_hidden);
    }
    var cols = accSalaryCategories.length ? accSalaryCategories : [];
    if (!cols.length && payrollDaily && payrollDaily.category_labels) {
      cols = Object.keys(payrollDaily.category_labels).map(function (slug) {
        var known = accSalaryCategories.find(function (c) { return c.slug === slug; });
        return known || { slug: slug, name: payrollDaily.category_labels[slug], is_office: accIsOfficeCategory(slug) };
      });
    }
    var colspan = accPayrollColspan();
    if (!payrollDaily || !payrollDaily.days || !payrollDaily.days.length) {
      tbody.innerHTML = '<tr><td colspan="' + colspan + '" class="empty">Veri yok</td></tr>';
      if (totalEl) totalEl.textContent = "—";
      if (subEl) subEl.textContent = "";
      return;
    }
    if (subEl) {
      subEl.textContent = (payrollDaily.period_start || "") + " → " + (payrollDaily.period_end || "");
      if (hideOffice) subEl.textContent += " · Ofis hariç toplam";
    }
    tbody.innerHTML = payrollDaily.days.slice().reverse().map(function (day) {
      var cur = accDisplayCurrency;
      var cells = cols.map(function (c) {
        var amt = (day.by_category && day.by_category[c.slug]) ? day.by_category[c.slug][cur] : 0;
        if (c.is_office && !accCanViewOfficeSalaries) {
          return '<td class="acc-col-office">' + accHiddenMoney() + "</td>";
        }
        return '<td' + (c.is_office ? ' class="acc-col-office"' : "") + ">" + accMoney(amt, cur) + "</td>";
      }).join("");
      var total = day.totals ? day.totals[cur] : 0;
      return '<tr><td class="mono">' + accEsc(day.date) + '</td>' +
        '<td>' + (day.active_count || 0) + (day.office_hidden ? ' <small class="muted">(ofis gizli)</small>' : '') + '</td>' +
        cells +
        '<td><strong>' + accMoney(total, cur) + '</strong></td></tr>';
    }).join("");
    if (totalEl && payrollDaily.period_accrual) {
      totalEl.textContent = accMoney(
        payrollDaily.period_accrual[accDisplayCurrency] != null
          ? payrollDaily.period_accrual[accDisplayCurrency]
          : payrollDaily.period_accrual.TRY || 0,
        accDisplayCurrency
      );
    }
  }

  function accUpdateEmpFormUi() {
    var statusEl = document.getElementById("acc-emp-status");
    var endWrap = document.getElementById("acc-emp-end-wrap");
    var endEl = document.getElementById("acc-emp-end");
    if (endWrap && statusEl) {
      var left = statusEl.value === "left";
      endWrap.hidden = !left;
      if (endEl) endEl.required = left;
      if (left && endEl && !endEl.value) endEl.value = accToday();
    }
    accUpdateOfficeRemaining();
  }

  function accUpdateOfficeRemaining() {
    var salaryEl = document.getElementById("acc-emp-salary");
    var bankEl = document.getElementById("acc-emp-bank");
    var cryptoEl = document.getElementById("acc-emp-crypto");
    var advanceEl = document.getElementById("acc-emp-advance");
    var remainEl = document.getElementById("acc-emp-remaining");
    if (!remainEl || !salaryEl) return;
    var salary = parseFloat(salaryEl.value) || 0;
    var bank = parseFloat(bankEl && bankEl.value) || 0;
    var crypto = parseFloat(cryptoEl && cryptoEl.value) || 0;
    var advance = parseFloat(advanceEl && advanceEl.value) || 0;
    remainEl.value = Math.max(salary - bank - crypto - advance, 0).toLocaleString("tr-TR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function accLoadDashboard() {
    accApi("/api/accounting/dashboard" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) {
        if (res && res.data && res.data.error) accToast(res.data.error);
        return;
      }
      accApplyPermissionsMeta(res.data);
      if (res.data.salary_categories) accApplySalaryCategories(res.data.salary_categories);
      if (res.data.departments) accApplyDepartments(res.data.departments);
      if (res.data.period_label) accUpdatePeriodLabel(res.data.period_label);
      if (res.data.rates) {
        accApplyRates(res.data.rates);
      }
      var kpiAll = res.data.kpi || {};
      var k = kpiAll[accDisplayCurrency] || kpiAll.TRY || {};
      document.getElementById("acc-kpi-deposits").textContent = accMoney(k.total_deposits, accDisplayCurrency);
      document.getElementById("acc-kpi-withdrawals").textContent = accMoney(k.total_withdrawals, accDisplayCurrency);
      document.getElementById("acc-kpi-commission").textContent = accMoney(k.total_commission, accDisplayCurrency);
      document.getElementById("acc-kpi-expenses").textContent = accMoney(k.total_expenses, accDisplayCurrency);
      var netEl = document.getElementById("acc-kpi-net");
      netEl.textContent = accMoney(k.net_profit, accDisplayCurrency);
      netEl.classList.toggle("negative", (k.net_profit || 0) < 0);
      var hint = document.getElementById("acc-kpi-payroll-hint");
      if (hint) {
        hint.textContent = "Personel hak edişi: " + accMoney(k.payroll_monthly || 0, accDisplayCurrency);
      }
      var sub = document.getElementById("acc-kpi-net-sub");
      if (sub && kpiAll.TRY) {
        var others = ["TRY", "USD", "EUR"].filter(function (c) { return c !== accDisplayCurrency; });
        sub.textContent = others.map(function (c) {
          var kk = kpiAll[c];
          return c + ": " + accMoney(kk ? kk.net_profit : 0, c);
        }).join(" · ");
      }
      accRenderPayrollDaily(res.data.payroll_daily);
    });
  }

  function accLoadPaymentMethods() {
    return accApi("/api/accounting/payment-methods").then(function (res) {
      if (!res || !res.ok) return;
      accPaymentMethods = res.data.payment_methods || [];
      accRefreshTxPaymentSelect();
      var tbody = document.getElementById("acc-pm-table");
      if (!tbody) return;
      if (!accPaymentMethods.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty">Henüz payment tanımı yok</td></tr>';
        return;
      }
      tbody.innerHTML = accPaymentMethods.map(function (p) {
        return '<tr><td><strong>' + accEsc(p.name) + '</strong></td>' +
          '<td><span class="tag ' + (p.tx_type === "deposit" ? "online" : "offline") + '">' + accTxTypeLabel(p.tx_type) + '</span></td>' +
          '<td><input type="number" class="acc-inline-rate" data-pm-id="' + p.id + '" value="' + p.commission_rate + '" step="0.01" min="0" style="width:80px;padding:0.3rem;"></td>' +
          '<td class="mono muted">' + accEsc((p.updated_at || p.created_at || "").slice(0, 10)) + '</td>' +
          '<td><button class="btn btn-sm btn-danger" data-del-pm="' + p.id + '">Sil</button></td></tr>';
      }).join("");
      tbody.querySelectorAll(".acc-inline-rate").forEach(function (inp) {
        inp.addEventListener("change", function () {
          accApi("/api/accounting/payment-methods/" + inp.getAttribute("data-pm-id"), {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ commission_rate: parseFloat(inp.value) || 0 })
          }).then(function (r) {
            if (r && r.ok) { accToast("Komisyon oranı güncellendi"); accLoadPaymentMethods(); }
            else if (r) alert(r.data.error || "Hata");
          });
        });
      });
      tbody.querySelectorAll("[data-del-pm]").forEach(function (btn) {
        btn.onclick = function () {
          if (!confirm("Silinsin mi?")) return;
          accApi("/api/accounting/payment-methods/" + btn.getAttribute("data-del-pm"), { method: "DELETE" })
            .then(function (r) {
              if (r && r.ok) { accLoadPaymentMethods(); accToast("Silindi"); }
              else if (r) alert(r.data.error || "Hata");
            });
        };
      });
    });
  }

  function accLoadTransactions() {
    return accApi("/api/accounting/transactions" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.period_label) accUpdatePeriodLabel(res.data.period_label);
      accData["acc-tx"].rows = res.data.transactions || [];
      accRenderTransactions();
    });
  }

  function accRenderTransactions() {
    var tbody = document.getElementById("acc-tx-table");
    var rows = accSortRows("acc-tx", accData["acc-tx"].rows, {
      tx_date: function (r) { return r.tx_date; },
      payment_name: function (r) { return r.payment_name; },
      tx_type: function (r) { return r.tx_type; },
      amount: function (r) { return r.amount; },
      commission_rate: function (r) { return r.commission_rate; },
      commission_amount: function (r) { return r.commission_amount; }
    });
    if (!accData["acc-tx"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Kayıt yok</td></tr>';
      accUpdateFoot("acc-tx", 0, "işlem");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return '<tr><td class="mono">' + accEsc(r.tx_date) + '</td>' +
        '<td>' + accEsc(r.payment_name) + '</td>' +
        '<td><span class="tag ' + (r.tx_type === "deposit" ? "online" : "offline") + '">' + accTxTypeLabel(r.tx_type) + '</span></td>' +
        '<td>' + accMoneyCellHtml(r, "amount") + '</td>' +
        '<td>' + r.commission_rate + '%</td>' +
        '<td>' + accMoneyCellHtml(r, "commission_amount") + '</td>' +
        '<td><button class="btn btn-sm btn-danger" data-del-tx="' + r.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-del-tx]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/transactions/" + btn.getAttribute("data-del-tx"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadTransactions(); accLoadDashboard(); accToast("Silindi"); } });
      };
    });
    accUpdateFoot("acc-tx", accData["acc-tx"].rows.length, "işlem");
    accUpdateSortHeaders("acc-tx");
  }

  function accLoadCategories() {
    return accApi("/api/accounting/expense-categories").then(function (res) {
      if (!res || !res.ok) return;
      accCategories = res.data.categories || [];
      var sel = document.getElementById("acc-exp-category");
      if (sel) {
        sel.innerHTML = accCategories.length
          ? accCategories.map(function (c) { return '<option value="' + c.id + '">' + accEsc(c.name) + '</option>'; }).join("")
          : '<option value="">Kategori ekleyin</option>';
      }
      var chips = document.getElementById("acc-cat-chips");
      if (chips) {
        chips.innerHTML = accCategories.map(function (c) {
          return '<span class="acc-chip">' + accEsc(c.name) +
            ' <button type="button" data-del-cat="' + c.id + '" title="Sil">×</button></span>';
        }).join("") || '<span class="muted">Henüz kategori yok</span>';
        chips.querySelectorAll("[data-del-cat]").forEach(function (btn) {
          btn.onclick = function () {
            if (!confirm("Kategori silinsin mi?")) return;
            accApi("/api/accounting/expense-categories/" + btn.getAttribute("data-del-cat"), { method: "DELETE" })
              .then(function (r) {
                if (r && r.ok) { accLoadCategories(); accToast("Silindi"); }
                else if (r) alert(r.data.error || "Hata");
              });
          };
        });
      }
    });
  }

  function accLoadExpenses() {
    return accApi("/api/accounting/expenses" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.period_label) accUpdatePeriodLabel(res.data.period_label);
      accData["acc-exp"].rows = res.data.expenses || [];
      accRenderExpenses();
    });
  }

  function accRenderExpenses() {
    var tbody = document.getElementById("acc-exp-table");
    var rows = accSortRows("acc-exp", accData["acc-exp"].rows, {
      expense_date: function (r) { return r.expense_date; },
      category_name: function (r) { return r.category_name; },
      description: function (r) { return r.description; },
      amount: function (r) { return r.amount; }
    });
    if (!accData["acc-exp"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Gider yok</td></tr>';
      accUpdateFoot("acc-exp", 0, "gider");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return '<tr><td class="mono">' + accEsc(r.expense_date) + '</td>' +
        '<td><span class="tag">' + accEsc(r.category_name) + '</span></td>' +
        '<td>' + accEsc(r.description || "—") + '</td>' +
        '<td>' + accMoneyCellHtml(r, "amount") + '</td>' +
        '<td><button class="btn btn-sm btn-danger" data-del-exp="' + r.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-del-exp]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/expenses/" + btn.getAttribute("data-del-exp"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadExpenses(); accLoadDashboard(); accToast("Silindi"); } });
      };
    });
    accUpdateFoot("acc-exp", accData["acc-exp"].rows.length, "gider");
    accUpdateSortHeaders("acc-exp");
  }

  function accLoadVault() {
    return accApi("/api/accounting/vault-transactions" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.period_label) accUpdatePeriodLabel(res.data.period_label);
      accData["acc-vault"].rows = res.data.vault_transactions || [];
      accRenderVault();
    });
  }

  function accRenderVault() {
    var tbody = document.getElementById("acc-vault-table");
    var rows = accSortRows("acc-vault", accData["acc-vault"].rows, {
      tx_date: function (r) { return r.tx_date; },
      vault_name: function (r) { return r.vault_name; },
      tx_type: function (r) { return r.tx_type; },
      description: function (r) { return r.description; },
      amount: function (r) { return r.amount; }
    });
    if (!accData["acc-vault"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Kayıt yok</td></tr>';
      accUpdateFoot("acc-vault", 0, "kayıt");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return '<tr><td class="mono">' + accEsc(r.tx_date) + '</td>' +
        '<td><strong>' + accEsc(r.vault_name) + '</strong></td>' +
        '<td><span class="tag ' + (r.tx_type === "in" ? "online" : "offline") + '">' + accVaultTypeLabel(r.tx_type) + '</span></td>' +
        '<td>' + accEsc(r.description || "—") + '</td>' +
        '<td>' + accMoneyCellHtml(r, "amount") + '</td>' +
        '<td><button class="btn btn-sm btn-danger" data-del-vault="' + r.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-del-vault]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/vault-transactions/" + btn.getAttribute("data-del-vault"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadVault(); accToast("Silindi"); } });
      };
    });
    accUpdateFoot("acc-vault", accData["acc-vault"].rows.length, "kayıt");
    accUpdateSortHeaders("acc-vault");
  }

  function accLoadEmployees() {
    return accApi("/api/accounting/employees" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      accApplyPermissionsMeta(res.data);
      if (res.data.salary_categories) accApplySalaryCategories(res.data.salary_categories);
      if (res.data.departments) accApplyDepartments(res.data.departments);
      if (res.data.period_label) {
        accUpdatePeriodLabel(res.data.period_label);
        var empPeriod = document.getElementById("acc-emp-period-label");
        if (empPeriod) empPeriod.textContent = res.data.period_label;
      }
      accData["acc-emp"].rows = res.data.employees || [];
      accRefreshEmpFilters();
      accRenderEmployees();
    });
  }

  function accOrderEmployees(rows) {
    return (rows || []).slice().sort(function (a, b) {
      var sa = a.status === "active" ? 0 : 1;
      var sb = b.status === "active" ? 0 : 1;
      if (sa !== sb) return sa - sb;
      var dc = String(a.department || "").localeCompare(String(b.department || ""), "tr", { sensitivity: "base" });
      if (dc !== 0) return dc;
      return String(a.name || "").localeCompare(String(b.name || ""), "tr", { sensitivity: "base" });
    });
  }

  function accEmpSelectHtml(field, value, empId, options, extraCls) {
    return '<select class="acc-emp-inline ' + (extraCls || "") + '" data-emp-field="' + field + '" data-emp-id="' + empId + '">' +
      options.map(function (o) {
        var sel = String(o.value) === String(value) ? " selected" : "";
        return '<option value="' + accEsc(o.value) + '"' + sel + ">" + accEsc(o.label) + "</option>";
      }).join("") + "</select>";
  }

  function accEmpInputHtml(field, value, empId, extraCls, type, step, placeholder) {
    return '<input type="' + (type || "text") + '" class="acc-emp-inline ' + (extraCls || "") + '"' +
      ' data-emp-field="' + field + '" data-emp-id="' + empId + '"' +
      (step ? ' step="' + step + '"' : "") +
      (placeholder ? ' placeholder="' + accEsc(placeholder) + '"' : "") +
      ' value="' + accEsc(value != null && value !== "" ? value : "") + '">';
  }

  function accSaveEmployeeField(empId, patch, onFail) {
    return accApi("/api/accounting/employees/" + empId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    }).then(function (r) {
      if (r && r.ok) {
        accLoadEmployees();
        accLoadDashboard();
        accToast("Personel güncellendi");
      } else if (r) {
        alert(r.data.error || "Hata");
        if (onFail) onFail();
        else accLoadEmployees();
      }
    });
  }

  function accEmpPayInfoHtml(r, hidden) {
    if (hidden) return accHiddenMoney();
    return '<div class="acc-emp-payinfo">' +
      '<label>TRC20</label>' +
      accEmpInputHtml("crypto_wallet", r.crypto_wallet || "", r.id, "acc-emp-inline-wallet") +
      '<label>IBAN</label>' +
      accEmpInputHtml("bank_iban", r.bank_iban || "", r.id, "acc-emp-inline-wallet") +
      '<label>Ad Soyad</label>' +
      accEmpInputHtml("bank_account_name", r.bank_account_name || "", r.id, "acc-emp-inline-wide") +
      "</div>";
  }

  function accEmpRowHtml(r) {
    var cur = r.currency || "TRY";
    var rowCls = r.status === "left" ? "acc-emp-row-left" : "";
    var deptOpts = accEmployeeDepartments.map(function (d) {
      return { value: d.name, label: d.name };
    });
    var catOpts = accSalaryCategories.map(function (c) {
      return { value: c.slug, label: c.name };
    });
    var statusCls = r.status === "active" ? "active-status" : "left-status";
    var hidden = r.salary_hidden;
    var nameCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("name", r.name, r.id, "acc-emp-inline-wide");
    var catCell = hidden ? accHiddenMoney() : accEmpSelectHtml("salary_category", r.salary_category, r.id, catOpts);
    var deptCell = accEmpSelectHtml("department", r.department, r.id, deptOpts);
    var refCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("notes", r.notes || "", r.id, "acc-emp-inline-wide", "text", null, "Referans / not");
    var locCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("location", r.location || "", r.id, "acc-emp-inline-wide", "text", null, "Konum");
    var startCell = accEmpInputHtml("start_date", r.start_date, r.id, "", "date");
    var endCell = r.status === "left"
      ? accEmpInputHtml("end_date", r.end_date || "", r.id, "", "date")
      : '<span class="muted">—</span>';
    var salaryCell = hidden
      ? accHiddenMoney()
      : ('<div style="display:flex;align-items:center;gap:0.25rem;">' +
        accEmpInputHtml("salary", r.salary, r.id, "acc-emp-inline-salary", "number", "0.01") +
        '<small class="muted">' + accEsc(cur) + "</small></div>" +
        '<small class="muted">' + accMoney(r.salary_try, "TRY") + " · " + accMoney(r.salary_usd, "USD") + " · " + accMoney(r.salary_eur, "EUR") + "</small>");
    var bankCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("bank_salary", r.bank_salary || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var cryptoCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("crypto_salary", r.crypto_salary || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var advanceCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("advance_amount", r.advance_amount || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var bonusCell = hidden
      ? accHiddenMoney()
      : accEmpInputHtml("bonus_amount", r.bonus_amount || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var remainCell = hidden
      ? accHiddenMoney()
      : ('<span class="acc-emp-remain-cell">' + accMoney(r.payment_remaining != null ? r.payment_remaining : r.office_remaining, cur) + "</span>");
    var payInfoCell = accEmpPayInfoHtml(r, hidden);
    var accrualCell = accPayrollTriCurCellHtml(r.accrual, hidden);
    var netCell = accPayrollTriCurCellHtml(r.net_accrual, hidden);
    var statusCell = accEmpSelectHtml("status", r.status || "active", r.id, [
      { value: "active", label: "Aktif Çalışıyor" },
      { value: "left", label: "Ayrıldı" }
    ], "acc-emp-status-select " + statusCls);
    return '<tr class="' + rowCls + '">' +
      "<td>" + nameCell + "</td>" +
      "<td>" + refCell + "</td>" +
      "<td>" + catCell + "</td>" +
      "<td>" + deptCell + "</td>" +
      "<td>" + locCell + "</td>" +
      '<td class="mono">' + startCell + "</td>" +
      '<td class="mono">' + endCell + "</td>" +
      "<td>" + salaryCell + "</td>" +
      "<td>" + bankCell + "</td>" +
      "<td>" + cryptoCell + "</td>" +
      "<td>" + advanceCell + "</td>" +
      "<td>" + bonusCell + "</td>" +
      "<td>" + remainCell + "</td>" +
      "<td>" + payInfoCell + "</td>" +
      "<td>" + accrualCell + "</td>" +
      "<td>" + netCell + "</td>" +
      "<td>" + statusCell + "</td>" +
      '<td><button class="btn btn-sm btn-danger" data-del-emp="' + r.id + '">Sil</button></td></tr>';
  }

  function accBindEmployeeInlineEditors(tbody) {
    tbody.querySelectorAll("[data-emp-field]").forEach(function (el) {
      el.addEventListener("change", function () {
        var field = el.getAttribute("data-emp-field");
        var empId = el.getAttribute("data-emp-id");
        var patch = {};
        if (field === "salary" || field === "bank_salary" || field === "crypto_salary" || field === "advance_amount" || field === "bonus_amount") {
          var num = parseFloat(el.value);
          if (isNaN(num) || num < 0) {
            alert("Geçerli tutar girin.");
            accLoadEmployees();
            return;
          }
          patch[field] = num;
        } else {
          patch[field] = el.value;
        }
        if (field === "status") {
          if (patch.status === "left") {
            var endDate = prompt("Çıkış tarihi (YYYY-MM-DD):", accToday());
            if (!endDate) {
              accLoadEmployees();
              return;
            }
            patch.end_date = endDate;
          } else {
            patch.end_date = null;
          }
        }
        accSaveEmployeeField(empId, patch);
      });
    });
  }

  function accSaveEmployeeAdvance(empId, value, inputEl) {
    accSaveEmployeeField(empId, { advance_amount: value }, function () {
      if (inputEl) accLoadEmployees();
    });
  }

  function accRenderEmployees() {
    var tbody = document.getElementById("acc-emp-table");
    var filtered = accFilteredEmployees();
    var ordered = accOrderEmployees(filtered);
    var activeRows = ordered.filter(function (r) { return r.status === "active"; });
    var leftRows = ordered.filter(function (r) { return r.status === "left"; });
    var cols = 18;

    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="' + cols + '" class="empty">' +
        (accData["acc-emp"].rows.length ? "Bu dönemde personel yok" : "Personel yok") + "</td></tr>";
      accUpdateFoot("acc-emp", 0, "personel");
      accUpdateEmpPayrollTotals([]);
      return;
    }

    var html = "";
    if (activeRows.length) {
      html += '<tr class="acc-emp-section acc-emp-section-active"><td colspan="' + cols + '">● Aktif Çalışanlar (' + activeRows.length + ")</td></tr>";
      html += activeRows.map(accEmpRowHtml).join("");
    }
    if (leftRows.length) {
      html += '<tr class="acc-emp-section acc-emp-section-left"><td colspan="' + cols + '">● İşten Ayrılanlar (' + leftRows.length + ")</td></tr>";
      html += leftRows.map(accEmpRowHtml).join("");
    }
    tbody.innerHTML = html;

    accBindEmployeeInlineEditors(tbody);
    tbody.querySelectorAll("[data-del-emp]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/employees/" + btn.getAttribute("data-del-emp"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadEmployees(); accLoadDashboard(); accToast("Silindi"); } });
      };
    });
    accUpdateFoot("acc-emp", filtered.length, "personel");
    accUpdateEmpPayrollTotals(filtered);
  }

  function accSwitchTab(tab) {
    accActiveTab = tab;
    document.querySelectorAll(".acc-tab").forEach(function (el) {
      el.classList.toggle("active", el.getAttribute("data-acc-tab") === tab);
    });
    document.querySelectorAll(".acc-pane").forEach(function (el) {
      var show = el.getAttribute("data-acc-pane") === tab;
      el.classList.toggle("active", show);
      el.hidden = !show;
    });
    if (tab === "dashboard") accLoadDashboard();
    else if (tab === "transactions") { accLoadPaymentMethods(); accLoadTransactions(); }
    else if (tab === "commissions") accLoadPaymentMethods();
    else if (tab === "expenses") { accLoadCategories(); accLoadExpenses(); }
    else if (tab === "vault") accLoadVault();
    else if (tab === "payroll") { accLoadEmpOptions(); accLoadEmployees(); }
  }

  function accRefreshAll() {
    accLoadDashboard();
    if (accActiveTab === "transactions") { accLoadPaymentMethods(); accLoadTransactions(); }
    else if (accActiveTab === "commissions") accLoadPaymentMethods();
    else if (accActiveTab === "expenses") { accLoadCategories(); accLoadExpenses(); }
    else if (accActiveTab === "vault") accLoadVault();
    else if (accActiveTab === "payroll") { accLoadEmpOptions(); accLoadEmployees(); }
  }

  function accInitForms() {
    ["acc-tx-date", "acc-exp-date", "acc-vault-date", "acc-emp-start"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.value) el.value = accToday();
    });

    document.getElementById("acc-tx-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({
          tx_date: document.getElementById("acc-tx-date").value,
          payment_method_id: document.getElementById("acc-tx-payment").value,
          tx_type: document.getElementById("acc-tx-type").value,
          amount: document.getElementById("acc-tx-amount").value,
          currency: document.getElementById("acc-tx-currency").value
        }, accReadFormRates("acc-tx-rate-usd", "acc-tx-rate-eur")))
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-tx-amount").value = "";
          accClearFormRates("acc-tx-rate-usd", "acc-tx-rate-eur");
          accLoadTransactions(); accLoadDashboard(); accSavedToast("İşlem kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    document.getElementById("acc-pm-form").addEventListener("submit", function (e) {
      e.preventDefault();
      var txType = document.getElementById("acc-pm-type").value;
      if (!txType) { alert("İşlem türü seçin: Yatırım veya Çekim."); return; }
      accApi("/api/accounting/payment-methods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: document.getElementById("acc-pm-name").value.trim(),
          tx_type: txType,
          commission_rate: document.getElementById("acc-pm-rate").value
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-pm-name").value = "";
          document.getElementById("acc-pm-type").value = "";
          accLoadPaymentMethods(); accToast("Payment eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    var txTypeEl = document.getElementById("acc-tx-type");
    if (txTypeEl) {
      txTypeEl.addEventListener("change", accRefreshTxPaymentSelect);
    }

    document.getElementById("acc-cat-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/expense-categories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: document.getElementById("acc-cat-name").value.trim() })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-cat-name").value = "";
          accLoadCategories(); accToast("Kategori eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    var deptForm = document.getElementById("acc-dept-form");
    if (deptForm) {
      deptForm.addEventListener("submit", function (e) {
        e.preventDefault();
        accApi("/api/accounting/employee-departments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: document.getElementById("acc-dept-name").value.trim() })
        }).then(function (r) {
          if (r && r.ok) {
            document.getElementById("acc-dept-name").value = "";
            accLoadEmpOptions(); accToast("Departman eklendi");
          } else if (r) alert(r.data.error || "Hata");
        });
      });
    }

    var salaryCatForm = document.getElementById("acc-salary-cat-form");
    if (salaryCatForm) {
      salaryCatForm.addEventListener("submit", function (e) {
        e.preventDefault();
        accApi("/api/accounting/salary-categories", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: document.getElementById("acc-salary-cat-name").value.trim(),
            is_office: document.getElementById("acc-salary-cat-office").checked
          })
        }).then(function (r) {
          if (r && r.ok) {
            document.getElementById("acc-salary-cat-name").value = "";
            document.getElementById("acc-salary-cat-office").checked = false;
            accLoadEmpOptions(); accLoadDashboard(); accToast("Maaş kategorisi eklendi");
          } else if (r) alert(r.data.error || "Hata");
        });
      });
    }

    document.getElementById("acc-exp-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/expenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.assign({
          expense_date: document.getElementById("acc-exp-date").value,
          category_id: document.getElementById("acc-exp-category").value,
          amount: document.getElementById("acc-exp-amount").value,
          currency: document.getElementById("acc-exp-currency").value,
          description: document.getElementById("acc-exp-desc").value.trim()
        }, accReadFormRates("acc-exp-rate-usd", "acc-exp-rate-eur")))
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-exp-amount").value = "";
          document.getElementById("acc-exp-desc").value = "";
          accClearFormRates("acc-exp-rate-usd", "acc-exp-rate-eur");
          accLoadExpenses(); accLoadDashboard(); accSavedToast("Gider kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    document.getElementById("acc-vault-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/vault-transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(Object.assign({
          tx_date: document.getElementById("acc-vault-date").value,
          vault_name: document.getElementById("acc-vault-name").value.trim(),
          tx_type: document.getElementById("acc-vault-type").value,
          amount: document.getElementById("acc-vault-amount").value,
          currency: document.getElementById("acc-vault-currency").value,
          description: document.getElementById("acc-vault-desc").value.trim()
        }, accReadFormRates("acc-vault-rate-usd", "acc-vault-rate-eur")))
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-vault-amount").value = "";
          document.getElementById("acc-vault-desc").value = "";
          accClearFormRates("acc-vault-rate-usd", "acc-vault-rate-eur");
          accLoadVault(); accSavedToast("Kasa işlemi kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    document.getElementById("acc-emp-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accUpdateEmpFormUi();
      var status = document.getElementById("acc-emp-status").value;
      var payload = Object.assign({
          name: document.getElementById("acc-emp-name").value.trim(),
          notes: (document.getElementById("acc-emp-reference").value || "").trim(),
          salary_category: document.getElementById("acc-emp-category").value,
          department: document.getElementById("acc-emp-dept").value,
          start_date: document.getElementById("acc-emp-start").value,
            salary: document.getElementById("acc-emp-salary").value,
            currency: document.getElementById("acc-emp-currency").value,
            status: status,
            bank_salary: document.getElementById("acc-emp-bank").value || 0,
            crypto_salary: document.getElementById("acc-emp-crypto").value || 0,
            advance_amount: document.getElementById("acc-emp-advance").value || 0,
            bonus_amount: document.getElementById("acc-emp-bonus").value || 0
        }, accReadFormRates("acc-emp-rate-usd", "acc-emp-rate-eur"));
      if (status === "left") {
        payload.end_date = document.getElementById("acc-emp-end").value;
      }
      accApi("/api/accounting/employees", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-emp-name").value = "";
          document.getElementById("acc-emp-reference").value = "";
          document.getElementById("acc-emp-salary").value = "";
          document.getElementById("acc-emp-bank").value = "0";
          document.getElementById("acc-emp-crypto").value = "0";
          document.getElementById("acc-emp-advance").value = "0";
          document.getElementById("acc-emp-bonus").value = "0";
          document.getElementById("acc-emp-status").value = "active";
          document.getElementById("acc-emp-end").value = "";
          accClearFormRates("acc-emp-rate-usd", "acc-emp-rate-eur");
          accUpdateEmpFormUi();
          accLoadEmployees(); accLoadDashboard(); accSavedToast("Personel eklendi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });
    ["acc-emp-status", "acc-emp-category"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", accUpdateEmpFormUi);
    });
    ["acc-emp-salary", "acc-emp-bank", "acc-emp-crypto", "acc-emp-advance", "acc-emp-bonus"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", accUpdateOfficeRemaining);
    });
    accUpdateEmpFormUi();
    accBindFxPreview("acc-tx-amount", "acc-tx-currency", "acc-tx-fx-preview", "acc-tx-rate-usd", "acc-tx-rate-eur");
    accBindFxPreview("acc-exp-amount", "acc-exp-currency", "acc-exp-fx-preview", "acc-exp-rate-usd", "acc-exp-rate-eur");
    accBindFxPreview("acc-vault-amount", "acc-vault-currency", "acc-vault-fx-preview", "acc-vault-rate-usd", "acc-vault-rate-eur");
    accBindFxPreview("acc-emp-salary", "acc-emp-currency", "acc-emp-fx-preview", "acc-emp-rate-usd", "acc-emp-rate-eur");
  }

  function accInitPeriodFilter() {
    var modeEl = document.getElementById("acc-filter-period");
    var monthEl = document.getElementById("acc-filter-month");
    if (modeEl) modeEl.value = accPeriodMode;
    if (monthEl) {
      if (accPeriodMode === "pick" && /^\d{4}-\d{2}$/.test(accPeriod)) {
        monthEl.value = accPeriod;
      } else {
        monthEl.value = accCurrentMonth();
      }
    }
    accResolvePeriod();
  }

  function accInitUi() {
    accInitPeriodFilter();
    var dispCur = document.getElementById("acc-display-currency");
    if (dispCur) {
      dispCur.value = accDisplayCurrency;
      dispCur.addEventListener("change", function () {
        accDisplayCurrency = dispCur.value;
        localStorage.setItem("acc_display_currency", accDisplayCurrency);
        accLoadDashboard();
        accRerenderTable("acc-tx");
        accRerenderTable("acc-exp");
        accRerenderTable("acc-vault");
        accRerenderTable("acc-emp");
        if (accActiveTab === "payroll") { accLoadEmpOptions(); accLoadEmployees(); }
      });
    }
    document.querySelectorAll(".acc-tab").forEach(function (btn) {
      btn.addEventListener("click", function () {
        accSwitchTab(btn.getAttribute("data-acc-tab"));
      });
    });
    document.getElementById("acc-filter-period").addEventListener("change", function () {
      accResolvePeriod();
      accRefreshAll();
    });
    var accMonthFilter = document.getElementById("acc-filter-month");
    if (accMonthFilter) {
      accMonthFilter.addEventListener("change", function () {
        var modeEl = document.getElementById("acc-filter-period");
        if (modeEl) modeEl.value = "pick";
        accResolvePeriod();
        accRefreshAll();
      });
    }
    document.querySelectorAll("[data-acc-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        accToggleExpand(btn.getAttribute("data-acc-toggle"));
      });
    });
    document.querySelectorAll("[data-acc-sort]").forEach(function (th) {
      th.addEventListener("click", function () {
        accToggleSort(th.getAttribute("data-acc-sort"), th.getAttribute("data-sort"));
      });
    });
    var goto = document.getElementById("acc-goto-commissions");
    if (goto) goto.addEventListener("click", function () { accSwitchTab("commissions"); });

    var empFilterCat = document.getElementById("acc-emp-filter-cat");
    var empFilterDept = document.getElementById("acc-emp-filter-dept");
    var empCurView = document.getElementById("acc-emp-currency-view");
    var empFilterClear = document.getElementById("acc-emp-filter-clear");
    if (empFilterCat) {
      empFilterCat.addEventListener("change", function () {
        accEmpFilterCat = empFilterCat.value;
        accRenderEmployees();
      });
    }
    if (empFilterDept) {
      empFilterDept.addEventListener("change", function () {
        accEmpFilterDept = empFilterDept.value;
        accRenderEmployees();
      });
    }
    if (empCurView) {
      empCurView.addEventListener("change", function () {
        accEmpCurrencyView = empCurView.value;
        localStorage.setItem("acc_emp_currency_view", accEmpCurrencyView);
        accRenderEmployees();
      });
    }
    if (empFilterClear) {
      empFilterClear.addEventListener("click", function () {
        accEmpFilterCat = "";
        accEmpFilterDept = "";
        if (empFilterCat) empFilterCat.value = "";
        if (empFilterDept) empFilterDept.value = "";
        accRenderEmployees();
      });
    }
    accRefreshEmpFilters();
  }

  window.MakroAccounting = {
    init: function () {
      accLoadRates().then(function () {
        accInitForms();
        accInitUi();
        accStartRatesPolling();
        accSwitchTab("dashboard");
      });
    },
    refresh: accRefreshAll,
    onShow: function () {
      accLoadRates().then(accRefreshAll);
      accStartRatesPolling();
    },
    setPermissions: function (perms) {
      var list = perms || [];
      var canView = list.indexOf("*") >= 0 || list.indexOf("accounting.payroll.office_salaries") >= 0;
      accSetOfficeSalaryAccess(canView);
    }
  };
})();
