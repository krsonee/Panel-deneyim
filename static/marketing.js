(function () {
  "use strict";

  var mktPerms = [];
  var mktLoaded = false;
  var mktDeals = [];
  var mktPayments = [];
  var mktEditingId = null;
  var mktExpandedDealId = null;
  var mktCurrentPeriodLabel = "";

  var STATUS_LABELS = { active: "Aktif", paused: "Duraklatıldı", ended: "Anlaşma Bitti · Ödeme Bitti" };
  var PAY_LABELS = { pending: "Bekliyor", paid: "Ödendi", skipped: "Yapılmayacak" };
  var CUR_SYMBOL = { TRY: "₺", USD: "$", EUR: "€" };
  var MONTH_TR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];

  function mktApi(url, opts) {
    opts = opts || {};
    return fetch(url, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (res.status === 401) {
          window.location.href = "/admin/login";
          return { ok: false, data: data };
        }
        return { ok: res.ok, status: res.status, data: data };
      });
    }).catch(function (err) {
      console.error("mktApi", err);
      return { ok: false, data: { error: "Bağlantı hatası" } };
    });
  }

  function mktToast(msg) {
    if (typeof window.toast === "function") { window.toast(msg); return; }
    var el = document.getElementById("toast");
    if (!el) { console.log(msg); return; }
    el.textContent = msg;
    el.classList.add("show");
    setTimeout(function () { el.classList.remove("show"); }, 2200);
  }

  function mktEsc(s) {
    return (s == null ? "" : String(s)).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function mktMoney(amount, currency) {
    var n = parseFloat(amount) || 0;
    var sym = CUR_SYMBOL[currency] || "₺";
    return sym + n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function mktFmtDate(iso) {
    if (!iso) return "—";
    var p = String(iso).slice(0, 10).split("-");
    return p.length === 3 ? p[2] + "." + p[1] + "." + p[0] : iso;
  }

  function mktPeriodLabel(period) {
    if (!period || period.length < 7) return period || "—";
    var parts = period.split("-");
    var m = parseInt(parts[1], 10);
    return (MONTH_TR[m] || parts[1]) + " " + parts[0];
  }

  function mktCurrentMonth() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0");
  }

  function mktSelectedMonth() {
    var el = document.getElementById("mkt-filter-month");
    return (el && el.value) ? el.value : mktCurrentMonth();
  }

  function mktEnsureMonthPicker() {
    var el = document.getElementById("mkt-filter-month");
    if (el && !el.value) el.value = mktCurrentMonth();
  }

  function mktRenderSummary(summary) {
    summary = summary || {};
    var acEl = document.getElementById("mkt-kpi-active-channels");
    if (acEl) acEl.textContent = summary.active_channel_count != null ? summary.active_channel_count : "—";
    var dcEl = document.getElementById("mkt-kpi-deal-count");
    if (dcEl) dcEl.textContent = summary.deal_count != null ? summary.deal_count : "—";
    var pmEl = document.getElementById("mkt-kpi-pending-month");
    if (pmEl) pmEl.textContent = summary.pending_this_month != null ? summary.pending_this_month : "—";
    var odEl = document.getElementById("mkt-kpi-overdue");
    if (odEl) odEl.textContent = summary.overdue_count != null ? summary.overdue_count : "—";
  }

  function mktPaymentRowClass(p) {
    if (p.status === "paid") return "mkt-pay-paid";
    if (p.status === "skipped") return "mkt-pay-skipped";
    var due = String(p.due_date || "").slice(0, 10);
    var today = new Date().toISOString().slice(0, 10);
    if (p.status === "pending" && due < today) return "mkt-pay-overdue";
    if (p.status === "pending") {
      var dueD = new Date(due + "T12:00:00");
      var todayD = new Date(today + "T12:00:00");
      var diff = Math.ceil((dueD - todayD) / 86400000);
      if (diff <= 3 && diff >= 0) return "mkt-pay-soon";
    }
    return "";
  }

  function mktRenderPaymentsTable() {
    var tbody = document.getElementById("mkt-payments-table");
    var title = document.getElementById("mkt-plan-title");
    var sub = document.getElementById("mkt-plan-sub");
    if (title) title.textContent = "Aylık Ödeme Planı — " + (mktCurrentPeriodLabel || mktPeriodLabel(mktSelectedMonth()));
    if (sub) sub.textContent = mktPayments.length ? mktPayments.length + " kayıt" : "";
    if (!tbody) return;
    if (!mktPayments.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty">Bu ay için ödeme planı yok</td></tr>';
      return;
    }
    tbody.innerHTML = mktPayments.map(function (p) {
      var cls = mktPaymentRowClass(p);
      var statusHtml = p.status === "paid"
        ? '<span class="mkt-badge mkt-badge-paid">Ödendi</span>'
        : p.status === "skipped"
          ? '<span class="mkt-badge mkt-badge-skipped">Yapılmayacak</span>'
          : '<span class="mkt-badge mkt-badge-pending">Bekliyor</span>';
      var btn = p.status === "pending"
        ? '<button type="button" class="btn btn-sm btn-primary" data-mkt-pay="' + p.id + '">Ödendi İşaretle</button> ' +
          '<button type="button" class="btn btn-sm btn-danger" data-mkt-skip="' + p.id + '">Yapılmayacak</button>'
        : p.status === "paid"
          ? '<button type="button" class="btn btn-sm" data-mkt-unpay="' + p.id + '">Geri Al</button>'
          : "";
      return '<tr class="' + cls + '">' +
        '<td>' + mktPeriodLabel(p.period) + '</td>' +
        '<td>' + mktFmtDate(p.due_date) + '</td>' +
        '<td class="acc-inv-name">' + mktEsc(p.channel_name) + '</td>' +
        '<td>' + mktMoney(p.amount, p.currency) + '</td>' +
        '<td>' + statusHtml + '</td>' +
        '<td>' + btn + '</td>' +
        '</tr>';
    }).join("");
  }

  function mktRenderDealSchedules() {
    var box = document.getElementById("mkt-deal-schedules");
    if (!box) return;
    if (mktExpandedDealId == null) {
      box.innerHTML = "";
      return;
    }
    var deal = mktDeals.filter(function (d) { return d.id === mktExpandedDealId; })[0];
    if (!deal || !deal.payments || !deal.payments.length) {
      box.innerHTML = "";
      return;
    }
    var rows = deal.payments.map(function (p) {
      var cls = mktPaymentRowClass(p);
      var statusHtml = p.status === "paid"
        ? '<span class="mkt-badge mkt-badge-paid">Ödendi</span>'
        : p.status === "skipped"
          ? '<span class="mkt-badge mkt-badge-skipped">Yapılmayacak</span>'
          : '<span class="mkt-badge mkt-badge-pending">Bekliyor</span>';
      var btn = p.status === "pending" && deal.status === "active"
        ? '<button type="button" class="btn btn-sm btn-primary" data-mkt-pay="' + p.id + '">Ödendi</button> ' +
          '<button type="button" class="btn btn-sm btn-danger" data-mkt-skip="' + p.id + '">Yapılmayacak</button>'
        : p.status === "pending"
          ? '<button type="button" class="btn btn-sm btn-danger" data-mkt-skip="' + p.id + '">Yapılmayacak</button>'
        : "";
      return '<tr class="' + cls + '">' +
        '<td>' + mktPeriodLabel(p.period) + '</td>' +
        '<td>' + mktFmtDate(p.due_date) + '</td>' +
        '<td>' + mktMoney(p.amount, p.currency) + '</td>' +
        '<td>' + statusHtml + '</td>' +
        '<td>' + btn + '</td>' +
        '</tr>';
    }).join("");
    box.innerHTML =
      '<div class="card" style="margin:0 1rem 1rem;border:1px solid var(--border);">' +
      '<div class="card-head"><span>' + mktEsc(deal.channel_name) + ' — Aylık Ödeme Takvimi</span></div>' +
      '<div class="table-wrap"><div class="table-scroll"><table class="acc-inv-table">' +
      '<thead><tr><th>Ay</th><th>Ödeme Tarihi</th><th>Tutar</th><th>Durum</th><th></th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table></div></div></div>';
  }

  function mktRenderDealsTable() {
    var tbody = document.getElementById("mkt-deals-table");
    if (!tbody) return;
    if (!mktDeals.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="empty">Henüz anlaşma eklenmedi</td></tr>';
      mktRenderDealSchedules();
      return;
    }
    tbody.innerHTML = mktDeals.map(function (d) {
      var passiveCls = d.status !== "active" ? " acc-pm-row-passive" : "";
      var expanded = mktExpandedDealId === d.id ? " mkt-row-expanded" : "";
      var ps = d.payment_summary || {};
      var overdueHint = ps.overdue_count > 0 ? ' <span class="mkt-badge mkt-badge-overdue">' + ps.overdue_count + ' gecikmiş</span>' : "";
      var endBtn = d.status === "active"
        ? '<button type="button" class="btn btn-sm btn-danger" data-mkt-end="' + d.id + '">Anlaşma Bitti</button> '
        : "";
      return '<tr class="mkt-deal-row' + passiveCls + expanded + '" data-mkt-deal-row="' + d.id + '">' +
        '<td>' + mktFmtDate(d.agreement_date) + '</td>' +
        '<td class="acc-inv-name">' + mktEsc(d.channel_name) + overdueHint + '</td>' +
        '<td>' + mktEsc(d.channel_type || "—") + '</td>' +
        '<td>' + mktMoney(d.fixed_fee, d.fixed_fee_currency) + '</td>' +
        '<td>%' + (parseFloat(d.affiliate_commission_rate) || 0).toLocaleString("tr-TR") + '</td>' +
        '<td><span class="mkt-status-' + d.status + '">' + (STATUS_LABELS[d.status] || d.status) + '</span></td>' +
        '<td>' +
        endBtn +
        '<button type="button" class="btn btn-sm" data-mkt-edit="' + d.id + '">Düzenle</button> ' +
        '<button type="button" class="btn btn-sm btn-danger" data-mkt-del="' + d.id + '">Sil</button>' +
        '</td>' +
        '</tr>';
    }).join("");
    mktRenderDealSchedules();
  }

  function mktLoadAll() {
    mktEnsureMonthPicker();
    var month = mktSelectedMonth();
    return Promise.all([
      mktApi("/api/marketing/deals").then(function (r) {
        if (r && r.ok) {
          mktDeals = r.data.deals || [];
          mktRenderSummary(r.data.summary);
          mktRenderDealsTable();
        }
      }),
      mktApi("/api/marketing/payments?month=" + encodeURIComponent(month)).then(function (r) {
        if (r && r.ok) {
          mktPayments = r.data.payments || [];
          mktCurrentPeriodLabel = r.data.period_label || "";
          mktRenderPaymentsTable();
        }
      })
    ]);
  }

  function mktMarkPayment(paymentId, status) {
    if (status === "skipped") {
      if (!confirm("Bu ödeme yapılmayacak olarak işaretlenecek ve hatırlatmalardan çıkarılacak. Onaylıyor musunuz?")) {
        return Promise.resolve();
      }
    }
    return mktApi("/api/marketing/payments/" + paymentId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: status })
    }).then(function (r) {
      if (r && r.ok) {
        mktToast(status === "paid" ? "Ödeme işaretlendi" : status === "skipped" ? "Ödeme yapılmayacak olarak işaretlendi" : "Ödeme bekliyor olarak güncellendi");
        mktLoadAll();
        mktCheckReminders(true);
      } else if (r) {
        alert((r.data && r.data.error) || "Güncellenemedi");
      }
    });
  }

  function mktEndDeal(dealId) {
    if (!confirm("Anlaşmayı bitirmek istediğine emin misin?\n\nAna listede \"Anlaşma Bitti · Ödeme Bitti\" olarak pasife alınır. Gelecek ayların bekleyen ödemeleri iptal edilir.")) return;
    mktApi("/api/marketing/deals/" + dealId + "/end", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    }).then(function (r) {
      if (r && r.ok) {
        mktToast("Anlaşma sonlandırıldı");
        mktLoadAll();
      } else if (r) {
        alert((r.data && r.data.error) || "İşlem başarısız");
      }
    });
  }

  function mktDefaultDate() {
    var d = new Date();
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }

  function mktResetForm() {
    var form = document.getElementById("mkt-deal-form");
    if (form) form.reset();
    var dateEl = document.getElementById("mkt-agreement-date");
    if (dateEl) dateEl.value = mktDefaultDate();
    mktEditingId = null;
    var btn = form ? form.querySelector("button[type=submit]") : null;
    if (btn) btn.textContent = "Ekle";
  }

  function mktFillFormForEdit(deal) {
    document.getElementById("mkt-agreement-date").value = (deal.agreement_date || "").slice(0, 10);
    document.getElementById("mkt-channel-name").value = deal.channel_name || "";
    document.getElementById("mkt-channel-type").value = deal.channel_type || "";
    document.getElementById("mkt-channel-ref").value = deal.channel_ref_code || "";
    document.getElementById("mkt-fee-currency").value = deal.fixed_fee_currency || "TRY";
    document.getElementById("mkt-fixed-fee").value = deal.fixed_fee != null ? deal.fixed_fee : "";
    document.getElementById("mkt-comm-rate").value = deal.affiliate_commission_rate != null ? deal.affiliate_commission_rate : "";
    document.getElementById("mkt-notes").value = deal.notes || "";
    mktEditingId = deal.id;
    var form = document.getElementById("mkt-deal-form");
    var btn = form ? form.querySelector("button[type=submit]") : null;
    if (btn) btn.textContent = "Güncelle (#" + deal.id + ")";
    if (form) form.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function mktCollectFormPayload() {
    return {
      agreement_date: document.getElementById("mkt-agreement-date").value,
      channel_name: document.getElementById("mkt-channel-name").value.trim(),
      channel_type: document.getElementById("mkt-channel-type").value.trim(),
      channel_ref_code: document.getElementById("mkt-channel-ref").value.trim(),
      fixed_fee_currency: document.getElementById("mkt-fee-currency").value,
      fixed_fee: document.getElementById("mkt-fixed-fee").value,
      affiliate_commission_rate: document.getElementById("mkt-comm-rate").value,
      notes: document.getElementById("mkt-notes").value.trim()
    };
  }

  function mktTodayKey() {
    return new Date().toISOString().slice(0, 10);
  }

  function mktReminderDismissedToday() {
    try {
      return localStorage.getItem("mkt_reminder_dismiss_" + mktTodayKey()) === "1";
    } catch (e) {
      return false;
    }
  }

  function mktDismissReminderToday() {
    try {
      localStorage.setItem("mkt_reminder_dismiss_" + mktTodayKey(), "1");
    } catch (e) { /* ignore */ }
    var modal = document.getElementById("mkt-reminder-modal");
    if (modal) modal.classList.remove("open");
  }

  function mktShowReminderModal(reminders) {
    if (!reminders || !reminders.length) return;
    if (mktReminderDismissedToday()) return;
    var list = document.getElementById("mkt-reminder-list");
    var modal = document.getElementById("mkt-reminder-modal");
    if (!list || !modal) return;
    list.innerHTML = reminders.map(function (r) {
      var overdue = r.is_overdue || r.days_until < 0;
      var msg = overdue
        ? "<strong>GECİKMİŞ</strong> — " + Math.abs(r.days_until) + " gün geçti"
        : r.days_until === 0
          ? "<strong>BUGÜN</strong> ödeme günü"
          : r.days_until + " gün kaldı";
      return '<div class="mkt-reminder-item' + (overdue ? " mkt-reminder-overdue" : "") + '">' +
        '<div><strong>' + mktEsc(r.channel_name) + '</strong> · ' + mktEsc(r.period_label || mktPeriodLabel(r.period)) + '</div>' +
        '<div class="muted" style="font-size:0.82rem;">Vade: ' + mktFmtDate(r.due_date) + ' · ' + mktMoney(r.amount, r.currency) + '</div>' +
        '<div style="font-size:0.82rem;margin-top:0.25rem;">' + msg + '</div>' +
        '<div style="display:flex;gap:0.45rem;flex-wrap:wrap;margin-top:0.5rem;">' +
        '<button type="button" class="btn btn-sm btn-primary" data-mkt-reminder-pay="' + r.id + '">Ödendi İşaretle</button>' +
        '<button type="button" class="btn btn-sm btn-danger" data-mkt-reminder-skip="' + r.id + '">Ödeme Yapılmayacak</button>' +
        '</div>' +
        '</div>';
    }).join("");
    modal.classList.add("open");
  }

  function mktCheckReminders(forceShow) {
    if (!forceShow && mktReminderDismissedToday()) return Promise.resolve();
    var hasPerm = mktPerms.indexOf("*") >= 0 || mktPerms.indexOf("module.marketing") >= 0 || mktPerms.indexOf("marketing.deals") >= 0;
    if (!hasPerm && mktPerms.length) return Promise.resolve();
    return mktApi("/api/marketing/reminders").then(function (r) {
      if (r && r.ok && r.data.reminders && r.data.reminders.length) {
        mktShowReminderModal(r.data.reminders);
      } else {
        var modal = document.getElementById("mkt-reminder-modal");
        if (modal) modal.classList.remove("open");
      }
    });
  }

  function mktBindEvents() {
    var form = document.getElementById("mkt-deal-form");
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var payload = mktCollectFormPayload();
        var isEdit = !!mktEditingId;
        var url = isEdit ? "/api/marketing/deals/" + mktEditingId : "/api/marketing/deals";
        mktApi(url, {
          method: isEdit ? "PUT" : "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        }).then(function (r) {
          if (r && r.ok) {
            mktResetForm();
            mktLoadAll();
            mktToast(isEdit ? "Anlaşma güncellendi" : "Anlaşma eklendi — aylık plan oluşturuldu");
          } else if (r) {
            alert((r.data && r.data.error) || "İşlem başarısız");
          }
        });
      });
    }

    var monthEl = document.getElementById("mkt-filter-month");
    if (monthEl) monthEl.addEventListener("change", mktLoadAll);

    var refreshBtn = document.getElementById("btn-mkt-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", mktLoadAll);

    var dealsTbody = document.getElementById("mkt-deals-table");
    if (dealsTbody) {
      dealsTbody.addEventListener("click", function (e) {
        var row = e.target.closest ? e.target.closest("[data-mkt-deal-row]") : null;
        if (row && !e.target.closest("button")) {
          var id = parseInt(row.getAttribute("data-mkt-deal-row"), 10);
          mktExpandedDealId = mktExpandedDealId === id ? null : id;
          mktRenderDealsTable();
          return;
        }
        var endBtn = e.target.closest ? e.target.closest("[data-mkt-end]") : null;
        if (endBtn) { mktEndDeal(endBtn.getAttribute("data-mkt-end")); return; }
        var editBtn = e.target.closest ? e.target.closest("[data-mkt-edit]") : null;
        if (editBtn) {
          var deal = mktDeals.filter(function (d) { return String(d.id) === editBtn.getAttribute("data-mkt-edit"); })[0];
          if (deal) mktFillFormForEdit(deal);
          return;
        }
        var delBtn = e.target.closest ? e.target.closest("[data-mkt-del]") : null;
        if (delBtn) {
          if (!confirm("Bu anlaşma ve tüm ödeme planı silinsin mi?")) return;
          mktApi("/api/marketing/deals/" + delBtn.getAttribute("data-mkt-del"), { method: "DELETE" }).then(function (r) {
            if (r && r.ok) { mktExpandedDealId = null; mktLoadAll(); mktToast("Silindi"); }
          });
        }
      });
    }

    function payClickHandler(e) {
      var payBtn = e.target.closest ? e.target.closest("[data-mkt-pay]") : null;
      if (payBtn) { mktMarkPayment(payBtn.getAttribute("data-mkt-pay"), "paid"); return; }
      var skipBtn = e.target.closest ? e.target.closest("[data-mkt-skip]") : null;
      if (skipBtn) { mktMarkPayment(skipBtn.getAttribute("data-mkt-skip"), "skipped"); return; }
      var unpayBtn = e.target.closest ? e.target.closest("[data-mkt-unpay]") : null;
      if (unpayBtn) { mktMarkPayment(unpayBtn.getAttribute("data-mkt-unpay"), "pending"); return; }
    }

    var payTbody = document.getElementById("mkt-payments-table");
    if (payTbody) payTbody.addEventListener("click", payClickHandler);

    var schedules = document.getElementById("mkt-deal-schedules");
    if (schedules) schedules.addEventListener("click", payClickHandler);

    var remClose = document.getElementById("mkt-reminder-close");
    if (remClose) remClose.addEventListener("click", mktDismissReminderToday);
    var remOk = document.getElementById("mkt-reminder-ok");
    if (remOk) remOk.addEventListener("click", mktDismissReminderToday);

    var remList = document.getElementById("mkt-reminder-list");
    if (remList) {
      remList.addEventListener("click", function (e) {
        var payBtn = e.target.closest ? e.target.closest("[data-mkt-reminder-pay]") : null;
        if (payBtn) {
          mktMarkPayment(payBtn.getAttribute("data-mkt-reminder-pay"), "paid");
          return;
        }
        var skipBtn = e.target.closest ? e.target.closest("[data-mkt-reminder-skip]") : null;
        if (skipBtn) {
          mktMarkPayment(skipBtn.getAttribute("data-mkt-reminder-skip"), "skipped");
        }
      });
    }

    var remModal = document.getElementById("mkt-reminder-modal");
    if (remModal) {
      remModal.addEventListener("click", function (e) {
        if (e.target === remModal) mktDismissReminderToday();
      });
    }
  }

  window.MakroMarketing = {
    init: function () {
      if (mktLoaded) return;
      mktLoaded = true;
      mktBindEvents();
      mktResetForm();
      mktEnsureMonthPicker();
    },
    onShow: function () {
      if (!mktLoaded) this.init();
      mktLoadAll().then(function () {
        mktCheckReminders(false);
      });
    },
    setPermissions: function (perms) {
      mktPerms = perms || [];
    },
    refresh: mktLoadAll,
    checkReminders: function () {
      return mktCheckReminders(false);
    }
  };
})();
