(function () {
  "use strict";

  var ACC_PAGE = 10;
  var accPeriod = "all";
  var accActiveTab = "dashboard";
  var accPaymentMethods = [];
  var accCategories = [];

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

  function accMoney(n) {
    n = parseFloat(n) || 0;
    return "$" + n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

  function accVaultTypeLabel(t) {
    return t === "in" ? "Giriş" : "Çıkış";
  }

  function accStatusLabel(s) {
    return s === "active" ? "Aktif Çalışıyor" : "Ayrıldı";
  }

  function accLoadDashboard() {
    accApi("/api/accounting/dashboard" + accPeriodQuery()).then(function (res) {
      if (!res || !res.ok) return;
      var k = res.data.kpi || {};
      document.getElementById("acc-kpi-deposits").textContent = accMoney(k.total_deposits);
      document.getElementById("acc-kpi-withdrawals").textContent = accMoney(k.total_withdrawals);
      document.getElementById("acc-kpi-commission").textContent = accMoney(k.total_commission);
      document.getElementById("acc-kpi-expenses").textContent = accMoney(k.total_expenses);
      var netEl = document.getElementById("acc-kpi-net");
      netEl.textContent = accMoney(k.net_profit);
      netEl.classList.toggle("negative", (k.net_profit || 0) < 0);
      var hint = document.getElementById("acc-kpi-payroll-hint");
      if (hint && k.payroll_monthly) {
        hint.textContent = "Aktif personel aylık: " + accMoney(k.payroll_monthly);
      }
    });
  }

  function accLoadPaymentMethods() {
    return accApi("/api/accounting/payment-methods").then(function (res) {
      if (!res || !res.ok) return;
      accPaymentMethods = res.data.payment_methods || [];
      var sel = document.getElementById("acc-tx-payment");
      if (sel) {
        sel.innerHTML = accPaymentMethods.length
          ? accPaymentMethods.map(function (p) {
              return '<option value="' + p.id + '">' + accEsc(p.name) + " (%" + p.commission_rate + ")</option>";
            }).join("")
          : '<option value="">Önce payment ekleyin</option>';
      }
      var tbody = document.getElementById("acc-pm-table");
      if (!tbody) return;
      if (!accPaymentMethods.length) {
        tbody.innerHTML = '<tr><td colspan="4" class="empty">Henüz payment tanımı yok</td></tr>';
        return;
      }
      tbody.innerHTML = accPaymentMethods.map(function (p) {
        return '<tr><td><strong>' + accEsc(p.name) + '</strong></td>' +
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
        '<td><strong>' + accMoney(r.amount) + '</strong></td>' +
        '<td>' + r.commission_rate + '%</td>' +
        '<td>' + accMoney(r.commission_amount) + '</td>' +
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
        '<td><strong>' + accMoney(r.amount) + '</strong></td>' +
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
        '<td><strong>' + accMoney(r.amount) + '</strong></td>' +
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
      document.getElementById("acc-payroll-total").textContent = accMoney(res.data.monthly_payroll_total);
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
        '<td>' + accMoney(r.salary) + '</td>' +
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
          amount: document.getElementById("acc-tx-amount").value
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
      accApi("/api/accounting/payment-methods", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: document.getElementById("acc-pm-name").value.trim(),
          commission_rate: document.getElementById("acc-pm-rate").value
        })
      }).then(function (r) {
        if (r && r.ok) {
          document.getElementById("acc-pm-name").value = "";
          accLoadPaymentMethods(); accToast("Payment eklendi");
        } else if (r) alert(r.data.error || "Hata");
      });
    });

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
  }

  function accInitUi() {
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
      accInitForms();
      accInitUi();
      accSwitchTab("dashboard");
    },
    refresh: accRefreshAll,
    onShow: function () {
      accRefreshAll();
    }
  };
})();
