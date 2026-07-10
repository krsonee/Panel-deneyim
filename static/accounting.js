(function () {
  "use strict";

  var ACC_PAGE = 10;
  var accPeriod = "all";
  var accActiveTab = "dashboard";
  var accPaymentMethods = [];
  var accCategories = [];
  var accEmployeeDepartments = [];
  var accSalaryCategories = [];
  var accDisplayCurrency = localStorage.getItem("acc_display_currency") || "TRY";
  var accRates = { usd_try: 34, eur_try: 37, date: null, source: "fallback" };
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
    if (usdEl && usdEl.value.trim()) body.rate_usd_try = usdEl.value.trim();
    if (eurEl && eurEl.value.trim()) body.rate_eur_try = eurEl.value.trim();
    return body;
  }

  function accClearFormRates(usdId, eurId) {
    var usdEl = document.getElementById(usdId);
    var eurEl = document.getElementById(eurId);
    if (usdEl) usdEl.value = "";
    if (eurEl) eurEl.value = "";
  }

  function accUpdateRatePlaceholders() {
    document.querySelectorAll(".acc-form-rate").forEach(function (el) {
      el.placeholder = "Boş = otomatik (" + (accRates.usd_try || "?") + " / " + (accRates.eur_try || "?") + ")";
    });
  }

  function accLoadRates() {
    return accApi("/api/accounting/exchange-rates").then(function (res) {
      if (!res || !res.ok) return;
      accRates = res.data;
      accUpdateRatePlaceholders();
    });
  }

  function accRatesSummary(rates) {
    rates = rates || accRates;
    var usd = parseFloat(rates.usd_try || 0).toFixed(2);
    var eur = parseFloat(rates.eur_try || 0).toFixed(2);
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

  function accPeriodQuery() {
    return accPeriod && accPeriod !== "all" ? "?period=" + encodeURIComponent(accPeriod) : "";
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
  }

  function accApplyDepartments(departments) {
    if (departments && departments.length) accEmployeeDepartments = departments;
    accRenderDeptChips();
    accRefreshEmpSelects();
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
    if (!chips) return;
    chips.innerHTML = accEmployeeDepartments.map(function (d) {
      return '<span class="acc-chip">' + accEsc(d.name) +
        ' <button type="button" data-del-dept="' + d.id + '" title="Sil">×</button></span>';
    }).join("") || '<span class="muted">Henüz departman yok</span>';
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
    if (!chips) return;
    chips.innerHTML = accSalaryCategories.map(function (c) {
      var tag = c.is_office ? ' <small class="muted">(ofis)</small>' : "";
      return '<span class="acc-chip">' + accEsc(c.name) + tag +
        ' <button type="button" data-del-salary-cat="' + c.id + '" title="Sil">×</button></span>';
    }).join("") || '<span class="muted">Henüz kategori yok</span>';
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
    return row.accrual[accDisplayCurrency] != null ? row.accrual[accDisplayCurrency] : row.accrual.TRY || 0;
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
    var catEl = document.getElementById("acc-emp-category");
    var endWrap = document.getElementById("acc-emp-end-wrap");
    var endEl = document.getElementById("acc-emp-end");
    var officeWrap = document.getElementById("acc-emp-office-fields");
    if (endWrap && statusEl) {
      var left = statusEl.value === "left";
      endWrap.hidden = !left;
      if (endEl) endEl.required = left;
      if (left && endEl && !endEl.value) endEl.value = accToday();
    }
    if (officeWrap && catEl) {
      var opt = catEl.options[catEl.selectedIndex];
      var isOffice = opt && opt.getAttribute("data-office") === "1";
      officeWrap.hidden = !isOffice;
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
      if (!res || !res.ok) return;
      accApplyPermissionsMeta(res.data);
      if (res.data.salary_categories) accApplySalaryCategories(res.data.salary_categories);
      if (res.data.departments) accApplyDepartments(res.data.departments);
      if (res.data.rates) {
        accRates = res.data.rates;
        accUpdateRatePlaceholders();
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
      accData["acc-emp"].rows = res.data.employees || [];
      var payroll = res.data.payroll_accrual || res.data.monthly_payroll_total || {};
      document.getElementById("acc-payroll-total").textContent = accMoney(
        payroll[accDisplayCurrency] != null ? payroll[accDisplayCurrency] : payroll.TRY || 0,
        accDisplayCurrency
      );
      accRenderEmployees();
    });
  }

  function accRenderEmployees() {
    var tbody = document.getElementById("acc-emp-table");
    var rows = accSortRows("acc-emp", accData["acc-emp"].rows, {
      name: function (r) { return r.name; },
      salary_category: function (r) { return r.salary_category; },
      department: function (r) { return r.department; },
      start_date: function (r) { return r.start_date; },
      end_date: function (r) { return r.end_date; },
      salary: function (r) { return r.salary; },
      accrual: function (r) { return accAccrualValue(r); },
      status: function (r) { return r.status; }
    });
    if (!accData["acc-emp"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">Personel yok</td></tr>';
      accUpdateFoot("acc-emp", 0, "personel");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      var officeInfo = "";
      if (accIsOfficeCategory(r.salary_category) && accCanViewOfficeSalaries) {
        officeInfo = '<br><small class="muted">Banka: ' + accMoney(r.bank_salary || 0, r.currency || "TRY") +
          " · Kripto: " + accMoney(r.crypto_salary || 0, r.currency || "TRY") +
          " · Avans: " + accMoney(r.advance_amount || 0, r.currency || "TRY") + "</small>";
      } else if (accIsOfficeCategory(r.salary_category) && r.salary_hidden) {
        officeInfo = '<br><small class="muted">Ofis maaş detayı gizli</small>';
      }
      var salaryCell = r.salary_hidden ? accHiddenMoney() : accMoneyCellHtml(r, "salary");
      var accrualCell = r.salary_hidden ? accHiddenMoney() : ("<strong>" + accMoney(accAccrualValue(r), accDisplayCurrency) + "</strong>");
      return '<tr><td><strong>' + accEsc(r.name) + '</strong>' + officeInfo + '</td>' +
        '<td><span class="tag">' + accEsc(accCategoryLabel(r.salary_category)) + '</span></td>' +
        '<td>' + accEsc(r.department) + '</td>' +
        '<td class="mono">' + accEsc(r.start_date) + '</td>' +
        '<td class="mono">' + accEsc(r.end_date || "—") + '</td>' +
        '<td>' + salaryCell + '</td>' +
        '<td>' + accrualCell + '</td>' +
        '<td><span class="tag ' + (r.status === "active" ? "online" : "offline") + '">' + accStatusLabel(r.status) + '</span></td>' +
        '<td><button class="btn btn-sm" data-toggle-emp="' + r.id + '" data-status="' + (r.status === "active" ? "left" : "active") + '">' +
        (r.status === "active" ? "Ayrıldı" : "Aktif") + '</button> ' +
        '<button class="btn btn-sm btn-danger" data-del-emp="' + r.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-toggle-emp]").forEach(function (btn) {
      btn.onclick = function () {
        var newStatus = btn.getAttribute("data-status");
        var body = { status: newStatus };
        if (newStatus === "left") {
          var endDate = prompt("Çıkış tarihi (YYYY-MM-DD):", accToday());
          if (!endDate) return;
          body.end_date = endDate;
        }
        accApi("/api/accounting/employees/" + btn.getAttribute("data-toggle-emp"), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }).then(function (r) {
          if (r && r.ok) { accLoadEmployees(); accLoadDashboard(); }
          else if (r) alert(r.data.error || "Hata");
        });
      };
    });
    tbody.querySelectorAll("[data-del-emp]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/employees/" + btn.getAttribute("data-del-emp"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) { accLoadEmployees(); accLoadDashboard(); accToast("Silindi"); } });
      };
    });
    accUpdateFoot("acc-emp", accData["acc-emp"].rows.length, "personel");
    accUpdateSortHeaders("acc-emp");
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
          salary_category: document.getElementById("acc-emp-category").value,
          department: document.getElementById("acc-emp-dept").value,
          start_date: document.getElementById("acc-emp-start").value,
            salary: document.getElementById("acc-emp-salary").value,
            currency: document.getElementById("acc-emp-currency").value,
            status: status,
            bank_salary: document.getElementById("acc-emp-bank").value || 0,
            crypto_salary: document.getElementById("acc-emp-crypto").value || 0,
            advance_amount: document.getElementById("acc-emp-advance").value || 0
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
          document.getElementById("acc-emp-salary").value = "";
          document.getElementById("acc-emp-bank").value = "0";
          document.getElementById("acc-emp-crypto").value = "0";
          document.getElementById("acc-emp-advance").value = "0";
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
    ["acc-emp-salary", "acc-emp-bank", "acc-emp-crypto", "acc-emp-advance"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("input", accUpdateOfficeRemaining);
    });
    accUpdateEmpFormUi();
    accBindFxPreview("acc-tx-amount", "acc-tx-currency", "acc-tx-fx-preview", "acc-tx-rate-usd", "acc-tx-rate-eur");
    accBindFxPreview("acc-exp-amount", "acc-exp-currency", "acc-exp-fx-preview", "acc-exp-rate-usd", "acc-exp-rate-eur");
    accBindFxPreview("acc-vault-amount", "acc-vault-currency", "acc-vault-fx-preview", "acc-vault-rate-usd", "acc-vault-rate-eur");
    accBindFxPreview("acc-emp-salary", "acc-emp-currency", "acc-emp-fx-preview", "acc-emp-rate-usd", "acc-emp-rate-eur");
  }

  function accInitUi() {
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
      accPeriod = this.value;
      accRefreshAll();
    });
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
  }

  window.MakroAccounting = {
    init: function () {
      accLoadRates();
      accInitForms();
      accInitUi();
      accSwitchTab("dashboard");
    },
    refresh: accRefreshAll,
    onShow: function () {
      accLoadRates().then(accRefreshAll);
    },
    setPermissions: function (perms) {
      var list = perms || [];
      var canView = list.indexOf("*") >= 0 || list.indexOf("accounting.payroll.office_salaries") >= 0;
      accSetOfficeSalaryAccess(canView);
    }
  };
})();
