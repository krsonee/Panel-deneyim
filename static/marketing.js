(function () {
  "use strict";

  var mktPerms = [];
  var mktLoaded = false;
  var mktDeals = [];
  var mktEditingId = null;

  var PAYMENT_LABELS = { pending: "Bekliyor", paid: "Ödendi", cancelled: "İptal" };
  var PAYMENT_CYCLE = { pending: "paid", paid: "cancelled", cancelled: "pending" };
  var STATUS_LABELS = { active: "Aktif", paused: "Duraklatıldı", ended: "Sona Erdi" };
  var STATUS_CYCLE = { active: "paused", paused: "ended", ended: "active" };
  var CUR_SYMBOL = { TRY: "₺", USD: "$", EUR: "€" };

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

  function mktSelectedMonth() {
    var el = document.getElementById("mkt-filter-month");
    return el ? el.value : "";
  }

  function mktRenderSummary(summary) {
    summary = summary || {};
    var totals = summary.total_fixed_fee_by_currency || {};
    var parts = Object.keys(totals).map(function (cur) {
      return mktMoney(totals[cur], cur);
    });
    var el = document.getElementById("mkt-kpi-fee-total");
    if (el) el.textContent = parts.length ? parts.join(" · ") : "₺0,00";
    var acEl = document.getElementById("mkt-kpi-active-channels");
    if (acEl) acEl.textContent = summary.active_channel_count != null ? summary.active_channel_count : "—";
    var dcEl = document.getElementById("mkt-kpi-deal-count");
    if (dcEl) dcEl.textContent = summary.deal_count != null ? summary.deal_count : "—";
  }

  function mktRenderTable() {
    var tbody = document.getElementById("mkt-deals-table");
    if (!tbody) return;
    if (!mktDeals.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="empty">Henüz anlaşma eklenmedi</td></tr>';
      return;
    }
    tbody.innerHTML = mktDeals.map(function (d) {
      var passiveCls = d.status !== "active" ? " acc-pm-row-passive" : "";
      return '<tr class="' + passiveCls.trim() + '" data-mkt-id="' + d.id + '">' +
        '<td>' + mktFmtDate(d.agreement_date) + '</td>' +
        '<td class="acc-inv-name">' + mktEsc(d.channel_name) + '</td>' +
        '<td>' + mktEsc(d.channel_type || "—") + '</td>' +
        '<td>' + mktEsc(d.channel_ref_code || "—") + '</td>' +
        '<td>' + mktMoney(d.fixed_fee, d.fixed_fee_currency) + '</td>' +
        '<td>%' + (parseFloat(d.affiliate_commission_rate) || 0).toLocaleString("tr-TR") + '</td>' +
        '<td><span class="acc-pm-status-toggle" data-mkt-payment="' + d.id + '" data-mkt-payment-status="' + d.payment_status + '">' + (PAYMENT_LABELS[d.payment_status] || d.payment_status) + '</span></td>' +
        '<td><span class="acc-pm-status-toggle" data-mkt-status="' + d.id + '" data-mkt-status-value="' + d.status + '">' + (STATUS_LABELS[d.status] || d.status) + '</span></td>' +
        '<td>' + mktEsc(d.notes || "—") + '</td>' +
        '<td>' +
        '<button type="button" class="btn btn-sm" data-mkt-edit="' + d.id + '">Düzenle</button> ' +
        '<button type="button" class="btn btn-sm btn-danger" data-mkt-del="' + d.id + '">Sil</button>' +
        '</td>' +
        '</tr>';
    }).join("");
  }

  function mktLoadDeals() {
    var month = mktSelectedMonth();
    var url = "/api/marketing/deals" + (month ? "?month=" + encodeURIComponent(month) : "");
    return mktApi(url).then(function (r) {
      if (r && r.ok) {
        mktDeals = r.data.deals || [];
        mktRenderTable();
        mktRenderSummary(r.data.summary);
      } else if (r) {
        console.error("mktLoadDeals", r.data);
      }
    });
  }

  function mktDefaultDate() {
    var d = new Date();
    var mm = String(d.getMonth() + 1).padStart(2, "0");
    var dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
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
    document.getElementById("mkt-payment-status").value = deal.payment_status || "pending";
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
      payment_status: document.getElementById("mkt-payment-status").value,
      notes: document.getElementById("mkt-notes").value.trim()
    };
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
            mktLoadDeals();
            mktToast(isEdit ? "Anlaşma güncellendi" : "Anlaşma eklendi");
          } else if (r) {
            alert((r.data && r.data.error) || "İşlem başarısız");
          }
        });
      });
    }

    var monthEl = document.getElementById("mkt-filter-month");
    if (monthEl) monthEl.addEventListener("change", mktLoadDeals);

    var showAllBtn = document.getElementById("btn-mkt-show-all");
    if (showAllBtn) showAllBtn.addEventListener("click", function () {
      if (monthEl) monthEl.value = "";
      mktLoadDeals();
    });

    var refreshBtn = document.getElementById("btn-mkt-refresh");
    if (refreshBtn) refreshBtn.addEventListener("click", mktLoadDeals);

    var tbody = document.getElementById("mkt-deals-table");
    if (tbody) {
      tbody.addEventListener("click", function (e) {
        var payBadge = e.target.closest ? e.target.closest("[data-mkt-payment]") : null;
        if (payBadge) {
          var pid = payBadge.getAttribute("data-mkt-payment");
          var next = PAYMENT_CYCLE[payBadge.getAttribute("data-mkt-payment-status")] || "pending";
          mktApi("/api/marketing/deals/" + pid, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ payment_status: next })
          }).then(function (r) { if (r && r.ok) mktLoadDeals(); });
          return;
        }
        var statBadge = e.target.closest ? e.target.closest("[data-mkt-status]") : null;
        if (statBadge) {
          var sid = statBadge.getAttribute("data-mkt-status");
          var nextS = STATUS_CYCLE[statBadge.getAttribute("data-mkt-status-value")] || "active";
          mktApi("/api/marketing/deals/" + sid, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: nextS })
          }).then(function (r) { if (r && r.ok) mktLoadDeals(); });
          return;
        }
        var editBtn = e.target.closest ? e.target.closest("[data-mkt-edit]") : null;
        if (editBtn) {
          var deal = mktDeals.filter(function (d) { return String(d.id) === editBtn.getAttribute("data-mkt-edit"); })[0];
          if (deal) mktFillFormForEdit(deal);
          return;
        }
        var delBtn = e.target.closest ? e.target.closest("[data-mkt-del]") : null;
        if (delBtn) {
          if (!confirm("Bu anlaşma silinsin mi?")) return;
          mktApi("/api/marketing/deals/" + delBtn.getAttribute("data-mkt-del"), { method: "DELETE" }).then(function (r) {
            if (r && r.ok) { mktLoadDeals(); mktToast("Anlaşma silindi"); }
          });
        }
      });
    }
  }

  window.MakroMarketing = {
    init: function () {
      if (mktLoaded) return;
      mktLoaded = true;
      mktBindEvents();
      mktResetForm();
    },
    onShow: function () {
      if (!mktLoaded) this.init();
      mktLoadDeals();
    },
    setPermissions: function (perms) {
      mktPerms = perms || [];
    },
    refresh: mktLoadDeals
  };
})();
