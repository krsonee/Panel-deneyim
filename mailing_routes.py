"""Mailing modülü API rotaları — CRM, şablon, kampanya, IVR, rapor iskeleti."""

from __future__ import annotations

import csv
import html as html_lib
import io
import json
import os
import re
import secrets
import threading
import urllib.parse
from contextlib import closing

from flask import Blueprint, jsonify, redirect, request

import smartico_api
from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    get_mail_setting,
    insert_returning_id,
    iso,
    scalar,
    upsert_mail_setting,
    utcnow,
)

IMPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mail_imports")
IMPORT_CHUNK_SIZE = 2000


def _ensure_import_dir():
    os.makedirs(IMPORT_DIR, exist_ok=True)

MODULE_ACCESS = ("module.mailing",)
MAIL_DASH = ("mailing.dashboard", "module.mailing")
MAIL_CRM = ("mailing.crm", "module.mailing")
MAIL_TPL = ("mailing.templates", "module.mailing")
MAIL_CAMP = ("mailing.campaigns", "module.mailing")
MAIL_IVR = ("mailing.ivr", "module.mailing")
MAIL_REP = ("mailing.reports", "module.mailing")
MAIL_SET = ("mailing.settings", "module.mailing")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
LINK_TOKEN_RE = re.compile(r"\{\{\s*link\s*:\s*([^}]+)\s*\}\}", re.I)
HREF_RE = re.compile(r'(<a\b[^>]*\bhref\s*=\s*["\'])(https?://[^"\']+)(["\'])', re.I)


def _row(r):
    if not r:
        return None
    return dict(r)


def _rows(rs):
    return [dict(r) for r in (rs or [])]


def _parse_tags(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(t).strip() for t in data if str(t).strip()]
        except Exception:
            pass
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _tags_json(tags):
    return json.dumps(_parse_tags(tags), ensure_ascii=False)


def _contact_out(row):
    d = _row(row) if not isinstance(row, dict) else dict(row)
    if not d:
        return None
    d["tags"] = _parse_tags(d.get("tags"))
    d["unsubscribed"] = bool(d.get("unsubscribed"))
    return d


DEFAULT_GREETING_NAME = "değerli üye"


def _render_template(text, contact):
    """{{name}} boşsa 'Merhaba ,' gibi bozuk bir selamlama çıkmasın —
    isim yoksa nazik bir varsayılan ('değerli üye') kullanılır."""
    text = text or ""
    name = ((contact or {}).get("name") or "").strip()
    mapping = {
        "name": name or DEFAULT_GREETING_NAME,
        "email": (contact or {}).get("email") or "",
        "phone": (contact or {}).get("phone") or "",
    }
    for key, val in mapping.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def _plain_to_html(text):
    """Basit yazıyı basit HTML'e çevir — satır sonları + {{link:}} korunur."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    holders = {}

    def hold(m):
        key = f"__MAILINK{len(holders)}__"
        holders[key] = m.group(0)
        return key

    protected = LINK_TOKEN_RE.sub(hold, text)
    parts = []
    for block in protected.split("\n\n"):
        esc = html_lib.escape(block).replace("\n", "<br>\n")
        for key, raw in holders.items():
            esc = esc.replace(html_lib.escape(key), raw).replace(key, raw)
        parts.append(f"<p>{esc}</p>")
    return "\n".join(parts)


def _public_base():
    base = (os.environ.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base:
        return base
    try:
        return (request.url_root or "").rstrip("/")
    except RuntimeError:
        return ""


_SMARTICO_LINK_RE = re.compile(r"^\s*sc\s*:\s*(.+)$", re.I | re.S)


def _split_smartico_marker(dest):
    """'sc:https://...' işaretini ayıkla. Dönüş: (asıl_url, is_smartico)."""
    dest = (dest or "").strip()
    m = _SMARTICO_LINK_RE.match(dest)
    if m:
        return m.group(1).strip(), True
    return dest, False


def _make_click_token(conn, *, dest_url, send_id=None, contact_id=None, campaign_id=None, is_smartico=False):
    token = secrets.token_urlsafe(10)
    now = iso(utcnow())
    insert_returning_id(
        conn,
        """
        INSERT INTO mail_click_links
        (token, send_id, contact_id, campaign_id, dest_url, is_smartico, click_count, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, ?)
        """,
        (token, send_id, contact_id, campaign_id, dest_url, 1 if is_smartico else 0, now),
    )
    return token


def _track_url(token):
    return f"{_public_base()}/m/c/{token}"


def _append_query_param(url, key, value):
    """URL'e query param ekle/güncelle — mevcut parametreleri korur."""
    try:
        parts = urllib.parse.urlsplit(url)
        qs = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        qs = [(k, v) for k, v in qs if k != key]
        qs.append((key, str(value)))
        new_query = urllib.parse.urlencode(qs)
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
    except Exception:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}{key}={value}"


def _inject_tracking(conn, body, *, send_id, contact_id=None, campaign_id=None, as_html=True):
    """{{link:url}} / {{link:sc:url}} ve <a href> adreslerini kişiye özel takip URL'sine çevir.

    'sc:' önekiyle işaretlenen linkler Smartico affiliate linkidir; tıklanınca
    contact_id, sub-id parametresi (afp1 vb.) olarak Smartico'ya iletilir —
    böylece kayıt/FTD raporunda hangi contact'ın dönüştüğü görülebilir.
    """
    body = body or ""
    if not body:
        return body

    def token_for(raw_dest):
        dest, is_sc = _split_smartico_marker(raw_dest)
        if not dest or dest.startswith("/m/c/") or "/m/c/" in dest:
            return dest
        tok = _make_click_token(
            conn,
            dest_url=dest,
            send_id=send_id,
            contact_id=contact_id,
            campaign_id=campaign_id,
            is_smartico=is_sc,
        )
        return _track_url(tok)

    def repl_token(m):
        tracked = token_for(m.group(1))
        if as_html:
            safe_dest, _ = _split_smartico_marker(m.group(1))
            safe_dest = html_lib.escape(safe_dest, quote=True)
            return f'<a href="{tracked}" target="_blank" rel="noopener">{safe_dest}</a>'
        return tracked

    body = LINK_TOKEN_RE.sub(repl_token, body)

    if as_html:
        def repl_href(m):
            tracked = token_for(m.group(2))
            return f"{m.group(1)}{tracked}{m.group(3)}"

        body = HREF_RE.sub(repl_href, body)
    return body


def _tag_contact(conn, contact_id, tag, now=None):
    if not contact_id or not tag:
        return
    now = now or iso(utcnow())
    row = fetchone(conn, "SELECT tags FROM mail_contacts WHERE id = ?", (contact_id,))
    if not row:
        return
    tags = _parse_tags(row["tags"])
    if tag not in tags:
        tags.append(tag)
        execute(
            conn,
            "UPDATE mail_contacts SET tags = ?, updated_at = ? WHERE id = ?",
            (_tags_json(tags), now, contact_id),
        )
    exists = scalar(conn, "SELECT COUNT(*) FROM mail_contact_tags WHERE name = ?", (tag,))
    if not exists:
        insert_returning_id(
            conn,
            "INSERT INTO mail_contact_tags (name, created_at) VALUES (?, ?)",
            (tag, now),
        )


def _untag_contact(conn, contact_id, tag, now=None):
    if not contact_id or not tag:
        return
    now = now or iso(utcnow())
    row = fetchone(conn, "SELECT tags FROM mail_contacts WHERE id = ?", (contact_id,))
    if not row:
        return
    tags = _parse_tags(row["tags"])
    if tag in tags:
        tags.remove(tag)
        execute(
            conn,
            "UPDATE mail_contacts SET tags = ?, updated_at = ? WHERE id = ?",
            (_tags_json(tags), now, contact_id),
        )


def _campaign_selection_where(tag_filter, exclude_previously_sent):
    """Kampanya alıcı seçiminde kullanılan WHERE + params — hem sayım
    önizlemesinde hem gerçek eklemede aynı filtre mantığı kullanılsın diye."""
    clauses = ["unsubscribed = 0"]
    params = []
    tag_filter = (tag_filter or "").strip()
    if tag_filter:
        clauses.append('tags LIKE ?')
        params.append(f'%"{tag_filter}"%')
    if exclude_previously_sent:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM mail_sends s WHERE s.contact_id = mail_contacts.id)"
        )
    return " AND ".join(clauses), params


def _attach_campaign_recipients(conn, campaign_id, *, tag_filter, max_recipients, exclude_previously_sent, now):
    """Filtreye uyan kontakları (limitliyse en fazla max_recipients kadar,
    en eski/ilk eklenenden başlayarak) tek seferde toplu INSERT ile kampanyaya
    ekler — yüz binlerce satırda da satır-satır sorgu yapmaz."""
    where_sql, params = _campaign_selection_where(tag_filter, exclude_previously_sent)
    sql = f"SELECT id FROM mail_contacts WHERE {where_sql} ORDER BY id ASC"
    if max_recipients:
        sql += " LIMIT ?"
        params.append(max_recipients)
    contact_ids = [r["id"] for r in fetchall(conn, sql, tuple(params))]
    attached = 0
    chunk_size = 5000
    for i in range(0, len(contact_ids), chunk_size):
        chunk = contact_ids[i:i + chunk_size]
        values_sql = ",".join(["(?, ?, 'pending', ?)"] * len(chunk))
        vparams = []
        for contact_id in chunk:
            vparams += [campaign_id, contact_id, now]
        execute(
            conn,
            f"INSERT INTO mail_campaign_recipients (campaign_id, contact_id, status, created_at) VALUES {values_sql}",
            tuple(vparams),
        )
        attached += len(chunk)
    return attached


def _bulk_upsert_contacts(conn, batch, tag, now):
    """batch: [(email, name), ...]. Tek SQL ifadesiyle toplu insert/upsert —
    milyonlarca satırı satır-satır sorgu yapmadan işlemek için."""
    if not batch:
        return 0
    tag = (tag or "").strip()
    tag_json_single = json.dumps([tag], ensure_ascii=False) if tag else "[]"
    # Not: '%' işaretini SQL metninin İÇİNE değil, bağlı (bound) parametrenin
    # içine koyuyoruz. Postgres'te (psycopg2) '%s' dışında kalan her ham '%'
    # karakteri bir placeholder gibi sayılıp "IndexError: tuple index out of
    # range" hatasına yol açıyor — bu yüzden LIKE deseni burada Python'da
    # hazırlanıp parametre olarak veriliyor (SQLite'ta da sorunsuz çalışır).
    tag_like_pattern = f'%"{tag}"%'
    values_sql = []
    params = []
    for email, name in batch:
        values_sql.append("(?, ?, ?, ?, 0, '', ?, ?)")
        params += [email, name, tag_json_single, "csv", now, now]
    sql = f"""
        INSERT INTO mail_contacts (email, name, tags, source, unsubscribed, notes, created_at, updated_at)
        VALUES {",".join(values_sql)}
        ON CONFLICT (email) DO UPDATE SET
            name = CASE WHEN mail_contacts.name = '' THEN EXCLUDED.name ELSE mail_contacts.name END,
            tags = CASE
                WHEN ? = '' THEN mail_contacts.tags
                WHEN mail_contacts.tags LIKE ? THEN mail_contacts.tags
                WHEN mail_contacts.tags = '[]' THEN ?
                ELSE substr(mail_contacts.tags, 1, length(mail_contacts.tags) - 1) || ',"' || ? || '"]'
            END,
            updated_at = EXCLUDED.updated_at
    """
    params += [tag, tag_like_pattern, tag_json_single, tag]
    cur = execute(conn, sql, tuple(params))
    return cur.rowcount if cur.rowcount and cur.rowcount > 0 else len(batch)


def _detect_csv_delimiter(path):
    """Türkiye'de Excel'in varsayılan CSV export'u virgül yerine noktalı virgül
    (;) kullanır (virgül ondalık ayracı olduğu için). Header/örnek satırlara
    bakıp doğru ayracı otomatik seçiyoruz — aksi halde tüm satır tek bir
    sütun gibi okunur ve email/name sütunları hiç bulunamaz."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
            sample = f.read(65536)
    except OSError:
        return ","
    if not sample.strip():
        return ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        return dialect.delimiter
    except csv.Error:
        pass
    first_line = next((ln for ln in sample.splitlines() if ln.strip()), "")
    counts = {d: first_line.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _count_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return max(sum(1 for _ in f) - 1, 0)


def _iter_csv_rows(path):
    delimiter = _detect_csv_delimiter(path)
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            yield row


def _count_xlsx_rows(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        return max((ws.max_row or 1) - 1, 0)
    finally:
        wb.close()


def _iter_xlsx_rows(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header_raw = next(rows_iter)
        except StopIteration:
            return
        header = [(str(h).strip() if h is not None else "") for h in header_raw]
        for values in rows_iter:
            row = {}
            for i, key in enumerate(header):
                if not key:
                    continue
                val = values[i] if i < len(values) else None
                row[key] = "" if val is None else str(val).strip()
            yield row
    finally:
        wb.close()


def _run_import_job(job_id, path, tag):
    """Arka plan thread: dosyayı satır satır okuyup IMPORT_CHUNK_SIZE'lık
    gruplar halinde bulk upsert eder — HTTP isteğinden bağımsız çalışır,
    timeout'a düşmez. CSV ve XLSX (.xlsx) destekler."""
    now = iso(utcnow())
    is_xlsx = os.path.splitext(path)[1].lower() in (".xlsx", ".xlsm")
    count_fn = _count_xlsx_rows if is_xlsx else _count_csv_rows
    iter_fn = _iter_xlsx_rows if is_xlsx else _iter_csv_rows
    try:
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT status FROM mail_import_jobs WHERE id = ?", (job_id,))
            if existing and existing["status"] == "cancelling":
                execute(conn, "UPDATE mail_import_jobs SET status = 'cancelled', updated_at = ? WHERE id = ?", (now, job_id))
                conn.commit()
                return
            execute(conn, "UPDATE mail_import_jobs SET status = 'running', updated_at = ? WHERE id = ?", (now, job_id))
            conn.commit()

            total = count_fn(path)
            execute(conn, "UPDATE mail_import_jobs SET total_rows = ? WHERE id = ?", (total, job_id))
            conn.commit()

            processed = 0
            upserted = 0
            skipped = 0
            batch = []
            cancelled = False
            # Manuel next() döngüsü kullanıyoruz ki satırı ÜRETİRKEN (örn. bozuk
            # encoding, tutarsız sütun sayısı) bir hata çıksa bile o satırı
            # geçersiz sayıp devam edebilelim — tek bozuk satır tüm job'ı
            # 'error' durumuna düşürmesin, milyonlarca satırın kalanı işlensin.
            row_iter = iter_fn(path)
            while True:
                try:
                    row = next(row_iter)
                except StopIteration:
                    break
                except Exception:
                    processed += 1
                    skipped += 1
                    continue
                processed += 1
                try:
                    email = (row.get("email") or row.get("Email") or row.get("EMAIL") or "").strip().lower()
                    if not email or not EMAIL_RE.match(email):
                        skipped += 1
                        continue
                    name = (row.get("name") or row.get("Name") or "").strip()
                    batch.append((email, name))
                except Exception:
                    skipped += 1
                    continue
                if len(batch) >= IMPORT_CHUNK_SIZE:
                    try:
                        upserted += _bulk_upsert_contacts(conn, batch, tag, iso(utcnow()))
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        skipped += len(batch)
                    batch = []
                    execute(
                        conn,
                        """
                        UPDATE mail_import_jobs
                        SET processed_rows = ?, upserted_count = ?, skipped_count = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (processed, upserted, skipped, iso(utcnow()), job_id),
                    )
                    conn.commit()
                    status_row = fetchone(conn, "SELECT status FROM mail_import_jobs WHERE id = ?", (job_id,))
                    if status_row and status_row["status"] == "cancelling":
                        cancelled = True
                        break
            if batch and not cancelled:
                try:
                    upserted += _bulk_upsert_contacts(conn, batch, tag, iso(utcnow()))
                    conn.commit()
                except Exception:
                    conn.rollback()
                    skipped += len(batch)

            final_now = iso(utcnow())
            if cancelled:
                execute(
                    conn,
                    """
                    UPDATE mail_import_jobs
                    SET status = 'cancelled', processed_rows = ?, upserted_count = ?, skipped_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (processed, upserted, skipped, final_now, job_id),
                )
                conn.commit()
                return
            if tag:
                _ensure_tag(conn, tag, final_now)
            execute(
                conn,
                """
                UPDATE mail_import_jobs
                SET status = 'done', processed_rows = ?, upserted_count = ?, skipped_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (processed, upserted, skipped, final_now, job_id),
            )
            conn.commit()
    except Exception as exc:
        try:
            with closing(get_db()) as conn:
                execute(
                    conn,
                    "UPDATE mail_import_jobs SET status = 'error', error = ?, updated_at = ? WHERE id = ?",
                    (str(exc)[:500], iso(utcnow()), job_id),
                )
                conn.commit()
        except Exception:
            pass
    finally:
        try:
            os.remove(path)
        except Exception:
            pass


def _ensure_tag(conn, name, now):
    name = (name or "").strip()
    if not name:
        return
    exists = scalar(conn, "SELECT COUNT(*) FROM mail_contact_tags WHERE name = ?", (name,))
    if not exists:
        insert_returning_id(
            conn,
            "INSERT INTO mail_contact_tags (name, created_at) VALUES (?, ?)",
            (name, now),
        )


def _stub_send(conn, *, channel, to_email, subject, contact=None, campaign_id=None,
               contact_id=None, template_id=None, domain_id=None, to_phone="",
               html_body="", text_body=""):
    """Alibaba bağlanana kadar simüle gönderim kaydı + takip linkleri oluşturur."""
    now = iso(utcnow())
    mode = (get_mail_setting(conn, "provider_mode", "stub") or "stub").strip().lower()
    status = "simulated" if mode == "stub" else "queued"
    msg_id = f"stub-{secrets.token_hex(8)}" if status == "simulated" else ""
    send_id = insert_returning_id(
        conn,
        """
        INSERT INTO mail_sends (
            channel, campaign_id, contact_id, template_id, domain_id,
            to_email, to_phone, subject, status, provider_msg_id, error,
            opened_at, clicked_at, sent_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            channel,
            campaign_id,
            contact_id,
            template_id,
            domain_id,
            to_email,
            to_phone or "",
            subject or "",
            status,
            msg_id,
            "" if status == "simulated" else "Provider henüz bağlanmadı (stub kuyruk)",
            None,
            None,
            now if status == "simulated" else None,
            now,
        ),
    )
    # Inject tracking — HTML öncelikli (çift token üretmesin)
    if html_body:
        _inject_tracking(
            conn, html_body, send_id=send_id, contact_id=contact_id,
            campaign_id=campaign_id, as_html=True,
        )
    elif text_body:
        _inject_tracking(
            conn, text_body, send_id=send_id, contact_id=contact_id,
            campaign_id=campaign_id, as_html=False,
        )
    return send_id, status


def create_mailing_click_blueprint():
    """Public click redirect — auth yok."""
    bp = Blueprint("mailing_click", __name__)

    @bp.route("/m/c/<token>", methods=["GET"])
    def mail_click(token):
        token = (token or "").strip()
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_click_links WHERE token = ?", (token,))
            if not row:
                return ("Link bulunamadı.", 404)
            dest = row["dest_url"]
            if row["is_smartico"] and row["contact_id"]:
                subid_param = (get_mail_setting(conn, "smartico_subid_param", "afp1") or "afp1").strip() or "afp1"
                dest = _append_query_param(dest, subid_param, row["contact_id"])
            first = row["first_clicked_at"] or now
            execute(
                conn,
                """
                UPDATE mail_click_links SET
                    click_count = COALESCE(click_count, 0) + 1,
                    first_clicked_at = ?,
                    last_clicked_at = ?
                WHERE id = ?
                """,
                (first, now, row["id"]),
            )
            if row["send_id"]:
                execute(
                    conn,
                    """
                    UPDATE mail_sends SET clicked_at = COALESCE(clicked_at, ?)
                    WHERE id = ?
                    """,
                    (now, row["send_id"]),
                )
            if row["contact_id"]:
                _tag_contact(conn, row["contact_id"], "mail_tiklayan", now)
            conn.commit()
        return redirect(dest, code=302)

    return bp


def create_mailing_blueprint(permission_required):
    bp = Blueprint("mailing", __name__, url_prefix="/api/mailing")

    def mail_perm(*keys):
        return permission_required(*keys)

    # ── Dashboard ──────────────────────────────────────────────
    @bp.route("/dashboard", methods=["GET"])
    @mail_perm(*MAIL_DASH)
    def dashboard():
        with closing(get_db()) as conn:
            contacts = scalar(conn, "SELECT COUNT(*) FROM mail_contacts") or 0
            active_contacts = scalar(
                conn, "SELECT COUNT(*) FROM mail_contacts WHERE unsubscribed = 0"
            ) or 0
            templates = scalar(conn, "SELECT COUNT(*) FROM mail_templates") or 0
            campaigns = scalar(conn, "SELECT COUNT(*) FROM mail_campaigns") or 0
            sends_total = scalar(conn, "SELECT COUNT(*) FROM mail_sends") or 0
            sends_sim = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status IN ('simulated','sent')"
            ) or 0
            sends_queued = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status = 'queued'"
            ) or 0
            sends_failed = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status = 'failed'"
            ) or 0
            opened = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE opened_at IS NOT NULL"
            ) or 0
            clicked = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE clicked_at IS NOT NULL"
            ) or 0
            ivr_events = scalar(conn, "SELECT COUNT(*) FROM mail_ivr_events") or 0
            domains = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
            provider = get_mail_setting(conn, "provider_mode", "stub")
        return jsonify({
            "kpi": {
                "contacts": contacts,
                "active_contacts": active_contacts,
                "templates": templates,
                "campaigns": campaigns,
                "sends_total": sends_total,
                "sends_delivered": sends_sim,
                "sends_queued": sends_queued,
                "sends_failed": sends_failed,
                "opened": opened,
                "clicked": clicked,
                "ivr_events": ivr_events,
            },
            "domains": domains,
            "provider_mode": provider,
            "note": "Gönderim şu an stub modunda; Alibaba DirectMail bağlanınca gerçek iletime geçer.",
        })

    # ── Contacts / CRM ─────────────────────────────────────────
    @bp.route("/contacts/stats", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def contact_stats():
        """CRM özet sayaçları: toplam kontak, en az 1 kez mail atılmış, hiç mail atılmamış."""
        with closing(get_db()) as conn:
            total = scalar(conn, "SELECT COUNT(*) FROM mail_contacts") or 0
            mailed = scalar(
                conn,
                """
                SELECT COUNT(*) FROM mail_contacts c
                WHERE EXISTS (SELECT 1 FROM mail_sends s WHERE s.contact_id = c.id)
                """,
            ) or 0
            never_mailed = max(total - mailed, 0)
        return jsonify({
            "total": total,
            "mailed": mailed,
            "never_mailed": never_mailed,
        })

    @bp.route("/contacts", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def list_contacts():
        q = (request.args.get("q") or "").strip().lower()
        tag = (request.args.get("tag") or "").strip()
        limit = min(int(request.args.get("limit") or 200), 1000)
        with closing(get_db()) as conn:
            rows = _rows(fetchall(
                conn,
                "SELECT * FROM mail_contacts ORDER BY id DESC LIMIT ?",
                (limit,),
            ))
        out = []
        for r in rows:
            c = _contact_out(r)
            if q:
                blob = f"{c.get('email','')} {c.get('name','')} {c.get('phone','')}".lower()
                if q not in blob:
                    continue
            if tag and tag not in (c.get("tags") or []):
                continue
            out.append(c)
        return jsonify({"contacts": out, "count": len(out)})

    @bp.route("/contacts", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def create_contact():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email or not EMAIL_RE.match(email):
            return jsonify({"error": "Geçerli bir e-posta girin."}), 400
        now = iso(utcnow())
        tags = _tags_json(data.get("tags"))
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT id FROM mail_contacts WHERE LOWER(email) = ?", (email,))
            if existing:
                return jsonify({"error": "Bu e-posta zaten kayıtlı.", "id": existing["id"]}), 409
            cid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_contacts
                (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    (data.get("phone") or "").strip(),
                    (data.get("name") or "").strip(),
                    tags,
                    (data.get("source") or "manual").strip() or "manual",
                    1 if data.get("unsubscribed") else 0,
                    (data.get("notes") or "").strip(),
                    now,
                    now,
                ),
            )
            for t in _parse_tags(data.get("tags")):
                _ensure_tag(conn, t, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (cid,))
        return jsonify({"contact": _contact_out(row)}), 201

    @bp.route("/contacts/<int:contact_id>", methods=["PATCH"])
    @mail_perm(*MAIL_CRM)
    def update_contact(contact_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
            if not row:
                return jsonify({"error": "Kontak bulunamadı."}), 404
            email = (data.get("email") if "email" in data else row["email"] or "").strip().lower()
            if not email or not EMAIL_RE.match(email):
                return jsonify({"error": "Geçerli bir e-posta girin."}), 400
            tags = _tags_json(data.get("tags")) if "tags" in data else row["tags"]
            execute(
                conn,
                """
                UPDATE mail_contacts SET
                    email = ?, phone = ?, name = ?, tags = ?, source = ?,
                    unsubscribed = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    email,
                    (data.get("phone") if "phone" in data else row["phone"] or "").strip(),
                    (data.get("name") if "name" in data else row["name"] or "").strip(),
                    tags,
                    (data.get("source") if "source" in data else row["source"] or "manual").strip(),
                    1 if data.get("unsubscribed", row["unsubscribed"]) else 0,
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    now,
                    contact_id,
                ),
            )
            if "tags" in data:
                for t in _parse_tags(data.get("tags")):
                    _ensure_tag(conn, t, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
        return jsonify({"contact": _contact_out(row)})

    @bp.route("/contacts/<int:contact_id>", methods=["DELETE"])
    @mail_perm(*MAIL_CRM)
    def delete_contact(contact_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_contacts WHERE id = ?", (contact_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/contacts/import", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def import_contacts():
        data = request.get_json(silent=True) or {}
        raw_csv = data.get("csv") or ""
        default_tag = (data.get("tag") or "").strip()
        if not raw_csv.strip():
            return jsonify({"error": "CSV içeriği boş."}), 400
        reader = csv.DictReader(io.StringIO(raw_csv))
        now = iso(utcnow())
        created = 0
        updated = 0
        skipped = 0
        with closing(get_db()) as conn:
            for row in reader:
                email = (row.get("email") or row.get("Email") or row.get("EMAIL") or "").strip().lower()
                if not email or not EMAIL_RE.match(email):
                    skipped += 1
                    continue
                name = (row.get("name") or row.get("Name") or "").strip()
                phone = (row.get("phone") or row.get("Phone") or row.get("tel") or "").strip()
                tags = _parse_tags(row.get("tags") or row.get("tag") or "")
                if default_tag and default_tag not in tags:
                    tags.append(default_tag)
                existing = fetchone(conn, "SELECT id, tags FROM mail_contacts WHERE LOWER(email) = ?", (email,))
                if existing:
                    merged = list(dict.fromkeys(_parse_tags(existing["tags"]) + tags))
                    execute(
                        conn,
                        """
                        UPDATE mail_contacts SET name = COALESCE(NULLIF(?, ''), name),
                            phone = COALESCE(NULLIF(?, ''), phone),
                            tags = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (name, phone, _tags_json(merged), now, existing["id"]),
                    )
                    updated += 1
                else:
                    insert_returning_id(
                        conn,
                        """
                        INSERT INTO mail_contacts
                        (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 0, '', ?, ?)
                        """,
                        (email, phone, name, _tags_json(tags), "csv", now, now),
                    )
                    created += 1
                for t in tags:
                    _ensure_tag(conn, t, now)
            conn.commit()
        return jsonify({"created": created, "updated": updated, "skipped": skipped})

    @bp.route("/contacts/import/start", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def start_import_job():
        """Büyük liste (yüz binler / milyonlar) için dosya yükleyip arka planda işler."""
        file = request.files.get("file")
        if not file or not file.filename:
            return jsonify({"error": "CSV veya XLSX dosyası seç."}), 400
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in (".csv", ".xlsx", ".xlsm"):
            return jsonify({"error": "Sadece .csv veya .xlsx dosyası yükleyebilirsin."}), 400
        if request.content_length and request.content_length > 800 * 1024 * 1024:
            return jsonify({"error": "Dosya çok büyük (800MB üstü). Bölüp tekrar dene."}), 400
        tag = (request.form.get("tag") or "").strip()
        _ensure_import_dir()
        now = iso(utcnow())
        with closing(get_db()) as conn:
            job_id = insert_returning_id(
                conn,
                """
                INSERT INTO mail_import_jobs
                (filename, tag, status, total_rows, processed_rows, upserted_count, skipped_count, error, created_at, updated_at)
                VALUES (?, ?, 'pending', 0, 0, 0, 0, '', ?, ?)
                """,
                (file.filename, tag, now, now),
            )
            conn.commit()
        path = os.path.join(IMPORT_DIR, f"job_{job_id}{ext}")
        file.save(path)
        threading.Thread(target=_run_import_job, args=(job_id, path, tag), daemon=True).start()
        return jsonify({"job_id": job_id, "status": "pending"}), 202

    @bp.route("/contacts/import/status/<int:job_id>", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def import_job_status(job_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_import_jobs WHERE id = ?", (job_id,))
        if not row:
            return jsonify({"error": "İş bulunamadı."}), 404
        return jsonify({"job": _row(row)})

    @bp.route("/contacts/import/jobs", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def list_import_jobs():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_import_jobs ORDER BY id DESC LIMIT 20"))
        return jsonify({"jobs": rows})

    @bp.route("/contacts/import/cancel/<int:job_id>", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def cancel_import_job(job_id):
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT status FROM mail_import_jobs WHERE id = ?", (job_id,))
            if not row:
                return jsonify({"error": "İş bulunamadı."}), 404
            status = row["status"]
            if status in ("done", "error", "cancelled", "cancelling"):
                return jsonify({"error": f"İş zaten sonlanmış ya da iptal ediliyor ({status})."}), 400
            execute(
                conn,
                "UPDATE mail_import_jobs SET status = 'cancelling', updated_at = ? WHERE id = ?",
                (iso(utcnow()), job_id),
            )
            conn.commit()
        return jsonify({"ok": True, "status": "cancelling"})

    @bp.route("/tags", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def list_tags():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_contact_tags ORDER BY name ASC"))
        return jsonify({"tags": rows})

    @bp.route("/crm/sync-smartico", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def sync_smartico_segments():
        """Smartico'daki kayıt/FTD verisini afp1 (sub-id) üzerinden contact_id'ye
        eşleştirip CRM'i otomatik etiketler: uye_oldu / ftd_yapti / ftd_yok.
        """
        now = iso(utcnow())
        with closing(get_db()) as conn:
            affiliate_id = (get_mail_setting(conn, "smartico_affiliate_id", "") or "").strip()
            subid_param = (get_mail_setting(conn, "smartico_subid_param", "afp1") or "afp1").strip() or "afp1"
            if not affiliate_id:
                return jsonify({"error": "Önce Ayarlar'dan Smartico Affiliate ID gir."}), 400
            if not smartico_api.is_configured(conn):
                return jsonify({"error": "Smartico API anahtarı tanımlı değil (Link Takip > Smartico)."}), 400

            result = smartico_api.fetch_subid_conversions(conn, affiliate_id, subid_param)
            if result.get("error"):
                return jsonify({"error": result["error"]}), 400

            matched = 0
            unmatched = 0
            tagged_uye = 0
            tagged_ftd = 0
            tagged_no_ftd = 0
            for row in result["rows"]:
                subid = row.get("subid") or ""
                try:
                    contact_id = int(subid)
                except (TypeError, ValueError):
                    unmatched += 1
                    continue
                contact = fetchone(conn, "SELECT id FROM mail_contacts WHERE id = ?", (contact_id,))
                if not contact:
                    unmatched += 1
                    continue
                matched += 1
                if row.get("registration_count", 0) > 0:
                    _tag_contact(conn, contact_id, "uye_oldu", now)
                    tagged_uye += 1
                    if row.get("ftd_count", 0) > 0:
                        _tag_contact(conn, contact_id, "ftd_yapti", now)
                        _untag_contact(conn, contact_id, "ftd_yok", now)
                        tagged_ftd += 1
                    else:
                        _tag_contact(conn, contact_id, "ftd_yok", now)
                        tagged_no_ftd += 1
            conn.commit()
        return jsonify({
            "ok": True,
            "matched": matched,
            "unmatched": unmatched,
            "tagged_uye_oldu": tagged_uye,
            "tagged_ftd_yapti": tagged_ftd,
            "tagged_ftd_yok": tagged_no_ftd,
            "message": f"{matched} contact eşleşti · {tagged_uye} üye oldu · {tagged_ftd} FTD yaptı · {tagged_no_ftd} FTD yok",
        })

    @bp.route("/tags", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def create_tag():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Etiket adı gerekli."}), 400
        now = iso(utcnow())
        with closing(get_db()) as conn:
            _ensure_tag(conn, name, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contact_tags WHERE name = ?", (name,))
        return jsonify({"tag": _row(row)}), 201

    # ── Templates ──────────────────────────────────────────────
    @bp.route("/templates", methods=["GET"])
    @mail_perm(*MAIL_TPL)
    def list_templates():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_templates ORDER BY id DESC"))
        return jsonify({"templates": rows})

    @bp.route("/templates", methods=["POST"])
    @mail_perm(*MAIL_TPL)
    def create_template():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Şablon adı gerekli."}), 400
        now = iso(utcnow())
        text_body = data.get("text_body") or ""
        html_body = data.get("html_body") or ""
        if not html_body.strip() and text_body.strip():
            html_body = _plain_to_html(text_body)
        with closing(get_db()) as conn:
            tid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    (data.get("subject") or "").strip(),
                    html_body,
                    text_body,
                    now,
                    now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (tid,))
        return jsonify({"template": _row(row)}), 201

    @bp.route("/templates/<int:template_id>", methods=["PATCH"])
    @mail_perm(*MAIL_TPL)
    def update_template(template_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (template_id,))
            if not row:
                return jsonify({"error": "Şablon bulunamadı."}), 404
            text_body = data.get("text_body") if "text_body" in data else row["text_body"] or ""
            html_body = data.get("html_body") if "html_body" in data else row["html_body"] or ""
            # Basit yazı kaydı: html boşsa veya sync_html istenirse üret
            if data.get("sync_html_from_text") or (not (html_body or "").strip() and (text_body or "").strip()):
                html_body = _plain_to_html(text_body)
            execute(
                conn,
                """
                UPDATE mail_templates SET name = ?, subject = ?, html_body = ?, text_body = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"]).strip(),
                    (data.get("subject") if "subject" in data else row["subject"] or "").strip(),
                    html_body,
                    text_body,
                    now,
                    template_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (template_id,))
        return jsonify({"template": _row(row)})

    @bp.route("/templates/<int:template_id>/test-send", methods=["POST"])
    @mail_perm(*MAIL_TPL)
    def test_send_template(template_id):
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email or not EMAIL_RE.match(email):
            return jsonify({"error": "Geçerli test e-postası girin."}), 400
        domain_id = data.get("domain_id")
        with closing(get_db()) as conn:
            tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (template_id,))
            if not tpl:
                return jsonify({"error": "Şablon bulunamadı."}), 404
            if not domain_id:
                raw = get_mail_setting(conn, "default_domain_id", "") or ""
                try:
                    domain_id = int(raw) if raw else None
                except ValueError:
                    domain_id = None
            if not domain_id:
                first = fetchone(conn, "SELECT id FROM mail_domains ORDER BY id ASC LIMIT 1")
                domain_id = first["id"] if first else None
            contact = {"name": data.get("name") or "Test", "email": email, "phone": ""}
            # Upsert test contact lightly
            existing = fetchone(conn, "SELECT id FROM mail_contacts WHERE LOWER(email) = ?", (email,))
            now = iso(utcnow())
            if existing:
                contact_id = existing["id"]
            else:
                contact_id = insert_returning_id(
                    conn,
                    """
                    INSERT INTO mail_contacts
                    (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                    VALUES (?, '', ?, ?, 'test', 0, '', ?, ?)
                    """,
                    (email, contact["name"], _tags_json(["test"]), now, now),
                )
            subject = _render_template(tpl["subject"], contact)
            html_body = _render_template(tpl["html_body"] or _plain_to_html(tpl["text_body"] or ""), contact)
            text_body = _render_template(tpl["text_body"] or "", contact)
            send_id, status = _stub_send(
                conn,
                channel="test",
                to_email=email,
                subject=subject,
                contact=contact,
                contact_id=contact_id,
                template_id=template_id,
                domain_id=domain_id,
                html_body=html_body,
                text_body=text_body,
            )
            links = _rows(fetchall(
                conn,
                "SELECT token, dest_url FROM mail_click_links WHERE send_id = ?",
                (send_id,),
            ))
            for L in links:
                L["track_url"] = _track_url(L["token"])
            conn.commit()
        return jsonify({
            "ok": True,
            "send_id": send_id,
            "status": status,
            "mode": "stub",
            "tracked_links": links,
            "message": "Test gönderim kaydı oluşturuldu (stub). Takip linkleri hazır; Alibaba bağlanınca gerçek mail gider.",
        })

    @bp.route("/templates/<int:template_id>", methods=["DELETE"])
    @mail_perm(*MAIL_TPL)
    def delete_template(template_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_templates WHERE id = ?", (template_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Campaigns ──────────────────────────────────────────────
    @bp.route("/campaigns", methods=["GET"])
    @mail_perm(*MAIL_CAMP)
    def list_campaigns():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_campaigns ORDER BY id DESC"))
            for r in rows:
                r["recipient_count"] = scalar(
                    conn,
                    "SELECT COUNT(*) FROM mail_campaign_recipients WHERE campaign_id = ?",
                    (r["id"],),
                ) or 0
        return jsonify({"campaigns": rows})

    @bp.route("/campaigns", methods=["POST"])
    @mail_perm(*MAIL_CAMP)
    def create_campaign():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Kampanya adı gerekli."}), 400
        template_id = data.get("template_id")
        domain_id = data.get("domain_id")
        if not template_id:
            return jsonify({"error": "Şablon seçin."}), 400
        if not domain_id:
            return jsonify({"error": "Domain seçin."}), 400
        now = iso(utcnow())
        tag_filter = (data.get("tag_filter") or "").strip()
        max_recipients = data.get("max_recipients")
        try:
            max_recipients = int(max_recipients)
            if max_recipients <= 0:
                max_recipients = None
        except (TypeError, ValueError):
            max_recipients = None
        exclude_sent = data.get("exclude_previously_sent")
        exclude_sent = True if exclude_sent is None else bool(exclude_sent)
        with closing(get_db()) as conn:
            if not fetchone(conn, "SELECT id FROM mail_templates WHERE id = ?", (template_id,)):
                return jsonify({"error": "Şablon bulunamadı."}), 404
            if not fetchone(conn, "SELECT id FROM mail_domains WHERE id = ?", (domain_id,)):
                return jsonify({"error": "Domain bulunamadı."}), 404
            cid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_campaigns
                (name, campaign_type, template_id, domain_id, status, tag_filter, notes, created_at, updated_at)
                VALUES (?, 'bulk', ?, ?, 'draft', ?, ?, ?, ?)
                """,
                (name, template_id, domain_id, tag_filter, (data.get("notes") or "").strip(), now, now),
            )
            attached = _attach_campaign_recipients(
                conn, cid, tag_filter=tag_filter, max_recipients=max_recipients,
                exclude_previously_sent=exclude_sent, now=now,
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (cid,))
            out = _row(row)
            out["recipient_count"] = attached
        return jsonify({"campaign": out}), 201

    @bp.route("/campaigns/select-preview", methods=["POST"])
    @mail_perm(*MAIL_CAMP)
    def preview_campaign_selection():
        """Kampanya oluşturmadan önce filtreye kaç kişinin denk geldiğini gösterir."""
        data = request.get_json(silent=True) or {}
        tag_filter = (data.get("tag_filter") or "").strip()
        exclude_sent = data.get("exclude_previously_sent")
        exclude_sent = True if exclude_sent is None else bool(exclude_sent)
        with closing(get_db()) as conn:
            where_sql, params = _campaign_selection_where(tag_filter, exclude_sent)
            total = scalar(conn, f"SELECT COUNT(*) FROM mail_contacts WHERE {where_sql}", tuple(params)) or 0
        return jsonify({"matching_count": total})

    @bp.route("/campaigns/<int:campaign_id>", methods=["PATCH"])
    @mail_perm(*MAIL_CAMP)
    def update_campaign(campaign_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
            if not row:
                return jsonify({"error": "Kampanya bulunamadı."}), 404
            if row["status"] not in ("draft",):
                return jsonify({"error": "Sadece taslak kampanyalar düzenlenebilir."}), 400
            execute(
                conn,
                """
                UPDATE mail_campaigns SET name = ?, template_id = ?, domain_id = ?,
                    tag_filter = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"]).strip(),
                    data.get("template_id") if "template_id" in data else row["template_id"],
                    data.get("domain_id") if "domain_id" in data else row["domain_id"],
                    (data.get("tag_filter") if "tag_filter" in data else row["tag_filter"] or "").strip(),
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    now,
                    campaign_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
        return jsonify({"campaign": _row(row)})

    @bp.route("/campaigns/<int:campaign_id>", methods=["DELETE"])
    @mail_perm(*MAIL_CAMP)
    def delete_campaign(campaign_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_campaign_recipients WHERE campaign_id = ?", (campaign_id,))
            execute(conn, "DELETE FROM mail_campaigns WHERE id = ?", (campaign_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/campaigns/<int:campaign_id>/queue", methods=["POST"])
    @mail_perm(*MAIL_CAMP)
    def queue_campaign(campaign_id):
        now = iso(utcnow())
        with closing(get_db()) as conn:
            camp = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
            if not camp:
                return jsonify({"error": "Kampanya bulunamadı."}), 404
            if camp["status"] not in ("draft", "queued"):
                return jsonify({"error": f"Kampanya durumu uygun değil: {camp['status']}"}), 400
            tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (camp["template_id"],))
            if not tpl:
                return jsonify({"error": "Şablon bulunamadı."}), 400
            recipients = _rows(fetchall(
                conn,
                """
                SELECT r.id AS recipient_id, r.contact_id, c.email, c.phone, c.name, c.tags
                FROM mail_campaign_recipients r
                JOIN mail_contacts c ON c.id = r.contact_id
                WHERE r.campaign_id = ? AND r.status = 'pending' AND c.unsubscribed = 0
                """,
                (campaign_id,),
            ))
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'sending', queued_at = ?, updated_at = ? WHERE id = ?",
                (now, now, campaign_id),
            )
            sent = 0
            for rec in recipients:
                contact = {
                    "name": rec.get("name") or "",
                    "email": rec.get("email") or "",
                    "phone": rec.get("phone") or "",
                }
                subject = _render_template(tpl["subject"], contact)
                html_body = _render_template(
                    tpl["html_body"] or _plain_to_html(tpl["text_body"] or ""), contact
                )
                text_body = _render_template(tpl["text_body"] or "", contact)
                send_id, status = _stub_send(
                    conn,
                    channel="bulk",
                    to_email=rec["email"],
                    subject=subject,
                    contact=contact,
                    campaign_id=campaign_id,
                    contact_id=rec["contact_id"],
                    template_id=camp["template_id"],
                    domain_id=camp["domain_id"],
                    to_phone=rec.get("phone") or "",
                    html_body=html_body,
                    text_body=text_body,
                )
                execute(
                    conn,
                    "UPDATE mail_campaign_recipients SET status = ?, send_id = ? WHERE id = ?",
                    (status, send_id, rec["recipient_id"]),
                )
                sent += 1
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'done', finished_at = ?, updated_at = ? WHERE id = ?",
                (now, now, campaign_id),
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "queued": sent,
            "mode": "stub",
            "message": f"{sent} alıcı için stub gönderim kaydı oluşturuldu. Alibaba bağlanınca gerçek iletim aktif olur.",
        })

    # ── Sends / Reports ────────────────────────────────────────
    @bp.route("/sends", methods=["GET"])
    @mail_perm(*MAIL_REP)
    def list_sends():
        status = (request.args.get("status") or "").strip()
        channel = (request.args.get("channel") or "").strip()
        limit = min(int(request.args.get("limit") or 200), 1000)
        with closing(get_db()) as conn:
            sql = "SELECT * FROM mail_sends WHERE 1=1"
            params = []
            if status:
                sql += " AND status = ?"
                params.append(status)
            if channel:
                sql += " AND channel = ?"
                params.append(channel)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = _rows(fetchall(conn, sql, tuple(params)))
        return jsonify({"sends": rows, "count": len(rows)})

    @bp.route("/reports/summary", methods=["GET"])
    @mail_perm(*MAIL_REP)
    def reports_summary():
        with closing(get_db()) as conn:
            by_status = _rows(fetchall(
                conn,
                "SELECT status, COUNT(*) AS cnt FROM mail_sends GROUP BY status ORDER BY cnt DESC",
            ))
            by_channel = _rows(fetchall(
                conn,
                "SELECT channel, COUNT(*) AS cnt FROM mail_sends GROUP BY channel ORDER BY cnt DESC",
            ))
            recent = _rows(fetchall(
                conn,
                "SELECT * FROM mail_sends ORDER BY id DESC LIMIT 20",
            ))
        return jsonify({
            "by_status": by_status,
            "by_channel": by_channel,
            "recent": recent,
        })

    # ── Domains / Settings ─────────────────────────────────────
    @bp.route("/domains", methods=["GET"])
    @mail_perm(*MAIL_SET)
    def list_domains():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
        return jsonify({"domains": rows})

    @bp.route("/domains/<int:domain_id>", methods=["PATCH"])
    @mail_perm(*MAIL_SET)
    def update_domain(domain_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
            if not row:
                return jsonify({"error": "Domain bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE mail_domains SET
                    from_name = ?, from_local = ?, status = ?, dns_status = ?, notes = ?
                WHERE id = ?
                """,
                (
                    (data.get("from_name") if "from_name" in data else row["from_name"] or "").strip(),
                    (data.get("from_local") if "from_local" in data else row["from_local"] or "noreply").strip(),
                    (data.get("status") if "status" in data else row["status"] or "pending").strip(),
                    (data.get("dns_status") if "dns_status" in data else row["dns_status"] or "unconfigured").strip(),
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    domain_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
        return jsonify({"domain": _row(row)})

    @bp.route("/settings", methods=["GET"])
    @mail_perm(*MAIL_SET)
    def get_settings():
        keys = (
            "provider_mode", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
            "webhook_secret", "default_domain_id",
            "smartico_affiliate_id", "smartico_subid_param",
        )
        with closing(get_db()) as conn:
            settings = {k: get_mail_setting(conn, k, "") or "" for k in keys}
            # Mask password
            pw = settings.get("smtp_password") or ""
            settings["smtp_password_set"] = bool(pw)
            settings["smtp_password"] = ""
            settings["webhook_secret_masked"] = _mask_secret(settings.get("webhook_secret") or "")
            domains = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
        return jsonify({"settings": settings, "domains": domains})

    @bp.route("/settings", methods=["PATCH"])
    @mail_perm(*MAIL_SET)
    def patch_settings():
        data = request.get_json(silent=True) or {}
        allowed = {
            "provider_mode", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
            "webhook_secret", "default_domain_id",
            "smartico_affiliate_id", "smartico_subid_param",
        }
        with closing(get_db()) as conn:
            if data.get("rotate_webhook_secret"):
                upsert_mail_setting(conn, "webhook_secret", secrets.token_hex(24))
            for key, val in data.items():
                if key not in allowed:
                    continue
                if key == "smtp_password" and (val is None or val == ""):
                    continue  # empty = keep existing
                upsert_mail_setting(conn, key, "" if val is None else str(val).strip())
            conn.commit()
            settings = {k: get_mail_setting(conn, k, "") or "" for k in allowed}
            pw = settings.get("smtp_password") or ""
            settings["smtp_password_set"] = bool(pw)
            settings["smtp_password"] = ""
            settings["webhook_secret_masked"] = _mask_secret(settings.get("webhook_secret") or "")
        return jsonify({"settings": settings})

    def _mask_secret(s):
        if not s:
            return ""
        if len(s) <= 8:
            return "•" * len(s)
        return s[:4] + "•" * (len(s) - 8) + s[-4:]

    # ── IVR ────────────────────────────────────────────────────
    @bp.route("/ivr/rules", methods=["GET"])
    @mail_perm(*MAIL_IVR)
    def get_ivr_rules():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_ivr_rules ORDER BY id ASC"))
        return jsonify({"rules": rows})

    @bp.route("/ivr/rules/<int:rule_id>", methods=["PATCH"])
    @mail_perm(*MAIL_IVR)
    def patch_ivr_rule(rule_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_ivr_rules WHERE id = ?", (rule_id,))
            if not row:
                return jsonify({"error": "Kural bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE mail_ivr_rules SET name = ?, active = ?, template_id = ?,
                    domain_id = ?, delay_seconds = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"] or "").strip(),
                    1 if data.get("active", row["active"]) else 0,
                    data.get("template_id") if "template_id" in data else row["template_id"],
                    data.get("domain_id") if "domain_id" in data else row["domain_id"],
                    int(data.get("delay_seconds") if "delay_seconds" in data else row["delay_seconds"] or 0),
                    rule_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_ivr_rules WHERE id = ?", (rule_id,))
        return jsonify({"rule": _row(row)})

    @bp.route("/ivr/events", methods=["GET"])
    @mail_perm(*MAIL_IVR)
    def list_ivr_events():
        limit = min(int(request.args.get("limit") or 100), 500)
        with closing(get_db()) as conn:
            rows = _rows(fetchall(
                conn,
                "SELECT * FROM mail_ivr_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ))
        return jsonify({"events": rows})

    @bp.route("/webhooks/ivr", methods=["POST"])
    def ivr_webhook():
        """Harici IVR santralinden çağrı cevabı bildirimi.
        Auth: X-Mailing-Webhook-Secret header veya ?secret= query.
        Body JSON: { phone, email?, answered_at?, name? }
        """
        data = request.get_json(silent=True) or {}
        secret = (
            request.headers.get("X-Mailing-Webhook-Secret")
            or request.args.get("secret")
            or ""
        ).strip()
        now = iso(utcnow())
        with closing(get_db()) as conn:
            expected = (get_mail_setting(conn, "webhook_secret", "") or "").strip()
            if not expected or secret != expected:
                return jsonify({"error": "Unauthorized"}), 401

            phone = (data.get("phone") or data.get("tel") or "").strip()
            email = (data.get("email") or "").strip().lower()
            answered_at = (data.get("answered_at") or now).strip()
            name = (data.get("name") or "").strip()

            event_id = insert_returning_id(
                conn,
                """
                INSERT INTO mail_ivr_events
                (phone, email, answered_at, contact_id, send_id, status, payload, error, created_at)
                VALUES (?, ?, ?, NULL, NULL, 'received', ?, '', ?)
                """,
                (phone, email, answered_at, json.dumps(data, ensure_ascii=False), now),
            )

            rule = fetchone(
                conn,
                "SELECT * FROM mail_ivr_rules WHERE active = 1 ORDER BY id ASC LIMIT 1",
            )
            if not rule:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("skipped", "Aktif IVR kuralı yok", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "skipped", "reason": "no_active_rule"})

            if not rule["template_id"] or not rule["domain_id"]:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("skipped", "IVR kuralında şablon/domain eksik", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "skipped", "reason": "rule_incomplete"})

            # Match contact by phone or email
            contact = None
            if phone:
                contact = fetchone(
                    conn,
                    "SELECT * FROM mail_contacts WHERE phone != '' AND phone = ? LIMIT 1",
                    (phone,),
                )
            if not contact and email:
                contact = fetchone(
                    conn,
                    "SELECT * FROM mail_contacts WHERE LOWER(email) = ? LIMIT 1",
                    (email,),
                )
            # Auto-create contact if email provided
            if not contact and email and EMAIL_RE.match(email):
                cid = insert_returning_id(
                    conn,
                    """
                    INSERT INTO mail_contacts
                    (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'ivr', 0, '', ?, ?)
                    """,
                    (email, phone, name, _tags_json(["ivr"]), now, now),
                )
                contact = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (cid,))

            contact = _row(contact) if contact else None

            if not contact or not contact.get("email"):
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("no_contact", "Eşleşen kontak/e-posta yok", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "no_contact"})

            if contact.get("unsubscribed"):
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, contact_id = ?, error = ? WHERE id = ?",
                    ("unsubscribed", contact["id"], "Kontak abonelikten çıkmış", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "unsubscribed"})

            tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (rule["template_id"],))
            if not tpl:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, contact_id = ?, error = ? WHERE id = ?",
                    ("error", contact["id"], "Şablon bulunamadı", event_id),
                )
                conn.commit()
                return jsonify({"ok": False, "event_id": event_id, "status": "error"}), 400

            contact_d = _contact_out(contact)
            subject = _render_template(tpl["subject"], contact_d)
            send_id, status = _stub_send(
                conn,
                channel="ivr",
                to_email=contact_d["email"],
                subject=subject,
                contact=contact_d,
                contact_id=contact_d["id"],
                template_id=rule["template_id"],
                domain_id=rule["domain_id"],
                to_phone=phone or contact_d.get("phone") or "",
            )
            execute(
                conn,
                "UPDATE mail_ivr_events SET status = ?, contact_id = ?, send_id = ? WHERE id = ?",
                (status, contact_d["id"], send_id, event_id),
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "event_id": event_id,
            "send_id": send_id,
            "status": status,
            "mode": "stub",
        })

    return bp
