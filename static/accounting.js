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
  var accVaults = [];
  var accVaultMethods = [];
  var accVaultMethodOptions = [];
  var accVaultOperationTypes = [];
  var accVaultOperationTypeOptions = [];
  var accVaultFilterId = localStorage.getItem("acc_vault_filter") || "";

  var accData = {
    "acc-tx": { rows: [], expanded: false, sortKey: "tx_date", sortDir: "desc" },
    "acc-exp": { rows: [], expanded: false, sortKey: "expense_date", sortDir: "desc", filterCat: "", filterQ: "" },
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
    return '<span class="acc-salary-blurred muted">•••••</span>';
  }

  function accSalaryHidden(r) {
    return !!(r && r.salary_hidden);
  }

  function accSalaryRedacted(r) {
    return !!(r && (r.salary_hidden || r.salary_redacted));
  }

  function accApplyPermissionsMeta(data) {
    if (data && typeof data.can_view_office_salaries !== "undefined") {
      accSetOfficeSalaryAccess(data.can_view_office_salaries);
    }
  }

  function accApi(path, opts) {
    opts = opts || {};
    var timeoutMs = opts.timeoutMs || 12000;
    var controller = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = controller ? setTimeout(function () { controller.abort(); }, timeoutMs) : null;
    var fetchOpts = Object.assign({}, opts);
    delete fetchOpts.timeoutMs;
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
    var usdEl = usdId ? document.getElementById(usdId) : null;
    var eurEl = eurId ? document.getElementById(eurId) : null;
    var body = {};
    var usdVal = usdEl && usdEl.value.trim();
    var eurVal = eurEl && eurEl.value.trim();
    if (usdVal && eurVal) {
      body.rate_usd_try = usdVal;
      body.rate_eur_try = eurVal;
    } else if (usdVal) {
      body.rate_usd_try = usdVal;
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
    if (!data) return;
    var usd = parseFloat(data.usd_try);
    var eur = parseFloat(data.eur_try);
    if (!usd && !eur) return;
    accRates = {
      usd_try: usd || accRates.usd_try,
      eur_try: eur || accRates.eur_try,
      date: data.date != null ? data.date : accRates.date,
      source: data.source || accRates.source,
      fetched_at: data.fetched_at != null ? data.fetched_at : accRates.fetched_at
    };
    accUpdateRatePlaceholders();
    if (accActiveTab === "vault") {
      accUpdateVaultFormRateBadge();
      accUpdateVaultTlPreview();
    }
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
      if (accRates.usd_try && accRates.eur_try) {
        var srcNote = accRates.source === "fallback" ? " (yaklaşık)" : "";
        badge.textContent = "USD/TL " + accFormatRate(accRates.usd_try) +
          " · EUR/TL " + accFormatRate(accRates.eur_try) + srcNote + accRateTimeLabel();
      } else {
        badge.textContent = "Kur yükleniyor…";
      }
    }
  }

  function accLoadRates() {
    return accApi("/api/accounting/exchange-rates").then(function (res) {
      if (!res || !res.ok) return;
      accApplyRates(res.data);
    }).catch(function () {});
  }

  function accApplyFallbackRates() {
    accApplyRates({
      usd_try: accRates.usd_try || 34.25,
      eur_try: accRates.eur_try || 37.10,
      source: "fallback"
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

  function accSelectedMonthPeriod() {
    accResolvePeriod();
    if (accPeriodMode !== "pick") return null;
    var monthEl = document.getElementById("acc-filter-month");
    return monthEl && monthEl.value ? monthEl.value : accCurrentMonth();
  }

  function accPaymentMethodsQuery() {
    var month = accSelectedMonthPeriod();
    return month ? "?period=" + encodeURIComponent(month) : "";
  }

  function accPeriodEndDate() {
    var month = accSelectedMonthPeriod();
    if (!month) return accToday();
    var parts = month.split("-");
    var y = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    var last = new Date(y, m, 0).getDate();
    return month + "-" + String(last).padStart(2, "0");
  }

  function accSyncTxDateToPeriod() {
    var editId = document.getElementById("acc-tx-edit-id");
    if (editId && editId.value) return;
    var el = document.getElementById("acc-tx-date");
    if (!el) return;
    if (accPeriodMode === "pick") el.value = accPeriodEndDate();
  }

  function accUpdateCommPeriodLabel(label) {
    var el = document.getElementById("acc-comm-period-label");
    if (!el) return;
    if (accSelectedMonthPeriod() && label) {
      el.textContent = "· " + label.replace(/^·\s*/, "");
    } else {
      el.textContent = accSelectedMonthPeriod() ? "" : "· Varsayılan oranlar";
    }
  }

  function accUpdateTxPeriodLabel(label) {
    var el = document.getElementById("acc-tx-period-label");
    if (el && label) el.textContent = label.replace(/^·\s*/, "");
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

  function accPayrollCompactCellHtml(map, row, hidden) {
    if (hidden) return accHiddenMoney();
    if (!map) return '<span class="muted">—</span>';
    var cur = (row && row.currency) || accEmpCurrencyView || "TRY";
    var amt = map[cur];
    if (amt == null) amt = map.TRY != null ? map.TRY : (map.USD != null ? map.USD : 0);
    return '<span class="acc-emp-money-cell">' + accMoney(amt, cur) + "</span>";
  }

  function accEmpReferansDisplay(notes) {
    if (!notes) return "";
    var s = String(notes).trim();
    var refMatch = s.match(/Ref(?:erans)?\s*:\s*([^|]+)/i);
    if (refMatch) return refMatch[1].trim();
    if (/^Panel:/i.test(s) || /Pozisyon:/i.test(s) || /Haziran kripto:/i.test(s) || /Sheet avans/i.test(s)) return "";
    if (s.length > 36) return s.slice(0, 34) + "…";
    return s;
  }

  function accEmpRefCellHtml(r, hidden) {
    if (hidden) return accHiddenMoney();
    var full = r.notes || "";
    var short = accEmpReferansDisplay(full);
    return '<input type="text" class="acc-emp-inline acc-emp-inline-ref"' +
      ' data-emp-field="notes" data-emp-id="' + r.id + '"' +
      ' title="' + accEsc(full || "Referans yok") + '"' +
      ' placeholder="—"' +
      ' value="' + accEsc(short) + '">';
  }

  function accEmpWalletCellHtml(r, hidden) {
    if (hidden) return accHiddenMoney();
    var w = r.crypto_wallet || "";
    return '<input type="text" class="acc-emp-inline acc-emp-inline-wallet"' +
      ' data-emp-field="crypto_wallet" data-emp-id="' + r.id + '"' +
      ' title="' + accEsc(w || "Cüzdan yok") + '"' +
      ' placeholder="TRC20"' +
      ' value="' + accEsc(w) + '">';
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
      if (accSalaryRedacted(r)) return;
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
    accUpdateEmpPanelTotals(rows);
  }

  function accSumPanelPayroll(rows, panel) {
    var panelRows = (rows || []).filter(function (r) { return accEmpPanelSide(r) === panel; });
    var cur = accEmpCurrencyView;
    var gross = 0;
    var net = 0;
    var advance = 0;
    var hiddenCount = 0;
    panelRows.forEach(function (r) {
      if (accSalaryRedacted(r)) {
        hiddenCount++;
        return;
      }
      gross += accAccrualValue(r);
      net += accNetAccrualValue(r);
      advance += accAdvanceDisplay(r);
    });
    return {
      rows: panelRows,
      count: panelRows.length,
      active: panelRows.filter(function (r) { return r.status === "active"; }).length,
      gross: gross,
      net: net,
      advance: advance,
      cur: cur,
      allHidden: panelRows.length > 0 && hiddenCount === panelRows.length
    };
  }

  function accUpdateEmpPanelTotals(rows) {
    var office = accSumPanelPayroll(rows, "left");
    var tr = accSumPanelPayroll(rows, "right");

    var officeTotal = document.getElementById("acc-emp-office-total");
    var officeSub = document.getElementById("acc-emp-office-sub");
    var officeMeta = document.getElementById("acc-emp-office-meta");
    var trTotal = document.getElementById("acc-emp-tr-total");
    var trSub = document.getElementById("acc-emp-tr-sub");
    var trMeta = document.getElementById("acc-emp-tr-meta");

    if (officeMeta) officeMeta.textContent = office.count + " kişi · " + office.active + " aktif";
    if (trMeta) trMeta.textContent = tr.count + " kişi · " + tr.active + " aktif";

    if (officeTotal) {
      officeTotal.textContent = office.allHidden ? "Gizli" : accMoney(office.net, office.cur);
    }
    if (officeSub) {
      officeSub.textContent = office.allHidden
        ? "Ofis maaşları yetkiniz dışında"
        : ("Hak ediş " + accMoney(office.gross, office.cur) + " · Avans " + accMoney(office.advance, office.cur));
    }
    if (trTotal) trTotal.textContent = accMoney(tr.net, tr.cur);
    if (trSub) {
      trSub.textContent = "Hak ediş " + accMoney(tr.gross, tr.cur) + " · Avans " + accMoney(tr.advance, tr.cur);
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

  function accSetText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function accLoadDashboard() {
    accApi("/api/accounting/dashboard" + accPeriodQuery()).then(function (res) {
      try {
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
      accSetText("acc-kpi-deposits", accMoney(k.total_deposits, accDisplayCurrency));
      accSetText("acc-kpi-withdrawals", accMoney(k.total_withdrawals, accDisplayCurrency));
      accSetText("acc-kpi-commission", accMoney(k.total_commission, accDisplayCurrency));
      accSetText("acc-kpi-expenses", accMoney(k.total_expenses, accDisplayCurrency));
      var netEl = document.getElementById("acc-kpi-net");
      if (netEl) {
        netEl.textContent = accMoney(k.net_profit, accDisplayCurrency);
        netEl.classList.toggle("negative", (k.net_profit || 0) < 0);
      }
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
      } catch (err) {
        console.error("accLoadDashboard", err);
      }
    });
  }

  function accBindPaymentMethodTable(tbodyId, methods, txType) {
    var tbody = document.getElementById(tbodyId);
    if (!tbody) return;
    var filtered = (methods || []).filter(function (p) { return p.tx_type === txType; });
    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Henüz ' +
        (txType === "deposit" ? "yatırım" : "çekim") + ' yöntemi yok</td></tr>';
      return;
    }
    var month = accSelectedMonthPeriod();
    tbody.innerHTML = filtered.map(function (p) {
      var globalRate = p.global_commission_rate != null ? p.global_commission_rate : p.commission_rate;
      var overrideHint = p.period_rate_override
        ? '<span class="tag online" style="font-size:0.62rem;margin-left:0.25rem;">aylık</span>'
        : "";
      return '<tr><td><strong>' + accEsc(p.name) + '</strong>' + overrideHint + '</td>' +
        '<td><input type="number" class="acc-inline-rate" data-pm-id="' + p.id + '" value="' + p.commission_rate + '" step="0.01" min="0" style="width:80px;padding:0.3rem;"></td>' +
        '<td class="mono muted">' + globalRate + '%</td>' +
        '<td class="mono muted">' + accEsc((p.updated_at || p.created_at || "").slice(0, 10)) + '</td>' +
        '<td><button class="btn btn-sm btn-danger" data-del-pm="' + p.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll(".acc-inline-rate").forEach(function (inp) {
      inp.addEventListener("change", function () {
        var body = { commission_rate: parseFloat(inp.value) || 0 };
        if (month) body.period = month;
        accApi("/api/accounting/payment-methods/" + inp.getAttribute("data-pm-id"), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }).then(function (r) {
          if (r && r.ok) {
            accToast(month ? "Aylık komisyon oranı güncellendi" : "Komisyon oranı güncellendi");
            accLoadPaymentMethods();
          } else if (r) alert(r.data.error || "Hata");
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
  }

  function accLoadPaymentMethods() {
    return accApi("/api/accounting/payment-methods" + accPaymentMethodsQuery()).then(function (res) {
      if (!res || !res.ok) return;
      accPaymentMethods = res.data.payment_methods || [];
      if (res.data.period_label) accUpdateCommPeriodLabel(res.data.period_label);
      accRefreshTxPaymentSelect();
      accBindPaymentMethodTable("acc-pm-table-deposit", accPaymentMethods, "deposit");
      accBindPaymentMethodTable("acc-pm-table-withdrawal", accPaymentMethods, "withdrawal");
    });
  }

  function accTransactionPaymentTotals(rows) {
    var map = {};
    (rows || []).forEach(function (r) {
      var key = (r.payment_name || "?") + "|" + r.tx_type;
      if (!map[key]) {
        map[key] = {
          name: r.payment_name || "?",
          tx_type: r.tx_type,
          amount_try: 0,
          commission_try: 0,
          count: 0,
        };
      }
      map[key].amount_try += parseFloat(r.amount_try) || 0;
      map[key].commission_try += parseFloat(r.commission_amount_try) || 0;
      map[key].count += 1;
    });
    return Object.keys(map).map(function (k) { return map[k]; })
      .sort(function (a, b) { return b.amount_try - a.amount_try; });
  }

  function accUpdateTransactionSummary(rows) {
    var depEl = document.getElementById("acc-tx-sum-deposit");
    var wdrEl = document.getElementById("acc-tx-sum-withdrawal");
    var commEl = document.getElementById("acc-tx-sum-commission");
    var countEl = document.getElementById("acc-tx-sum-count");
    if (!depEl) return;
    var dep = 0, wdr = 0, comm = 0;
    (rows || []).forEach(function (r) {
      var tryAmt = parseFloat(r.amount_try) || 0;
      var commAmt = parseFloat(r.commission_amount_try) || 0;
      if (r.tx_type === "withdrawal") wdr += tryAmt;
      else dep += tryAmt;
      comm += commAmt;
    });
    depEl.textContent = accMoney(dep, "TRY");
    wdrEl.textContent = accMoney(wdr, "TRY");
    commEl.textContent = accMoney(comm, "TRY");
    if (countEl) countEl.textContent = String((rows || []).length);
    accRenderTransactionPmCards(rows);
  }

  function accRenderTransactionPmCards(rows) {
    var el = document.getElementById("acc-tx-pm-cards");
    if (!el) return;
    var totals = accTransactionPaymentTotals(rows);
    if (!totals.length) {
      el.innerHTML = '<div class="acc-exp-cat-card acc-exp-cat-card-empty muted">Bu dönemde işlem yok</div>';
      return;
    }
    el.innerHTML = totals.map(function (t) {
      var cls = t.tx_type === "deposit" ? "acc-exp-cat-salary" : "acc-exp-cat-office";
      return '<div class="acc-exp-cat-card ' + cls + '">' +
        '<div class="acc-exp-cat-card-head">' +
          '<span class="acc-exp-cat-card-name">' + accEsc(t.name) + '</span>' +
          '<span class="acc-exp-cat-card-count">' + accTxTypeLabel(t.tx_type) + " · " + t.count + '</span>' +
        '</div>' +
        '<strong class="acc-exp-cat-card-try">' + accMoney(t.amount_try, "TRY") + '</strong>' +
        '<span class="acc-exp-cat-card-usd">Kom: ' + accMoney(t.commission_try, "TRY") + '</span>' +
      '</div>';
    }).join("");
  }

  function accSetTxFormMode(editing) {
    var title = document.getElementById("acc-tx-form-title");
    var submit = document.getElementById("acc-tx-submit");
    var cancel = document.getElementById("acc-tx-edit-cancel");
    var section = document.getElementById("acc-tx-form-section");
    if (title) title.textContent = editing ? "İşlemi Düzenle" : "Yeni İşlem";
    if (submit) submit.textContent = editing ? "Güncelle" : "Kaydet";
    if (cancel) cancel.hidden = !editing;
    if (section) section.classList.toggle("acc-exp-form-editing", !!editing);
  }

  function accResetTxForm() {
    var editId = document.getElementById("acc-tx-edit-id");
    if (editId) editId.value = "";
    var amount = document.getElementById("acc-tx-amount");
    if (amount) amount.value = "";
    accClearFormRates("acc-tx-rate-usd", "acc-tx-rate-eur");
    var preview = document.getElementById("acc-tx-fx-preview");
    if (preview) preview.textContent = "";
    accSetTxFormMode(false);
    accSyncTxDateToPeriod();
    accRenderTransactions();
  }

  function accStartTxEdit(row) {
    if (!row) return;
    var editId = document.getElementById("acc-tx-edit-id");
    var dateEl = document.getElementById("acc-tx-date");
    var payEl = document.getElementById("acc-tx-payment");
    var typeEl = document.getElementById("acc-tx-type");
    var curEl = document.getElementById("acc-tx-currency");
    var amountEl = document.getElementById("acc-tx-amount");
    var rateUsdEl = document.getElementById("acc-tx-rate-usd");
    var rateEurEl = document.getElementById("acc-tx-rate-eur");
    if (editId) editId.value = String(row.id);
    if (dateEl) dateEl.value = row.tx_date || "";
    if (typeEl) typeEl.value = row.tx_type || "deposit";
    accRefreshTxPaymentSelect();
    if (payEl && row.payment_method_id) payEl.value = String(row.payment_method_id);
    if (curEl) curEl.value = row.currency || "TRY";
    if (amountEl) amountEl.value = row.amount != null ? row.amount : "";
    if (rateUsdEl) rateUsdEl.value = row.rate_usd_try > 0 ? row.rate_usd_try : "";
    if (rateEurEl) rateEurEl.value = row.rate_eur_try > 0 ? row.rate_eur_try : "";
    accSetTxFormMode(true);
    accRenderTransactions();
    var section = document.getElementById("acc-tx-form-section");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
    if (amountEl) amountEl.dispatchEvent(new Event("input"));
  }

  function accLoadTransactions() {
    return accApi("/api/accounting/transactions" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.period_label) {
        accUpdatePeriodLabel(res.data.period_label);
        accUpdateTxPeriodLabel(res.data.period_label);
      }
      accData["acc-tx"].rows = res.data.transactions || [];
      accRenderTransactions();
    });
  }

  function accRenderTransactions() {
    var tbody = document.getElementById("acc-tx-table");
    var editIdEl = document.getElementById("acc-tx-edit-id");
    var editingId = editIdEl && editIdEl.value ? parseInt(editIdEl.value, 10) : null;
    var allRows = accData["acc-tx"].rows;
    accUpdateTransactionSummary(allRows);
    var rows = accSortRows("acc-tx", allRows, {
      tx_date: function (r) { return r.tx_date; },
      payment_name: function (r) { return r.payment_name; },
      tx_type: function (r) { return r.tx_type; },
      amount: function (r) { return r.amount; },
      commission_rate: function (r) { return r.commission_rate; },
      commission_amount: function (r) { return r.commission_amount; }
    });
    if (!allRows.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Bu dönemde kayıt yok</td></tr>';
      accUpdateFoot("acc-tx", 0, "işlem");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var editing = editingId === r.id;
      return '<tr class="' + (editing ? "acc-exp-row-editing" : "") + '" data-edit-tx-row="' + r.id + '">' +
        '<td class="mono">' + accEsc(r.tx_date) + '</td>' +
        '<td>' + accEsc(r.payment_name) + '</td>' +
        '<td><span class="tag ' + (r.tx_type === "deposit" ? "online" : "offline") + '">' + accTxTypeLabel(r.tx_type) + '</span></td>' +
        '<td>' + accMoneyCellHtml(r, "amount") + '</td>' +
        '<td>' + r.commission_rate + '%</td>' +
        '<td>' + accMoneyCellHtml(r, "commission_amount") + '</td>' +
        '<td class="acc-exp-actions">' +
          '<button type="button" class="btn btn-sm acc-exp-edit-btn" data-edit-tx="' + r.id + '" title="Düzenle">✎</button> ' +
          '<button class="btn btn-sm btn-danger" data-del-tx="' + r.id + '">Sil</button>' +
        '</td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-edit-tx]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var id = parseInt(btn.getAttribute("data-edit-tx"), 10);
        var row = allRows.find(function (r) { return r.id === id; });
        accStartTxEdit(row);
      };
    });
    tbody.querySelectorAll("[data-edit-tx-row]").forEach(function (tr) {
      tr.addEventListener("click", function (e) {
        if (e.target.closest("button")) return;
        var id = parseInt(tr.getAttribute("data-edit-tx-row"), 10);
        var row = allRows.find(function (r) { return r.id === id; });
        accStartTxEdit(row);
      });
    });
    tbody.querySelectorAll("[data-del-tx]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/transactions/" + btn.getAttribute("data-del-tx"), { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) {
              var editId = document.getElementById("acc-tx-edit-id");
              if (editId && editId.value === btn.getAttribute("data-del-tx")) accResetTxForm();
              accLoadTransactions(); accLoadDashboard(); accToast("Silindi");
            }
          });
      };
    });
    accUpdateFoot("acc-tx", allRows.length, "işlem");
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
      var countEl = document.getElementById("acc-cat-count");
      if (countEl) countEl.textContent = String(accCategories.length);
      accFillExpenseFilterCats();
      if (chips) {
        chips.innerHTML = accCategories.map(function (c) {
          return '<span class="acc-exp-cat-pill">' + accEsc(c.name) +
            '<button type="button" data-del-cat="' + c.id + '" title="Sil">×</button></span>';
        }).join("") || '<span class="muted acc-exp-cat-empty">Henüz kategori yok</span>';
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

  function accFmtExpenseDate(iso) {
    if (!iso) return "—";
    var p = String(iso).slice(0, 10).split("-");
    if (p.length === 3) return p[2] + "." + p[1] + "." + p[0];
    return iso;
  }

  function accExpenseCatClass(name) {
    var n = (name || "").toLowerCase();
    if (n.indexOf("marketing") >= 0 || n.indexOf("boss") >= 0 || n.indexOf("site masraf") >= 0) return "acc-exp-cat-marketing";
    if (n.indexOf("maa") >= 0 || n.indexOf("avans") >= 0) return "acc-exp-cat-salary";
    if (n.indexOf("ofis") >= 0 || n.indexOf("sabit") >= 0 || n.indexOf("call") >= 0) return "acc-exp-cat-office";
    if (n.indexOf("fatura") >= 0 || n.indexOf("kasa") >= 0) return "acc-exp-cat-invoice";
    if (n.indexOf("affilate") >= 0 || n.indexOf("betroz") >= 0) return "acc-exp-cat-affiliate";
    if (n.indexOf("değişken") >= 0 || n.indexOf("degisken") >= 0) return "acc-exp-cat-variable";
    return "acc-exp-cat-other";
  }

  function accFilteredExpenses() {
    var rows = accData["acc-exp"].rows || [];
    var cat = accData["acc-exp"].filterCat || "";
    var q = (accData["acc-exp"].filterQ || "").toLowerCase().trim();
    if (!cat && !q) return rows;
    return rows.filter(function (r) {
      if (cat && String(r.category_id) !== cat) return false;
      if (q) {
        var hay = ((r.description || "") + " " + (r.category_name || "")).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
  }

  function accSyncExpenseFilterUi() {
    var catSel = document.getElementById("acc-exp-filter-cat");
    var qEl = document.getElementById("acc-exp-filter-q");
    var clearBtn = document.getElementById("acc-exp-filter-clear");
    var meta = document.getElementById("acc-exp-filter-meta");
    var cat = accData["acc-exp"].filterCat || "";
    var q = accData["acc-exp"].filterQ || "";
    if (catSel && catSel.value !== cat) catSel.value = cat;
    if (qEl && qEl.value !== q) qEl.value = q;
    if (clearBtn) clearBtn.hidden = !cat && !q;
    if (meta) {
      var filtered = accFilteredExpenses();
      var total = accData["acc-exp"].rows.length;
      meta.textContent = (cat || q) && filtered.length !== total
        ? filtered.length + " / " + total + " kayıt"
        : "";
    }
  }

  function accSetExpenseFilter(cat, q) {
    accData["acc-exp"].filterCat = cat != null ? String(cat) : accData["acc-exp"].filterCat;
    accData["acc-exp"].filterQ = q != null ? String(q) : accData["acc-exp"].filterQ;
    accData["acc-exp"].expanded = false;
    accSyncExpenseFilterUi();
    accRenderExpenses();
  }

  function accClearExpenseFilter() {
    accData["acc-exp"].filterCat = "";
    accData["acc-exp"].filterQ = "";
    accSyncExpenseFilterUi();
    accRenderExpenses();
  }

  function accFillExpenseFilterCats() {
    var sel = document.getElementById("acc-exp-filter-cat");
    if (!sel) return;
    var cur = accData["acc-exp"].filterCat || "";
    sel.innerHTML = '<option value="">Tüm kategoriler</option>' +
      accCategories.map(function (c) {
        return '<option value="' + c.id + '">' + accEsc(c.name) + "</option>";
      }).join("");
    sel.value = cur;
  }

  function accExpenseDescHtml(text) {
    var raw = text || "";
    if (!raw.trim()) return '<span class="muted">—</span>';
    var short = raw.length > 72 ? raw.slice(0, 72) + "…" : raw;
    return '<span class="acc-exp-desc" title="' + accEsc(raw) + '">' + accEsc(short) + "</span>";
  }

  function accExpenseMoneyHtml(row) {
    var cur = row.currency || "USD";
    var main = accMoney(row.amount || 0, cur);
    var tryV = row.amount_try;
    var usdV = row.amount_usd;
    var eurV = row.amount_eur;
    if (tryV == null && usdV == null) return '<div class="acc-exp-money-main">' + main + "</div>";
    return '<div class="acc-exp-money-main">' + main + '</div>' +
      '<div class="acc-exp-money-sub">' +
      accMoney(tryV, "TRY") + " · " + accMoney(usdV, "USD") + " · " + accMoney(eurV, "EUR") +
      "</div>";
  }

  function accExpenseCategoryTotals(rows) {
    var map = {};
    (rows || []).forEach(function (r) {
      var key = r.category_name || "Diğer";
      if (!map[key]) {
        map[key] = { name: key, try: 0, usd: 0, count: 0 };
      }
      map[key].try += parseFloat(r.amount_try) || 0;
      map[key].usd += parseFloat(r.amount_usd) || 0;
      map[key].count += 1;
    });
    return Object.keys(map).map(function (k) { return map[k]; })
      .sort(function (a, b) { return b.try - a.try; });
  }

  function accRenderExpenseCategoryCards(rows) {
    var el = document.getElementById("acc-exp-cat-cards");
    if (!el) return;
    var totals = accExpenseCategoryTotals(rows);
    if (!totals.length) {
      el.innerHTML = '<div class="acc-exp-cat-card acc-exp-cat-card-empty muted">Bu dönemde gider yok</div>';
      return;
    }
    el.innerHTML = totals.map(function (t) {
      var cls = accExpenseCatClass(t.name);
      var catObj = accCategories.find(function (c) { return c.name === t.name; });
      var catId = catObj ? catObj.id : "";
      var active = String(accData["acc-exp"].filterCat || "") === String(catId);
      return '<button type="button" class="acc-exp-cat-card acc-exp-cat-card-btn ' + cls +
        (active ? " acc-exp-cat-card-active" : "") + '" data-exp-cat-filter="' + catId + '">' +
        '<div class="acc-exp-cat-card-head">' +
          '<span class="acc-exp-cat-card-name">' + accEsc(t.name) + "</span>" +
          '<span class="acc-exp-cat-card-count">' + t.count + " kayıt</span>" +
        "</div>" +
        '<strong class="acc-exp-cat-card-try">' + accMoney(t.try, "TRY") + "</strong>" +
        '<span class="acc-exp-cat-card-usd">' + accMoney(t.usd, "USD") + "</span>" +
      "</button>";
    }).join("");
    el.querySelectorAll("[data-exp-cat-filter]").forEach(function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute("data-exp-cat-filter");
        if (!id) return;
        var current = accData["acc-exp"].filterCat || "";
        accSetExpenseFilter(current === id ? "" : id, accData["acc-exp"].filterQ);
      };
    });
  }

  function accUpdateExpenseSummary(rows, filteredRows) {
    var tryEl = document.getElementById("acc-exp-sum-try");
    var usdEl = document.getElementById("acc-exp-sum-usd");
    var countEl = document.getElementById("acc-exp-sum-count");
    var periodEl = document.getElementById("acc-exp-period-label");
    if (!tryEl) return;
    var source = filteredRows || rows;
    var totalTry = 0;
    var totalUsd = 0;
    (source || []).forEach(function (r) {
      totalTry += parseFloat(r.amount_try) || 0;
      totalUsd += parseFloat(r.amount_usd) || 0;
    });
    tryEl.textContent = accMoney(totalTry, "TRY");
    usdEl.textContent = accMoney(totalUsd, "USD");
    countEl.textContent = String((source || []).length);
    if (periodEl) {
      var lbl = document.getElementById("acc-period-label");
      periodEl.textContent = lbl ? lbl.textContent : "";
    }
    accRenderExpenseCategoryCards(rows);
  }

  function accSetExpenseFormMode(editing) {
    var title = document.getElementById("acc-exp-form-title");
    var submit = document.getElementById("acc-exp-submit");
    var cancel = document.getElementById("acc-exp-edit-cancel");
    var section = document.getElementById("acc-exp-form-section");
    if (title) title.textContent = editing ? "Gideri Düzenle" : "Yeni Gider";
    if (submit) submit.textContent = editing ? "Güncelle" : "Kaydet";
    if (cancel) cancel.hidden = !editing;
    if (section) section.classList.toggle("acc-exp-form-editing", !!editing);
  }

  function accResetExpenseForm() {
    var editId = document.getElementById("acc-exp-edit-id");
    if (editId) editId.value = "";
    var amount = document.getElementById("acc-exp-amount");
    var desc = document.getElementById("acc-exp-desc");
    if (amount) amount.value = "";
    if (desc) desc.value = "";
    accClearFormRates("acc-exp-rate-usd", "acc-exp-rate-eur");
    var preview = document.getElementById("acc-exp-fx-preview");
    if (preview) preview.textContent = "";
    accSetExpenseFormMode(false);
    accRenderExpenses();
  }

  function accStartExpenseEdit(row) {
    if (!row) return;
    var editId = document.getElementById("acc-exp-edit-id");
    var dateEl = document.getElementById("acc-exp-date");
    var catEl = document.getElementById("acc-exp-category");
    var curEl = document.getElementById("acc-exp-currency");
    var amountEl = document.getElementById("acc-exp-amount");
    var rateUsdEl = document.getElementById("acc-exp-rate-usd");
    var rateEurEl = document.getElementById("acc-exp-rate-eur");
    var descEl = document.getElementById("acc-exp-desc");
    if (editId) editId.value = String(row.id);
    if (dateEl) dateEl.value = row.expense_date || "";
    if (catEl && row.category_id) catEl.value = String(row.category_id);
    if (curEl) curEl.value = row.currency || "USD";
    if (amountEl) amountEl.value = row.amount != null ? row.amount : "";
    if (rateUsdEl) rateUsdEl.value = row.rate_usd_try > 0 ? row.rate_usd_try : "";
    if (rateEurEl) rateEurEl.value = row.rate_eur_try > 0 ? row.rate_eur_try : "";
    if (descEl) descEl.value = row.description || "";
    accSetExpenseFormMode(true);
    accRenderExpenses();
    var section = document.getElementById("acc-exp-form-section");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
    var amountInput = document.getElementById("acc-exp-amount");
    if (amountInput) amountInput.dispatchEvent(new Event("input"));
  }

  function accRenderExpenses() {
    var tbody = document.getElementById("acc-exp-table");
    var editIdEl = document.getElementById("acc-exp-edit-id");
    var editingId = editIdEl && editIdEl.value ? parseInt(editIdEl.value, 10) : null;
    var allRows = accData["acc-exp"].rows;
    var filtered = accFilteredExpenses();
    accSyncExpenseFilterUi();
    accUpdateExpenseSummary(allRows, filtered);
    var rows = accSortRows("acc-exp", filtered, {
      expense_date: function (r) { return r.expense_date; },
      category_name: function (r) { return r.category_name; },
      description: function (r) { return r.description; },
      amount: function (r) { return r.amount; },
      rate_usd_try: function (r) { return r.rate_usd_try; }
    });
    if (!allRows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty acc-exp-empty">Bu dönemde gider kaydı yok</td></tr>';
      accUpdateFoot("acc-exp", 0, "gider");
      return;
    }
    if (!filtered.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty acc-exp-empty">Filtreye uygun kayıt yok</td></tr>';
      accUpdateFoot("acc-exp", 0, "gider");
      accUpdateSortHeaders("acc-exp");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var kur = r.rate_usd_try > 0
        ? parseFloat(r.rate_usd_try).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 })
        : "—";
      var editing = editingId === r.id;
      return '<tr class="acc-exp-row' + (editing ? " acc-exp-row-editing" : "") + '" data-exp-row="' + r.id + '">' +
        '<td class="mono acc-exp-td-date">' + accFmtExpenseDate(r.expense_date) + "</td>" +
        '<td><span class="acc-exp-cat ' + accExpenseCatClass(r.category_name) + '">' + accEsc(r.category_name) + "</span></td>" +
        '<td class="acc-exp-td-desc">' + accExpenseDescHtml(r.description) + "</td>" +
        '<td class="acc-exp-td-money">' + accExpenseMoneyHtml(r) + "</td>" +
        '<td class="mono acc-exp-td-kur">' + kur + "</td>" +
        '<td class="acc-exp-row-actions">' +
          '<button type="button" class="btn btn-sm acc-exp-edit-btn" data-edit-exp="' + r.id + '" title="Düzenle">✎</button> ' +
          '<button type="button" class="btn btn-sm btn-danger" data-del-exp="' + r.id + '" title="Sil">×</button>' +
        "</td></tr>";
    }).join("");
    tbody.querySelectorAll("[data-edit-exp]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        var id = parseInt(btn.getAttribute("data-edit-exp"), 10);
        var row = (accData["acc-exp"].rows || []).find(function (r) { return r.id === id; });
        if (row) accStartExpenseEdit(row);
      };
    });
    tbody.querySelectorAll("[data-exp-row]").forEach(function (tr) {
      tr.onclick = function (e) {
        if (e.target.closest("button")) return;
        var id = parseInt(tr.getAttribute("data-exp-row"), 10);
        var row = (accData["acc-exp"].rows || []).find(function (r) { return r.id === id; });
        if (row) accStartExpenseEdit(row);
      };
    });
    tbody.querySelectorAll("[data-del-exp]").forEach(function (btn) {
      btn.onclick = function (e) {
        e.stopPropagation();
        if (!confirm("Silinsin mi?")) return;
        var delId = btn.getAttribute("data-del-exp");
        accApi("/api/accounting/expenses/" + delId, { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) {
              var editId = document.getElementById("acc-exp-edit-id");
              if (editId && editId.value === delId) accResetExpenseForm();
              accLoadExpenses();
              accLoadDashboard();
              accToast("Silindi");
            }
          });
      };
    });
    accUpdateFoot("acc-exp", filtered.length, "gider");
    accUpdateSortHeaders("acc-exp");
  }

  function accFmtVaultDate(iso) {
    if (!iso) return "—";
    var p = String(iso).slice(0, 10).split("-");
    if (p.length === 3) return p[2] + "." + p[1] + "." + p[0];
    return iso;
  }

  function accLinkify(text) {
    if (!text) return "—";
    var safe = accEsc(text);
    return safe.replace(/(https?:\/\/[^\s<]+)/g, function (url) {
      return '<a href="' + url + '" target="_blank" rel="noopener">' + url + "</a>";
    });
  }

  function accVaultQuery() {
    var q = accPeriodQuery();
    if (accVaultFilterId) {
      q += (q.indexOf("?") >= 0 ? "&" : "?") + "vault_id=" + encodeURIComponent(accVaultFilterId);
    }
    return q;
  }

  function accRenderVaultDashboard(vaults, totals) {
    var cardsEl = document.getElementById("acc-vault-cards");
    var totalUsdt = document.getElementById("acc-vault-total-usdt");
    var totalTry = document.getElementById("acc-vault-total-try");
    if (!cardsEl) return;

    if (!vaults || !vaults.length) {
      cardsEl.innerHTML = '<div class="acc-vault-card muted">Henüz kasa yok — aşağıdan ekleyin.</div>';
    } else {
      cardsEl.innerHTML = vaults.map(function (v) {
        var balClass = (v.balance_usdt || 0) < 0 ? " acc-vault-card-bal negative" : " acc-vault-card-bal";
        var period = v.period || {};
        return '<div class="acc-vault-card" data-vault-card="' + v.id + '" style="--vault-accent:' + accEsc(v.color || "#6366f1") + '">' +
          '<div class="acc-vault-card-head">' +
          '<span class="acc-vault-card-icon">' + accEsc(v.icon || "💰") + '</span>' +
          '<span class="acc-vault-card-name">' + accEsc(v.name) + '</span>' +
          '<div class="acc-vault-card-actions">' +
          '<button type="button" title="Bakiyeyi kopyala" data-copy-vault-bal="' + v.id + '">📋</button>' +
          '<button type="button" title="Defterde filtrele" data-filter-vault="' + v.id + '">🔍</button>' +
          "</div></div>" +
          '<div class="' + balClass.trim() + '">' + accUsdt(v.balance_usdt || 0) + "</div>" +
          '<div class="acc-vault-card-sub">' + accMoney(v.balance_try || 0, "TRY") + " · " + (v.total_tx_count || 0) + " hareket</div>" +
          '<div class="acc-vault-card-stats">' +
          '<span class="acc-vault-stat-in">↑ ' + accUsdt(period.usdt_in || 0) + "</span>" +
          '<span class="acc-vault-stat-out">↓ ' + accUsdt(period.usdt_out || 0) + "</span>" +
          (period.fee_usdt > 0 ? '<span class="muted">Fee ' + accUsdt(period.fee_usdt) + "</span>" : "") +
          '<span class="muted">Net ' + accUsdt(period.net_usdt || 0) + "</span>" +
          "</div></div>";
      }).join("");

      cardsEl.querySelectorAll("[data-vault-card]").forEach(function (card) {
        card.addEventListener("click", function (e) {
          if (e.target.closest("button")) return;
          var id = card.getAttribute("data-vault-card");
          accSetVaultFilter(id);
        });
      });
      cardsEl.querySelectorAll("[data-filter-vault]").forEach(function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          accSetVaultFilter(btn.getAttribute("data-filter-vault"));
        };
      });
      cardsEl.querySelectorAll("[data-copy-vault-bal]").forEach(function (btn) {
        btn.onclick = function (e) {
          e.stopPropagation();
          var vid = parseInt(btn.getAttribute("data-copy-vault-bal"), 10);
          var vault = vaults.find(function (v) { return v.id === vid; });
          if (!vault) return;
          var text = vault.name + ": " + accUsdt(vault.balance_usdt) + " / " + accMoney(vault.balance_try, "TRY");
          navigator.clipboard.writeText(text).then(function () { accToast("Bakiye kopyalandı"); });
        };
      });
    }

    if (totalUsdt) totalUsdt.textContent = totals ? accUsdt(totals.balance_usdt || 0) : "—";
    if (totalTry) totalTry.textContent = totals ? accMoney(totals.balance_try || 0, "TRY") : "";
  }

  function accFillVaultSelects(vaults) {
    var sel = document.getElementById("acc-vault-select");
    var filter = document.getElementById("acc-vault-filter");
    var opts = (vaults || []).map(function (v) {
      return '<option value="' + v.id + '">' + accEsc(v.icon || "💰") + " " + accEsc(v.name) + "</option>";
    }).join("");
    if (sel) {
      var prev = sel.value;
      sel.innerHTML = opts || '<option value="">Kasa yok</option>';
      if (prev && vaults.some(function (v) { return String(v.id) === prev; })) sel.value = prev;
      else if (vaults.length) sel.value = String(vaults[0].id);
    }
    if (filter) {
      var prevF = accVaultFilterId || filter.value;
      filter.innerHTML = '<option value="">Tüm kasalar</option>' + opts;
      filter.value = prevF || "";
      accVaultFilterId = filter.value;
    }
  }

  function accRenderVaultChips(vaults) {
    var box = document.getElementById("acc-vault-chip-list");
    if (!box) return;
    if (!vaults || !vaults.length) {
      box.innerHTML = '<span class="muted" style="font-size:0.75rem;">Kasa ekleyerek başlayın.</span>';
      return;
    }
    box.innerHTML = vaults.map(function (v) {
      return '<span class="acc-vault-chip">' +
        '<span class="acc-vault-chip-dot" style="background:' + accEsc(v.color || "#6366f1") + '"></span>' +
        accEsc(v.name) +
        ' <button type="button" title="Kaldır" data-del-vault-id="' + v.id + '">&times;</button></span>';
    }).join("");
    box.querySelectorAll("[data-del-vault-id]").forEach(function (btn) {
      btn.onclick = function () {
        var id = btn.getAttribute("data-del-vault-id");
        if (!confirm("Kasa silinsin / pasifleştirilsin mi?")) return;
        accApi("/api/accounting/vaults/" + id, { method: "DELETE" }).then(function (r) {
          if (r && r.ok) {
            if (String(accVaultFilterId) === String(id)) accSetVaultFilter("");
            accLoadVault();
            accToast(r.data.deactivated ? "Kasa pasifleştirildi" : "Kasa silindi");
          } else if (r) alert(r.data.error || "Hata");
        });
      };
    });
  }

  function accRenderVaultMethods(methods) {
    var list = document.getElementById("acc-vault-method-list");
    if (!list) return;
    list.innerHTML = (methods || []).map(function (m) {
      return "<option value=\"" + accEsc(m) + "\"></option>";
    }).join("");
  }

  function accRenderVaultOperationTypes(types) {
    var list = document.getElementById("acc-vault-optype-list");
    if (!list) return;
    list.innerHTML = (types || []).map(function (m) {
      return "<option value=\"" + accEsc(m) + "\"></option>";
    }).join("");
  }

  function accRenderOptypeChips() {
    var chips = document.getElementById("acc-optype-chips");
    var countEl = document.getElementById("acc-optype-count");
    if (!chips) return;
    var rows = accVaultOperationTypeOptions.slice().sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "tr");
    });
    if (countEl) countEl.textContent = rows.length + " kayıt";
    chips.innerHTML = rows.length
      ? rows.map(function (o) {
          return '<span class="acc-chip" title="' + accEsc(o.name) + '"><span class="acc-chip-text">' + accEsc(o.name) +
            '</span> <button type="button" data-del-optype="' + o.id + '" title="Sil">×</button></span>';
        }).join("")
      : '<span class="acc-chip-empty">Henüz işlem başlığı yok</span>';
    chips.querySelectorAll("[data-del-optype]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("İşlem başlığı silinsin mi?")) return;
        accApi("/api/accounting/vault-operation-types/" + btn.getAttribute("data-del-optype"), { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) { accLoadVault(); accToast("Silindi"); }
            else if (r) alert(r.data.error || "Hata");
          });
      };
    });
  }

  function accRenderMethodChips() {
    var chips = document.getElementById("acc-method-chips");
    var countEl = document.getElementById("acc-method-count");
    if (!chips) return;
    var rows = accVaultMethodOptions.slice().sort(function (a, b) {
      return String(a.name).localeCompare(String(b.name), "tr");
    });
    if (countEl) countEl.textContent = rows.length + " kayıt";
    chips.innerHTML = rows.length
      ? rows.map(function (m) {
          return '<span class="acc-chip" title="' + accEsc(m.name) + '"><span class="acc-chip-text">' + accEsc(m.name) +
            '</span> <button type="button" data-del-method="' + m.id + '" title="Sil">×</button></span>';
        }).join("")
      : '<span class="acc-chip-empty">Henüz yöntem yok</span>';
    chips.querySelectorAll("[data-del-method]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Yöntem silinsin mi?")) return;
        accApi("/api/accounting/vault-methods/" + btn.getAttribute("data-del-method"), { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) { accLoadVault(); accToast("Silindi"); }
            else if (r) alert(r.data.error || "Hata");
          });
      };
    });
  }

  function accSetVaultFilter(vaultId) {
    accVaultFilterId = vaultId ? String(vaultId) : "";
    localStorage.setItem("acc_vault_filter", accVaultFilterId);
    var filter = document.getElementById("acc-vault-filter");
    if (filter) filter.value = accVaultFilterId;
    accLoadVault();
    if (vaultId) accToast("Kasa filtresi uygulandı");
  }

  function accUpdateVaultTlPreview() {
    var usdtEl = document.getElementById("acc-vault-usdt");
    var dirEl = document.getElementById("acc-vault-direction");
    var rateEl = document.getElementById("acc-vault-rate-usd");
    var feeEl = document.getElementById("acc-vault-fee");
    var outEl = document.getElementById("acc-vault-tl-preview");
    var netEl = document.getElementById("acc-vault-net-preview");
    if (!usdtEl || !outEl) return;
    var amount = parseFloat(usdtEl.value) || 0;
    var fee = parseFloat(feeEl && feeEl.value) || 0;
    var rate = parseFloat(rateEl && rateEl.value) || accRates.usd_try || 0;
    var dir = dirEl ? dirEl.value : "in";
    if (!amount || !rate) {
      outEl.value = "";
      if (netEl) netEl.value = "";
      return;
    }
    var delta = dir === "out" ? -(amount + fee) : (amount - fee);
    var tl = delta * rate;
    outEl.value = accMoney(Math.abs(tl), "TRY") + (tl < 0 ? " (net giden)" : " (net gelen)");
    if (netEl) {
      if (dir === "out") {
        netEl.value = accUsdt(amount + fee) + " kasadan düşer · transfer " + accUsdt(amount) + " + fee " + accUsdt(fee);
      } else {
        netEl.value = accUsdt(Math.max(0, amount - fee)) + " kasaya net girer";
      }
    }
  }

  function accSuggestVaultFee() {
    var amount = document.getElementById("acc-vault-usdt").value;
    var dir = document.getElementById("acc-vault-direction").value;
    return accApi(
      "/api/accounting/vault-transactions/suggest-fee?amount=" +
      encodeURIComponent(amount || 0) + "&direction=" + encodeURIComponent(dir || "out")
    ).then(function (res) {
      if (!res || !res.ok) return;
      var feeEl = document.getElementById("acc-vault-fee");
      if (feeEl) feeEl.value = res.data.fee_usdt != null ? res.data.fee_usdt : 0;
      var hint = document.getElementById("acc-vault-fee-hint");
      if (hint && res.data.note) hint.textContent = res.data.note;
      accUpdateVaultTlPreview();
    });
  }

  function accUpdateVaultFormRateBadge() {
    var badge = document.getElementById("acc-vault-form-rate-badge");
    if (!badge) return;
    if (accRates.usd_try) badge.textContent = "Canlı kur: " + accRates.usd_try.toFixed(4) + " ₺";
    else badge.textContent = "";
  }

  function accSetVaultFormMode(editing) {
    var title = document.getElementById("acc-vault-form-title");
    var submit = document.getElementById("acc-vault-submit");
    var cancel = document.getElementById("acc-vault-edit-cancel");
    var section = document.getElementById("acc-vault-form-section");
    if (title) title.textContent = editing ? "Kasa Hareketini Düzenle" : "Yeni Kasa Hareketi";
    if (submit) submit.textContent = editing ? "Güncelle" : "Kaydet";
    if (cancel) cancel.hidden = !editing;
    if (section) section.classList.toggle("acc-vault-form-editing", !!editing);
  }

  function accResetVaultForm() {
    var editId = document.getElementById("acc-vault-edit-id");
    if (editId) editId.value = "";
    var usdt = document.getElementById("acc-vault-usdt");
    var fee = document.getElementById("acc-vault-fee");
    var desc = document.getElementById("acc-vault-desc");
    var method = document.getElementById("acc-vault-method");
    var optype = document.getElementById("acc-vault-optype");
    if (usdt) usdt.value = "";
    if (fee) fee.value = "0";
    if (desc) desc.value = "";
    if (method) method.value = "";
    if (optype) optype.value = "";
    accClearFormRates("acc-vault-rate-usd", null);
    accUpdateVaultTlPreview();
    accSetVaultFormMode(false);
  }

  function accStartVaultEdit(row) {
    if (!row) return;
    var editId = document.getElementById("acc-vault-edit-id");
    var vaultSel = document.getElementById("acc-vault-select");
    var dateEl = document.getElementById("acc-vault-date");
    var dirEl = document.getElementById("acc-vault-direction");
    var usdtEl = document.getElementById("acc-vault-usdt");
    var feeEl = document.getElementById("acc-vault-fee");
    var rateEl = document.getElementById("acc-vault-rate-usd");
    var optypeEl = document.getElementById("acc-vault-optype");
    var methodEl = document.getElementById("acc-vault-method");
    var descEl = document.getElementById("acc-vault-desc");
    if (editId) editId.value = String(row.id);
    if (vaultSel && row.vault_id) vaultSel.value = String(row.vault_id);
    if (dateEl) dateEl.value = row.tx_date || "";
    if (dirEl) dirEl.value = row.tx_type || (row.usdt_in > 0 ? "in" : "out");
    if (usdtEl) usdtEl.value = row.usdt_in > 0 ? row.usdt_in : row.usdt_out;
    if (feeEl) feeEl.value = row.fee_usdt != null ? row.fee_usdt : 0;
    if (rateEl) rateEl.value = row.rate_display > 0 ? row.rate_display : "";
    if (optypeEl) optypeEl.value = row.operation_type || "";
    if (methodEl) {
      var mn = row.method_name || "";
      methodEl.value = (mn === "Giriş" || mn === "Çıkış") ? "" : mn;
    }
    if (descEl) descEl.value = row.description || "";
    accSetVaultFormMode(true);
    accUpdateVaultTlPreview();
    var section = document.getElementById("acc-vault-form-section");
    if (section) section.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function accCancelVaultEdit() {
    accResetVaultForm();
  }

  function accLoadVault() {
    return accApi("/api/accounting/vault-transactions" + accVaultQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.period_label) accUpdatePeriodLabel(res.data.period_label);
      accVaults = res.data.vaults || [];
      accVaultMethods = res.data.methods || [];
      accVaultMethodOptions = res.data.method_options || [];
      accVaultOperationTypes = res.data.operation_types || [];
      accVaultOperationTypeOptions = res.data.operation_type_options || [];
      accData["acc-vault"].rows = res.data.vault_transactions || [];
      accFillVaultSelects(accVaults);
      accRenderVaultChips(accVaults);
      accRenderVaultMethods(accVaultMethods);
      accRenderVaultOperationTypes(accVaultOperationTypes);
      accRenderMethodChips();
      accRenderOptypeChips();
      accRenderVaultDashboard(accVaults, res.data.totals);
      accRenderVault();
      accUpdateVaultFormRateBadge();
    });
  }

  function accRenderVault() {
    var tbody = document.getElementById("acc-vault-table");
    if (!tbody) return;
    var rows = accSortRows("acc-vault", accData["acc-vault"].rows, {
      tx_date: function (r) { return r.tx_date; },
      operation_type: function (r) { return r.operation_type; },
      method_name: function (r) { return r.method_name; },
      usdt_out: function (r) { return r.usdt_out; },
      usdt_in: function (r) { return r.usdt_in; },
      fee_usdt: function (r) { return r.fee_usdt; },
      tl_signed: function (r) { return r.tl_signed; },
      rate_display: function (r) { return r.rate_display; },
      balance_usdt: function (r) { return r.balance_usdt; },
      balance_try: function (r) { return r.balance_try; },
      description: function (r) { return r.description; },
      vault_name: function (r) { return r.vault_name; }
    });
    if (!accData["acc-vault"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="13" class="empty">Kayıt yok</td></tr>';
      accUpdateFoot("acc-vault", 0, "kayıt");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var outCell = r.usdt_out > 0 ? '<span class="acc-vault-out">' + accMoney(-r.usdt_out, "USD") + "</span>" : "—";
      var inCell = r.usdt_in > 0 ? '<span class="acc-vault-in">' + accMoney(r.usdt_in, "USD") + "</span>" : "—";
      var feeCell = r.fee_usdt > 0 ? '<span class="acc-vault-fee">' + accUsdt(r.fee_usdt) + "</span>" : "—";
      var tl = parseFloat(r.tl_signed) || 0;
      var tlCell = tl === 0 ? "—" : '<span class="' + (tl < 0 ? "acc-vault-out" : "acc-vault-in") + '">' + accMoney(tl, "TRY") + "</span>";
      var kur = r.rate_display > 0 ? parseFloat(r.rate_display).toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : "—";
      return "<tr>" +
        '<td class="mono">' + accFmtVaultDate(r.tx_date) + "</td>" +
        "<td>" + accEsc(r.operation_type || "—") + "</td>" +
        "<td><strong>" + accEsc(r.method_name || "—") + "</strong></td>" +
        "<td>" + outCell + "</td>" +
        "<td>" + inCell + "</td>" +
        "<td>" + feeCell + "</td>" +
        "<td>" + tlCell + "</td>" +
        '<td class="mono">' + kur + "</td>" +
        '<td class="acc-vault-bal">' + (r.balance_usdt != null ? accUsdt(r.balance_usdt) : "—") + "</td>" +
        '<td class="acc-vault-bal">' + (r.balance_try != null ? accMoney(r.balance_try, "TRY") : "—") + "</td>" +
        '<td class="acc-vault-desc">' + accLinkify(r.description) + "</td>" +
        "<td>" + accEsc(r.vault_name || "—") + "</td>" +
        '<td class="acc-vault-row-actions">' +
          '<button type="button" class="btn btn-sm" data-edit-vault="' + r.id + '" title="Düzenle">Düzenle</button> ' +
          '<button type="button" class="btn btn-sm btn-danger" data-del-vault="' + r.id + '">Sil</button>' +
        "</td></tr>";
    }).join("");
    tbody.querySelectorAll("[data-edit-vault]").forEach(function (btn) {
      btn.onclick = function () {
        var id = parseInt(btn.getAttribute("data-edit-vault"), 10);
        var row = (accData["acc-vault"].rows || []).find(function (r) { return r.id === id; });
        if (row) accStartVaultEdit(row);
      };
    });
    tbody.querySelectorAll("[data-del-vault]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        var delId = btn.getAttribute("data-del-vault");
        accApi("/api/accounting/vault-transactions/" + delId, { method: "DELETE" })
          .then(function (r) {
            if (r && r.ok) {
              var editId = document.getElementById("acc-vault-edit-id");
              if (editId && editId.value === delId) accResetVaultForm();
              accLoadVault();
              accToast("Silindi");
            }
          });
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
      var dc = String(a.department || "").localeCompare(String(b.department || ""), "tr", { sensitivity: "base" });
      if (dc !== 0) return dc;
      return String(a.name || "").localeCompare(String(b.name || ""), "tr", { sensitivity: "base" });
    });
  }

  function accIsOfficeEmployee(r) {
    return accIsOfficeCategory(r && r.salary_category);
  }

  function accEmpPanelSide(r) {
    if (!r) return "right";
    if (r.salary_category === "turkey") return "right";
    var loc = String(r.location || "").toLowerCase().replace(/ı/g, "i").replace(/ü/g, "u");
    if (r.salary_category === "crypto" && loc.indexOf("turk") >= 0) return "right";
    return "left";
  }

  function accEmpSectionHtml(cols, type, icon, label, count, sub) {
    return '<tr class="acc-emp-section acc-emp-section-' + type + '">' +
      '<td colspan="' + cols + '">' +
      '<div class="acc-emp-section-inner">' +
      (icon ? '<span class="acc-emp-section-icon" aria-hidden="true">' + icon + "</span>" : "") +
      '<span class="acc-emp-section-label">' + accEsc(label) + "</span>" +
      '<span class="acc-emp-section-count">' + count + "</span>" +
      (sub ? '<span class="acc-emp-section-sub">' + accEsc(sub) + "</span>" : "") +
      "</div></td></tr>";
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

  function accEmpRowHtml(r, panel) {
    var cur = r.currency || "TRY";
    var rowCls = "acc-emp-row " + (panel === "left" ? "acc-emp-row-office" : "acc-emp-row-tr");
    if (r.status === "left") rowCls += " acc-emp-row-left";
    var deptOpts = accEmployeeDepartments.map(function (d) {
      return { value: d.name, label: d.name };
    });
    var statusCls = r.status === "active" ? "active-status" : "left-status";
    var nameHidden = accSalaryHidden(r);
    var moneyHidden = accSalaryRedacted(r);
    var nameCell = nameHidden
      ? accHiddenMoney()
      : accEmpInputHtml("name", r.name, r.id, "acc-emp-inline-name");
    var deptCell = accEmpSelectHtml("department", r.department, r.id, deptOpts, "acc-emp-inline-dept");
    var refCell = accEmpRefCellHtml(r, moneyHidden);
    var locCell = moneyHidden
      ? accHiddenMoney()
      : accEmpInputHtml("location", r.location || "", r.id, "acc-emp-inline-loc", "text", null, "Konum");
    var startCell = accEmpInputHtml("start_date", r.start_date, r.id, "", "date");
    var endCell = r.status === "left"
      ? accEmpInputHtml("end_date", r.end_date || "", r.id, "", "date")
      : '<span class="muted">—</span>';
    var salaryCell = moneyHidden
      ? accHiddenMoney()
      : ('<div class="acc-emp-salary-cell">' +
        accEmpInputHtml("salary", r.salary, r.id, "acc-emp-inline-salary", "number", "0.01") +
        '<span class="acc-emp-salary-cur">' + accEsc(cur) + "</span></div>");
    var cryptoCell = moneyHidden
      ? accHiddenMoney()
      : accEmpInputHtml("crypto_salary", r.crypto_salary || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var advanceCell = moneyHidden
      ? accHiddenMoney()
      : accEmpInputHtml("advance_amount", r.advance_amount || 0, r.id, "acc-emp-inline-salary", "number", "0.01");
    var remainCell = moneyHidden
      ? accHiddenMoney()
      : ('<span class="acc-emp-remain-cell">' + accMoney(r.payment_remaining != null ? r.payment_remaining : r.office_remaining, cur) + "</span>");
    var walletCell = accEmpWalletCellHtml(r, moneyHidden);
    var accrualCell = accPayrollCompactCellHtml(r.accrual, r, moneyHidden);
    var netCell = accPayrollCompactCellHtml(r.net_accrual, r, moneyHidden);
    var statusCell = accEmpSelectHtml("status", r.status || "active", r.id, [
      { value: "active", label: "Aktif" },
      { value: "left", label: "Ayrıldı" }
    ], "acc-emp-status-select " + statusCls);
    var delCell = '<button class="btn btn-sm btn-danger acc-emp-del" data-del-emp="' + r.id + '" title="Sil">×</button>';

    if (panel === "left") {
      return '<tr class="' + rowCls + '">' +
        '<td class="acc-emp-col-sticky acc-emp-td-name">' + nameCell + "</td>" +
        '<td class="acc-emp-td-ref">' + refCell + "</td>" +
        '<td class="acc-emp-td-dept">' + deptCell + "</td>" +
        '<td class="acc-emp-td-loc">' + locCell + "</td>" +
        '<td class="acc-emp-td-date mono">' + startCell + "</td>" +
        '<td class="acc-emp-td-date mono">' + endCell + "</td>" +
        '<td class="acc-emp-td-money">' + salaryCell + "</td>" +
        '<td class="acc-emp-td-money">' + cryptoCell + "</td>" +
        '<td class="acc-emp-td-money">' + advanceCell + "</td>" +
        '<td class="acc-emp-td-money">' + remainCell + "</td>" +
        '<td class="acc-emp-td-wallet">' + walletCell + "</td>" +
        '<td class="acc-emp-td-status">' + statusCell + "</td>" +
        '<td class="acc-emp-td-action">' + delCell + "</td></tr>";
    }

    return '<tr class="' + rowCls + '">' +
      '<td class="acc-emp-col-sticky acc-emp-td-name">' + nameCell + "</td>" +
      '<td class="acc-emp-td-ref">' + refCell + "</td>" +
      '<td class="acc-emp-td-dept">' + deptCell + "</td>" +
      '<td class="acc-emp-td-loc">' + locCell + "</td>" +
      '<td class="acc-emp-td-date mono">' + startCell + "</td>" +
      '<td class="acc-emp-td-date mono">' + endCell + "</td>" +
      '<td class="acc-emp-td-money">' + salaryCell + "</td>" +
        '<td class="acc-emp-td-money acc-emp-td-money-lg">' + accrualCell + "</td>" +
        '<td class="acc-emp-td-money">' + cryptoCell + "</td>" +
        '<td class="acc-emp-td-money acc-emp-td-money-lg">' + netCell + "</td>" +
      '<td class="acc-emp-td-status">' + statusCell + "</td>" +
      '<td class="acc-emp-td-action">' + delCell + "</td></tr>";
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

  function accRenderEmployeesPanel(tbody, rows, panel, cols) {
    var ordered = accOrderEmployees(rows);
    var activeRows = ordered.filter(function (r) { return r.status === "active"; });
    var leftRows = ordered.filter(function (r) { return r.status === "left"; });
    var sectionType = panel === "left" ? "office" : "tr";
    var emptyMsg = panel === "left" ? "Sol panelde personel yok" : "Sağ panelde personel yok";

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="' + cols + '" class="empty acc-emp-empty">' + emptyMsg + "</td></tr>";
      return;
    }

    var html = "";
    if (activeRows.length) {
      html += accEmpSectionHtml(cols, sectionType + "-active", "", "Aktif", activeRows.length, "kişi");
      html += activeRows.map(function (r) { return accEmpRowHtml(r, panel); }).join("");
    }
    if (leftRows.length) {
      html += accEmpSectionHtml(cols, sectionType + "-left", "", "Ayrılan", leftRows.length, "kişi");
      html += leftRows.map(function (r) { return accEmpRowHtml(r, panel); }).join("");
    }
    tbody.innerHTML = html;
  }

  function accBindEmployeeTable(tbody) {
    if (!tbody) return;
    accBindEmployeeInlineEditors(tbody);
    tbody.querySelectorAll("[data-del-emp]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/employees/" + btn.getAttribute("data-del-emp"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadEmployees(); accLoadDashboard(); accToast("Silindi"); } });
      };
    });
  }

  function accRenderEmployees() {
    var tbodyLeft = document.getElementById("acc-emp-table-left");
    var tbodyRight = document.getElementById("acc-emp-table-right");
    var filtered = accFilteredEmployees();
    var leftRows = filtered.filter(function (r) { return accEmpPanelSide(r) === "left"; });
    var rightRows = filtered.filter(function (r) { return accEmpPanelSide(r) === "right"; });

    if (!filtered.length) {
      if (tbodyLeft) tbodyLeft.innerHTML = '<tr><td colspan="13" class="empty acc-emp-empty">Personel yok</td></tr>';
      if (tbodyRight) tbodyRight.innerHTML = '<tr><td colspan="12" class="empty acc-emp-empty">Personel yok</td></tr>';
      accUpdateFoot("acc-emp", 0, "personel");
      accUpdateEmpPayrollTotals([]);
      return;
    }

    accRenderEmployeesPanel(tbodyLeft, leftRows, "left", 13);
    accRenderEmployeesPanel(tbodyRight, rightRows, "right", 12);

    accBindEmployeeTable(tbodyLeft);
    accBindEmployeeTable(tbodyRight);

    var leftCount = document.getElementById("acc-emp-left-count");
    var rightCount = document.getElementById("acc-emp-right-count");
    if (leftCount) leftCount.textContent = leftRows.length + " kişi";
    if (rightCount) rightCount.textContent = rightRows.length + " kişi";

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
    else if (tab === "transactions") { accSyncTxDateToPeriod(); accLoadPaymentMethods(); accLoadTransactions(); }
    else if (tab === "commissions") accLoadPaymentMethods();
    else if (tab === "expenses") { accLoadCategories(); accLoadExpenses(); }
    else if (tab === "vault") accLoadVault();
    else if (tab === "payroll") { accLoadEmpOptions(); accLoadEmployees(); }
  }

  function accRefreshAll() {
    accLoadDashboard();
    accSyncTxDateToPeriod();
    if (accActiveTab === "transactions") { accLoadPaymentMethods(); accLoadTransactions(); }
    else if (accActiveTab === "commissions") accLoadPaymentMethods();
    else if (accActiveTab === "expenses") { accLoadCategories(); accLoadExpenses(); }
    else if (accActiveTab === "vault") accLoadVault();
    else if (accActiveTab === "payroll") { accLoadEmpOptions(); accLoadEmployees(); }
  }

  function accBindForm(formId, handler) {
    var form = document.getElementById(formId);
    if (form) form.addEventListener("submit", handler);
  }

  function accInitForms() {
    ["acc-tx-date", "acc-exp-date", "acc-vault-date", "acc-emp-start"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.value) el.value = accToday();
    });

    accBindForm("acc-tx-form", function (e) {
      e.preventDefault();
      var editIdEl = document.getElementById("acc-tx-edit-id");
      var editId = editIdEl && editIdEl.value ? editIdEl.value : "";
      var payload = Object.assign({
        tx_date: document.getElementById("acc-tx-date").value,
        payment_method_id: document.getElementById("acc-tx-payment").value,
        tx_type: document.getElementById("acc-tx-type").value,
        amount: document.getElementById("acc-tx-amount").value,
        currency: document.getElementById("acc-tx-currency").value
      }, accReadFormRates("acc-tx-rate-usd", "acc-tx-rate-eur"));
      var url = editId
        ? "/api/accounting/transactions/" + editId
        : "/api/accounting/transactions";
      accApi(url, {
        method: editId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (r && r.ok) {
          accResetTxForm();
          accLoadTransactions(); accLoadDashboard();
          accSavedToast(editId ? "İşlem güncellendi" : "İşlem kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    var txCancel = document.getElementById("acc-tx-edit-cancel");
    if (txCancel) txCancel.addEventListener("click", accResetTxForm);

    accBindForm("acc-pm-form", function (e) {
      e.preventDefault();
      var txType = document.getElementById("acc-pm-type").value;
      if (!txType) { alert("İşlem türü seçin: Yatırım veya Çekim."); return; }
      var body = {
        name: document.getElementById("acc-pm-name").value.trim(),
        tx_type: txType,
        commission_rate: document.getElementById("acc-pm-rate").value
      };
      var month = accSelectedMonthPeriod();
      if (month) body.period = month;
      accApi("/api/accounting/payment-methods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
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

    accBindForm("acc-cat-form", function (e) {
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

    accBindForm("acc-exp-form", function (e) {
      e.preventDefault();
      var editIdEl = document.getElementById("acc-exp-edit-id");
      var editId = editIdEl && editIdEl.value ? editIdEl.value.trim() : "";
      var body = Object.assign({
        expense_date: document.getElementById("acc-exp-date").value,
        category_id: document.getElementById("acc-exp-category").value,
        amount: document.getElementById("acc-exp-amount").value,
        currency: document.getElementById("acc-exp-currency").value,
        description: document.getElementById("acc-exp-desc").value.trim()
      }, accReadFormRates("acc-exp-rate-usd", "acc-exp-rate-eur"));
      var url = editId ? "/api/accounting/expenses/" + editId : "/api/accounting/expenses";
      accApi(url, {
        method: editId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(function (r) {
        if (r && r.ok) {
          accResetExpenseForm();
          accLoadExpenses();
          accLoadDashboard();
          accSavedToast(editId ? "Gider güncellendi" : "Gider kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    var expCancel = document.getElementById("acc-exp-edit-cancel");
    if (expCancel) expCancel.onclick = accResetExpenseForm;

    var expFilterQ = document.getElementById("acc-exp-filter-q");
    if (expFilterQ) {
      expFilterQ.addEventListener("input", function () {
        accSetExpenseFilter(accData["acc-exp"].filterCat, expFilterQ.value);
      });
    }
    var expFilterCat = document.getElementById("acc-exp-filter-cat");
    if (expFilterCat) {
      expFilterCat.addEventListener("change", function () {
        accSetExpenseFilter(expFilterCat.value, accData["acc-exp"].filterQ);
      });
    }
    var expFilterClear = document.getElementById("acc-exp-filter-clear");
    if (expFilterClear) expFilterClear.onclick = accClearExpenseFilter;

    accBindForm("acc-vault-form", function (e) {
      e.preventDefault();
      var editIdEl = document.getElementById("acc-vault-edit-id");
      var editId = editIdEl && editIdEl.value ? editIdEl.value.trim() : "";
      var body = Object.assign({
        tx_date: document.getElementById("acc-vault-date").value,
        vault_id: parseInt(document.getElementById("acc-vault-select").value, 10),
        operation_type: document.getElementById("acc-vault-optype").value.trim(),
        method_name: document.getElementById("acc-vault-method").value.trim(),
        direction: document.getElementById("acc-vault-direction").value,
        usdt_amount: document.getElementById("acc-vault-usdt").value,
        fee_usdt: document.getElementById("acc-vault-fee").value || 0,
        description: document.getElementById("acc-vault-desc").value.trim()
      }, accReadFormRates("acc-vault-rate-usd", null));
      var url = editId
        ? "/api/accounting/vault-transactions/" + editId
        : "/api/accounting/vault-transactions";
      accApi(url, {
        method: editId ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
      }).then(function (r) {
        if (r && r.ok) {
          accResetVaultForm();
          accLoadVault();
          accSavedToast(editId ? "Kasa hareketi güncellendi" : "Kasa hareketi kaydedildi", r.data.rates);
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    accBindForm("acc-optype-form", function (e) {
      e.preventDefault();
      accApi("/api/accounting/vault-operation-types", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: document.getElementById("acc-optype-name").value.trim() })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-optype-name").value = "";
          accLoadVault(); accToast("İşlem başlığı eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    accBindForm("acc-method-form", function (e) {
      e.preventDefault();
      accApi("/api/accounting/vault-methods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: document.getElementById("acc-method-name").value.trim() })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-method-name").value = "";
          accLoadVault(); accToast("Yöntem eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    var vaultAddToggle = document.getElementById("acc-vault-add-toggle");
    var vaultCreateForm = document.getElementById("acc-vault-create-form");
    var vaultAddCancel = document.getElementById("acc-vault-add-cancel");
    var vaultEditCancel = document.getElementById("acc-vault-edit-cancel");
    if (vaultEditCancel) {
      vaultEditCancel.onclick = accCancelVaultEdit;
    }
    if (vaultAddToggle && vaultCreateForm) {
      vaultAddToggle.onclick = function () { vaultCreateForm.hidden = !vaultCreateForm.hidden; };
    }
    if (vaultAddCancel && vaultCreateForm) {
      vaultAddCancel.onclick = function () { vaultCreateForm.hidden = true; };
    }
    var vaultCreate = document.getElementById("acc-vault-create-form");
    if (vaultCreate) {
      vaultCreate.addEventListener("submit", function (e) {
        e.preventDefault();
        accApi("/api/accounting/vaults", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: document.getElementById("acc-vault-new-name").value.trim(),
            opening_usdt: document.getElementById("acc-vault-new-open-usdt").value || 0,
            opening_try: document.getElementById("acc-vault-new-open-try").value || 0
          })
        }).then(function (r) {
          if (r && r.ok) {
            document.getElementById("acc-vault-new-name").value = "";
            document.getElementById("acc-vault-new-open-usdt").value = "0";
            document.getElementById("acc-vault-new-open-try").value = "0";
            vaultCreateForm.hidden = true;
            accLoadVault();
            accToast("Kasa eklendi");
          } else if (r) alert(r.data.error || "Hata");
        });
      });
    }
    var vaultFilter = document.getElementById("acc-vault-filter");
    if (vaultFilter) {
      vaultFilter.addEventListener("change", function () {
        accSetVaultFilter(vaultFilter.value);
      });
    }
    var vaultFeeSuggest = document.getElementById("acc-vault-fee-suggest");
    if (vaultFeeSuggest) vaultFeeSuggest.onclick = accSuggestVaultFee;
    document.querySelectorAll(".acc-vault-fee-preset").forEach(function (btn) {
      btn.onclick = function () {
        var feeEl = document.getElementById("acc-vault-fee");
        if (feeEl) feeEl.value = btn.getAttribute("data-fee") || "0";
        accUpdateVaultTlPreview();
      };
    });
    var vaultDir = document.getElementById("acc-vault-direction");
    if (vaultDir) {
      vaultDir.addEventListener("change", function () {
        if (vaultDir.value === "in") {
          var feeEl = document.getElementById("acc-vault-fee");
          if (feeEl) feeEl.value = "0";
        }
        accUpdateVaultTlPreview();
      });
    }
    ["acc-vault-usdt", "acc-vault-direction", "acc-vault-rate-usd", "acc-vault-fee"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", accUpdateVaultTlPreview);
      if (el) el.addEventListener("change", accUpdateVaultTlPreview);
    });

    accBindForm("acc-emp-form", function (e) {
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
    accSyncTxDateToPeriod();
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
    var accFilterPeriod = document.getElementById("acc-filter-period");
    if (accFilterPeriod) accFilterPeriod.addEventListener("change", function () {
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
      accApplyFallbackRates();
      try { accInitForms(); } catch (err) { console.error("accInitForms", err); }
      try { accInitUi(); } catch (err) { console.error("accInitUi", err); }
      accStartRatesPolling();
      try { accSwitchTab("dashboard"); } catch (err) { console.error("accSwitchTab", err); }
      accLoadRates();
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
