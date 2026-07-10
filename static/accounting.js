(function () {
  "use strict";

  var ACC_PAGE = 10;
  var accPeriod = "all";
  var accActiveTab = "dashboard";
  var accPaymentMethods = [];
  var accCategories = [];
  var accDisplayCurrency = localStorage.getItem("acc_display_currency") || "TRY";
  var accRates = { usd_try: 34, eur_try: 37, date: null, source: "fallback" };
  var ACC_SYMBOLS = { TRY: "₺", USD: "$", EUR: "€" };

  var accData = {
    "acc-tx": { rows: [], expanded: false, sortKey: "tx_date", sortDir: "desc" },
    "acc-exp": { rows: [], expanded: false, sortKey: "expense_date", sortDir: "desc" },
    "acc-vault": { rows: [], expanded: false, sortKey: "tx_date", sortDir: "desc" },
    "acc-emp": { rows: [], expanded: false, sortKey: "name", sortDir: "asc" }
  };

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

  function accFxPreviewText(amount, currency) {
    amount = parseFloat(amount);
    if (!amount || amount <= 0) return "";
    return accApi("/api/accounting/convert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount: amount, currency: currency })
    }).then(function (res) {
      if (!res || !res.ok) return "";
      var c = res.data.converted;
      return "≈ " + accMoney(c.TRY, "TRY") + " · " + accMoney(c.USD, "USD") + " · " + accMoney(c.EUR, "EUR");
    });
  }

  function accBindFxPreview(amountId, currencyId, previewId) {
    var amountEl = document.getElementById(amountId);
    var curEl = document.getElementById(currencyId);
    var previewEl = document.getElementById(previewId);
    if (!amountEl || !curEl || !previewEl) return;
    var timer = null;
    function update() {
      clearTimeout(timer);
      timer = setTimeout(function () {
        accFxPreviewText(amountEl.value, curEl.value).then(function (txt) {
          previewEl.textContent = txt || "";
        });
      }, 250);
    }
    amountEl.addEventListener("input", update);
    curEl.addEventListener("change", update);
  }

  function accLoadRates() {
    return accApi("/api/accounting/exchange-rates").then(function (res) {
      if (!res || !res.ok) return;
      accRates = res.data;
      var hint = document.getElementById("acc-rates-hint");
      if (hint) {
        hint.textContent = "Güncel kur (1 USD = " + accRates.usd_try + " ₺, 1 EUR = " + accRates.eur_try +
          " ₺) · " + (accRates.date || "") + " · " + (accRates.source || "");
      }
    });
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

  function accLoadDashboard() {
    accApi("/api/accounting/dashboard" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      if (res.data.rates) accRates = res.data.rates;
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
      if (hint && k.payroll_monthly) {
        hint.textContent = "Aktif personel aylık: " + accMoney(k.payroll_monthly, accDisplayCurrency);
      }
      var sub = document.getElementById("acc-kpi-net-sub");
      if (sub && kpiAll.TRY) {
        var others = ["TRY", "USD", "EUR"].filter(function (c) { return c !== accDisplayCurrency; });
        sub.textContent = others.map(function (c) {
          var kk = kpiAll[c];
          return c + ": " + accMoney(kk ? kk.net_profit : 0, c);
        }).join(" · ");
      }
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
    return accApi("/api/accounting/employees").then(function (res) {
      if (!res || !res.ok) return;
      accData["acc-emp"].rows = res.data.employees || [];
      var payroll = res.data.monthly_payroll_total || {};
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
      department: function (r) { return r.department; },
      start_date: function (r) { return r.start_date; },
      salary: function (r) { return r.salary; },
      status: function (r) { return r.status; }
    });
    if (!accData["acc-emp"].rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Personel yok</td></tr>';
      accUpdateFoot("acc-emp", 0, "personel");
      return;
    }
    tbody.innerHTML = rows.map(function (r) {
      return '<tr><td><strong>' + accEsc(r.name) + '</strong></td>' +
        '<td>' + accEsc(r.department) + '</td>' +
        '<td class="mono">' + accEsc(r.start_date) + '</td>' +
        '<td>' + accMoneyCellHtml(r, "salary") + '</td>' +
        '<td><span class="tag ' + (r.status === "active" ? "online" : "offline") + '">' + accStatusLabel(r.status) + '</span></td>' +
        '<td><button class="btn btn-sm" data-toggle-emp="' + r.id + '" data-status="' + (r.status === "active" ? "left" : "active") + '">' +
        (r.status === "active" ? "Ayrıldı" : "Aktif") + '</button> ' +
        '<button class="btn btn-sm btn-danger" data-del-emp="' + r.id + '">Sil</button></td></tr>';
    }).join("");
    tbody.querySelectorAll("[data-toggle-emp]").forEach(function (btn) {
      btn.onclick = function () {
        accApi("/api/accounting/employees/" + btn.getAttribute("data-toggle-emp"), {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: btn.getAttribute("data-status") })
        }).then(function (r) { if (r && r.ok) accLoadEmployees(); });
      };
    });
    tbody.querySelectorAll("[data-del-emp]").forEach(function (btn) {
      btn.onclick = function () {
        if (!confirm("Silinsin mi?")) return;
        accApi("/api/accounting/employees/" + btn.getAttribute("data-del-emp"), { method: "DELETE" })
          .then(function (r) { if (r && r.ok) accLoadEmployees(); });
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
    else if (tab === "payroll") accLoadEmployees();
  }

  function accRefreshAll() {
    accLoadDashboard();
    if (accActiveTab === "transactions") { accLoadPaymentMethods(); accLoadTransactions(); }
    else if (accActiveTab === "commissions") accLoadPaymentMethods();
    else if (accActiveTab === "expenses") { accLoadCategories(); accLoadExpenses(); }
    else if (accActiveTab === "vault") accLoadVault();
    else if (accActiveTab === "payroll") accLoadEmployees();
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
        body: JSON.stringify({
          tx_date: document.getElementById("acc-tx-date").value,
          payment_method_id: document.getElementById("acc-tx-payment").value,
          tx_type: document.getElementById("acc-tx-type").value,
          amount: document.getElementById("acc-tx-amount").value,
          currency: document.getElementById("acc-tx-currency").value
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-tx-amount").value = "";
          accLoadTransactions(); accLoadDashboard(); accToast("İşlem kaydedildi");
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

    document.getElementById("acc-exp-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/expenses", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
          expense_date: document.getElementById("acc-exp-date").value,
          category_id: document.getElementById("acc-exp-category").value,
          amount: document.getElementById("acc-exp-amount").value,
          currency: document.getElementById("acc-exp-currency").value,
          description: document.getElementById("acc-exp-desc").value.trim()
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-exp-amount").value = "";
          document.getElementById("acc-exp-desc").value = "";
          accLoadExpenses(); accLoadDashboard(); accToast("Gider kaydedildi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    document.getElementById("acc-vault-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/vault-transactions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tx_date: document.getElementById("acc-vault-date").value,
          vault_name: document.getElementById("acc-vault-name").value.trim(),
          tx_type: document.getElementById("acc-vault-type").value,
          amount: document.getElementById("acc-vault-amount").value,
          currency: document.getElementById("acc-vault-currency").value,
          description: document.getElementById("acc-vault-desc").value.trim()
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-vault-amount").value = "";
          document.getElementById("acc-vault-desc").value = "";
          accLoadVault(); accToast("Kasa işlemi kaydedildi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

    document.getElementById("acc-emp-form").addEventListener("submit", function (e) {
      e.preventDefault();
      accApi("/api/accounting/employees", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: document.getElementById("acc-emp-name").value.trim(),
          department: document.getElementById("acc-emp-dept").value,
          start_date: document.getElementById("acc-emp-start").value,
            salary: document.getElementById("acc-emp-salary").value,
            currency: document.getElementById("acc-emp-currency").value,
            status: document.getElementById("acc-emp-status").value
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-emp-name").value = "";
          document.getElementById("acc-emp-salary").value = "";
          accLoadEmployees(); accToast("Personel eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });
    accBindFxPreview("acc-tx-amount", "acc-tx-currency", "acc-tx-fx-preview");
    accBindFxPreview("acc-exp-amount", "acc-exp-currency", "acc-exp-fx-preview");
    accBindFxPreview("acc-vault-amount", "acc-vault-currency", "acc-vault-fx-preview");
    accBindFxPreview("acc-emp-salary", "acc-emp-currency", "acc-emp-fx-preview");
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
        if (accActiveTab === "payroll") accLoadEmployees();
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
    }
  };
})();
