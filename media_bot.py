"""Telegram medya botu.

Ortam:
  MEDIA_BOT_TOKEN   BotFather tokeni. Ziyaretçi alarm botundan ayrı olsun.
  GEMINI_API_KEY    Google AI Studio anahtarı.
  MEDIA_BOT_ENABLED 1 ise panel ayağa kalkınca bu bot da başlar.

Tek başına: python media_bot.py
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO

from media_brands import BRANDS, CATEGORIES, FORMATS, logo_reference, mascot_reference
from media_flow import (
    banner_motion_prompt,
    banner_prompt,
    campaign_prompt,
    new_session,
    ready_caption,
    revise_prompt,
    sticker_prompt,
    video_aspect,
    video_prompt,
    welcome_text,
)
from media_gemini import GeminiError, generate_image, generate_video

TOKEN_ENV = "MEDIA_BOT_TOKEN"


class MediaBot:
    def __init__(self, token):
        self.token = token
        self.offset = None
        self.sessions = {}
        self.username = ""
        self.sticker_sets = {}
        self.busy = set()

    def run(self):
        me = self._api("getMe")
        self.username = (me.get("result") or {}).get("username") or ""
        print(f"media bot @{self.username} dinliyor")
        self._skip_backlog()
        while True:
            try:
                updates = self._api("getUpdates", {"timeout": 25, "offset": self.offset}, timeout=35)
            except Exception as exc:
                print(f"media bot getUpdates: {exc}")
                time.sleep(3)
                continue
            for update in updates.get("result") or []:
                self.offset = update["update_id"] + 1
                try:
                    self._on_update(update)
                except Exception as exc:
                    print(f"media bot update: {exc}")
                    chat_id = _chat_id(update)
                    if chat_id:
                        try:
                            self._send(chat_id, f"İşlem yarıda kaldı: {exc}")
                        except Exception:
                            pass

    def _skip_backlog(self):
        try:
            updates = self._api("getUpdates", {"timeout": 0, "offset": self.offset}, timeout=15)
        except Exception:
            return
        result = updates.get("result") or []
        if result:
            self.offset = result[-1]["update_id"] + 1

    def _session(self, chat_id):
        session = self.sessions.get(chat_id)
        if session is None:
            session = new_session()
            self.sessions[chat_id] = session
        return session

    def _on_update(self, update):
        if "callback_query" in update:
            self._on_callback(update["callback_query"])
            return
        message = update.get("message") or {}
        text = (message.get("text") or "").strip()
        chat = message.get("chat") or {}
        if not chat.get("id"):
            return
        user_id = (message.get("from") or {}).get("id")
        if user_id:
            self._session(chat["id"])["user_id"] = user_id
        if text.startswith("/start") or text.startswith("/marka"):
            self._show_brands(chat["id"])
            return
        if text:
            self._on_text(chat["id"], text)

    def _on_callback(self, query):
        data = query.get("data") or ""
        message = query.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        self._api("answerCallbackQuery", {"callback_query_id": query.get("id")})
        if not chat_id:
            return
        user_id = (query.get("from") or {}).get("id")
        session = self._session(chat_id)
        if user_id:
            session["user_id"] = user_id
        if data.startswith("b:"):
            key = data[2:]
            if key not in BRANDS:
                return
            session.clear()
            session.update(new_session())
            session["brand"] = key
            session["user_id"] = user_id
            session["step"] = "menu"
            self._show_menu(chat_id)
            return
        if data == "a:home":
            self._show_brands(chat_id)
            return
        if data == "m:img":
            session["mode"] = "image"
            session["step"] = "format"
            self._show_formats(chat_id)
            return
        if data == "m:vid":
            session["mode"] = "video"
            session["step"] = "format"
            self._show_formats(chat_id)
            return
        if data == "m:gif":
            session["mode"] = "gif"
            session["step"] = "format"
            self._show_formats(chat_id)
            return
        if data == "m:stk":
            session["mode"] = "sticker"
            session["step"] = "format"
            self._show_formats(chat_id)
            return
        if data.startswith("f:"):
            key = data[2:]
            if key not in FORMATS:
                return
            session["fmt"] = key
            if session.get("mode") == "sticker":
                session["step"] = "sticker_kind"
                self._show_sticker_kinds(chat_id)
            else:
                session["step"] = "category"
                self._show_categories(chat_id)
            return
        if data.startswith("c:"):
            key = data[2:]
            if key not in CATEGORIES:
                return
            session["category"] = key
            session["step"] = "campaign"
            self._send(chat_id, self._campaign_help(session))
            return
        if data == "a:new":
            session["step"] = "campaign"
            self._send(chat_id, "Yeni kampanya metnini yaz.")
            return
        if data == "a:rev":
            session["step"] = "revise"
            self._send(
                chat_id,
                "Sadece değişecek kısmı yaz.\nÖrnek: %100 yerine %500 yaz, butonu sarı yap.",
            )
            return
        if data == "a:vid":
            self._animate(chat_id, session)
            return
        if data == "a:hd":
            self._send_hd(chat_id, session)
            return
        if data == "a:stk":
            session["mode"] = "sticker"
            session["step"] = "format"
            self._show_formats(chat_id)
            return
        if data.startswith("s:"):
            self._on_sticker_callback(chat_id, session, data[2:])

    def _on_text(self, chat_id, text):
        session = self._session(chat_id)
        step = session.get("step")
        if step == "campaign":
            session["campaign"] = text
            mode = session.get("mode")
            if mode == "video":
                self._make_clip(chat_id, session, "video")
            elif mode == "gif":
                self._make_clip(chat_id, session, "gif")
            else:
                self._make_image(chat_id, session, campaign_prompt(session), revise=False)
            return
        if step == "revise":
            self._make_image(chat_id, session, revise_prompt(session, text), revise=True)
            return
        if step == "game":
            session["game"] = text
            session["step"] = "slogan_choice"
            self._ask_slogan(chat_id)
            return
        if step == "slogan":
            session["slogan"] = text
            session["step"] = "character"
            self._send(chat_id, "Karakteri bir cümleyle yaz. Örnek: elinde tahta tabela tutan balıkçı.")
            return
        if step == "character":
            session["character"] = text
            self._make_sticker(chat_id, session)
            return
        if step == "sticker_ready":
            self._send(chat_id, "Kaydetmek için Onayla ve kaydet’e bas, ya da İptal.")
            return
        self._show_brands(chat_id)

    def _on_sticker_callback(self, chat_id, session, action):
        if action == "mascot":
            session["sticker_kind"] = "mascot"
            session["step"] = "game"
            self._send(chat_id, "Hangi oyun temasını tarif edeyim? Oyun adını yaz.")
            return
        if action == "object":
            session["sticker_kind"] = "object"
            session["step"] = "character"
            session["slogan"] = ""
            self._send(chat_id, "Nasıl bir obje olsun? Bir cümle yaz.")
            return
        if action == "yes":
            session["step"] = "slogan"
            self._send(chat_id, "Sticker üstündeki kısa metni yaz.")
            return
        if action == "no":
            session["slogan"] = ""
            session["step"] = "character"
            self._send(chat_id, "Karakteri bir cümleyle yaz.")
            return
        if action == "ok":
            self._save_sticker(chat_id, session)
            return
        if action == "cancel":
            self._show_menu(chat_id)

    def _make_image(self, chat_id, session, prompt, revise):
        if not session.get("brand") or not session.get("fmt"):
            self._show_brands(chat_id)
            return
        if chat_id in self.busy:
            self._send(chat_id, "Bir iş hâlâ sürüyor. Bitince tekrar yaz.")
            return
        self.busy.add(chat_id)
        try:
            self._send(chat_id, "Görsel hazırlanıyor. Bu bir dakikayı bulabilir.")
            aspect = FORMATS[session["fmt"]][0]
            reference = []
            logo = logo_reference(session["brand"])
            if logo:
                reference.append(logo)
            if revise and session.get("image"):
                reference.append({"bytes": session["image"], "mime": session.get("mime") or "image/png"})
            image = self._call_with_deadline(
                lambda: generate_image(prompt, aspect, reference=reference)
            )
            session["image"] = image["bytes"]
            session["mime"] = image["mime"]
            session["interaction_id"] = image.get("interaction_id")
            session["step"] = "ready"
            filename = f"{session['brand']}_{session['fmt']}.png"
            self._send_photo(chat_id, image["bytes"], ready_caption(session, filename), self._result_keyboard())
        except Exception as exc:
            self._send(chat_id, f"Görsel çıkmadı: {exc}")
        finally:
            self.busy.discard(chat_id)

    def _make_sticker(self, chat_id, session):
        if chat_id in self.busy:
            self._send(chat_id, "Bir iş hâlâ sürüyor.")
            return
        self.busy.add(chat_id)
        try:
            if session.get("fmt") not in FORMATS:
                self._show_formats(chat_id)
                return
            aspect = FORMATS[session["fmt"]][0]
            self._send(chat_id, f"Sticker kesiliyor. Boyut: {FORMATS[session['fmt']][1]}.")
            reference = []
            if session.get("sticker_kind") != "object":
                mascot = mascot_reference(session["brand"])
                if mascot:
                    reference.append({
                        "bytes": _reference_on_magenta(mascot["bytes"]),
                        "mime": "image/png",
                    })
            prompt = sticker_prompt(session)
            image = self._call_with_deadline(
                lambda: generate_image(prompt, aspect, reference=reference)
            )
            webp, cleaned = _prepare_sticker(image["bytes"])
            if webp and not cleaned:
                self._send(chat_id, "İlk çizim afiş gibi kaldı. Sticker diye bir kez daha deniyorum.")
                image = self._call_with_deadline(
                    lambda: generate_image(prompt, aspect, reference=reference)
                )
                webp, cleaned = _prepare_sticker(image["bytes"])
            if not webp:
                self._send(chat_id, "Sticker kesilemedi. Tekrar dene.")
                return
            session["image"] = image["bytes"]
            session["mime"] = image["mime"]
            session["sticker_webp"] = webp
            session["interaction_id"] = image.get("interaction_id")
            session["step"] = "sticker_ready"
            _write_draft(chat_id, webp, session.get("brand"), session.get("user_id"))
            try:
                self._send_sticker_file(chat_id, webp)
            except Exception:
                self._send_document(chat_id, webp, "sticker.webp", "Sticker dosyası.")
            note = "Sticker böyle, zemini yok. Pakete ekleyeyim mi?"
            if not cleaned:
                note = "Zemin tam silinemedi, hâlâ afiş gibi duruyor. Pakete ekleyeyim mi?"
            self._send(
                chat_id,
                note,
                {"inline_keyboard": [[
                    {"text": "Onayla ve kaydet", "callback_data": "s:ok"},
                    {"text": "İptal", "callback_data": "s:cancel"},
                ]]},
            )
        except Exception as exc:
            self._send(chat_id, f"Sticker çıkmadı: {exc}")
        finally:
            self.busy.discard(chat_id)

    def _make_clip(self, chat_id, session, kind):
        if not session.get("brand") or not session.get("fmt"):
            self._show_brands(chat_id)
            return
        if chat_id in self.busy:
            self._send(chat_id, "Bir iş hâlâ sürüyor. Bitince tekrar yaz.")
            return
        label = "Video" if kind == "video" else "Banner gif"
        self.busy.add(chat_id)
        still = None
        try:
            aspect = FORMATS[session["fmt"]][1]
            self._send(
                chat_id,
                f"{label} hazırlanıyor ({aspect}). Önce afiş, sonra 4 saniyelik hareket. "
                "Yaklaşık 0,30 dolar. Birkaç dakika sürebilir.",
            )
            ratio = FORMATS[session["fmt"]][0]
            reference = []
            logo = logo_reference(session["brand"])
            if logo:
                reference.append(logo)
            prompt = campaign_prompt(session) if kind == "video" else banner_prompt(session)
            image = self._call_with_deadline(
                lambda: generate_image(prompt, ratio, reference=reference)
            )
            still = image["bytes"]
            mime = image.get("mime") or "image/png"
            session["image"] = still
            session["mime"] = mime
            session["interaction_id"] = image.get("interaction_id")
            motion = video_prompt(session) if kind == "video" else banner_motion_prompt(session)
            clip = self._call_with_deadline(
                lambda: generate_video(motion, still, mime, video_aspect(session.get("fmt"))),
                seconds=300,
            )
            session["step"] = "ready"
            caption = f"{label} hazır.\n{BRANDS[session['brand']]['name']} · {aspect}"
            if kind == "gif":
                self._send_animation(chat_id, clip, caption)
            else:
                self._send_video(chat_id, clip, caption)
            self._show_menu(chat_id)
        except Exception as exc:
            if still:
                self._send_photo(
                    chat_id,
                    still,
                    f"{label} hareketi çıkmadı: {exc}\nAfiş burada.",
                    self._result_keyboard(),
                )
            else:
                self._send(chat_id, f"{label} çıkmadı: {exc}")
        finally:
            self.busy.discard(chat_id)

    def _animate(self, chat_id, session):
        if not session.get("image"):
            self._send(chat_id, "Önce bir görsel üret.")
            return
        if chat_id in self.busy:
            self._send(chat_id, "Bir iş hâlâ sürüyor.")
            return
        aspect = video_aspect(session.get("fmt"))
        self.busy.add(chat_id)
        try:
            self._send(
                chat_id,
                f"Video hazırlanıyor ({aspect}, 4 saniye). Yaklaşık 0,20 dolar. Birkaç dakika sürebilir.",
            )
            video = self._call_with_deadline(
                lambda: generate_video(
                    video_prompt(session),
                    session["image"],
                    session.get("mime") or "image/png",
                    aspect,
                ),
                seconds=240,
            )
            self._send_video(chat_id, video, "Video hazır.")
        except Exception as exc:
            self._send(chat_id, f"Video çıkmadı: {exc}")
        finally:
            self.busy.discard(chat_id)

    def _send_hd(self, chat_id, session):
        if not session.get("image"):
            self._send(chat_id, "İndirilecek görsel yok.")
            return
        filename = f"{session.get('brand') or 'kampanya'}.png"
        self._send_document(chat_id, session["image"], filename, "Dosya olarak.")

    def _save_sticker(self, chat_id, session):
        webp = session.get("sticker_webp")
        brand = session.get("brand")
        if not webp:
            draft = _read_draft(chat_id)
            if draft:
                webp = draft["webp"]
                brand = brand or draft.get("brand")
                if not session.get("user_id") and draft.get("user_id"):
                    session["user_id"] = draft["user_id"]
        if not webp:
            self._send(chat_id, "Taslak durmuyor. Sticker’ı tekrar üret, çıkınca kaydet.")
            return
        if not self.username:
            try:
                me = self._api("getMe")
                self.username = ((me.get("result") or {}).get("username") or "").strip()
            except Exception as exc:
                self._send(chat_id, f"Sticker kaydedilemedi: bot adı alınamadı ({exc})")
                return
        if not self.username:
            self._send(chat_id, "Sticker kaydedilemedi: botun kullanıcı adı yok.")
            return
        if brand not in BRANDS:
            self._send(chat_id, "Marka kayboldu. /start yazıp sticker’ı tekrar üret.")
            return
        brand = session.get("brand") or brand
        session["brand"] = brand
        owner = session.get("user_id") or chat_id
        set_name = self.sticker_sets.get(brand) or f"{brand}_media_by_{self.username}".lower()
        title = f"{BRANDS[brand]['name']} Media"
        sticker = {
            "sticker": "attach://sticker",
            "format": "static",
            "emoji_list": ["🎰"],
        }
        file_part = {"sticker": ("sticker.webp", webp, "image/webp")}
        try:
            if brand in self.sticker_sets:
                self._api(
                    "addStickerToSet",
                    {"user_id": owner, "name": set_name, "sticker": json.dumps(sticker)},
                    files=file_part,
                )
            else:
                self._api(
                    "createNewStickerSet",
                    {
                        "user_id": owner,
                        "name": set_name,
                        "title": title,
                        "stickers": json.dumps([sticker]),
                    },
                    files=file_part,
                )
        except Exception as first_error:
            if brand in self.sticker_sets:
                self._send(chat_id, f"Paket eklenemedi: {first_error}")
                return
            try:
                self._api(
                    "addStickerToSet",
                    {"user_id": owner, "name": set_name, "sticker": json.dumps(sticker)},
                    files=file_part,
                )
            except Exception as second_error:
                self._send(chat_id, f"Paket eklenemedi: {second_error}")
                return
        self.sticker_sets[brand] = set_name
        _clear_draft(chat_id)
        self._send(chat_id, f"Sticker pakete eklendi: https://t.me/addstickers/{set_name}")
        self._show_menu(chat_id)

    def _show_brands(self, chat_id):
        user_id = (self.sessions.get(chat_id) or {}).get("user_id")
        self.sessions[chat_id] = new_session()
        if user_id:
            self.sessions[chat_id]["user_id"] = user_id
        rows = [[{"text": brand["name"], "callback_data": f"b:{key}"}] for key, brand in BRANDS.items()]
        self._send(chat_id, welcome_text(), {"inline_keyboard": rows})

    def _show_menu(self, chat_id):
        session = self._session(chat_id)
        name = BRANDS[session["brand"]]["name"]
        self._send(
            chat_id,
            f"{name} seçildi. Ne üreteyim?",
            {"inline_keyboard": [
                [{"text": "Görsel üret", "callback_data": "m:img"}],
                [{"text": "Video üret", "callback_data": "m:vid"}],
                [{"text": "Banner gif", "callback_data": "m:gif"}],
                [{"text": "Sticker üret", "callback_data": "m:stk"}],
                [{"text": "Marka değiştir", "callback_data": "a:home"}],
            ]},
        )

    def _show_formats(self, chat_id):
        self._send(
            chat_id,
            "Boyut seç.\n1:1 Kare — gönderi\n9:16 Dikey — story\n16:9 Yatay — banner",
            {"inline_keyboard": [[
                {"text": "1:1 Kare", "callback_data": "f:1x1"},
                {"text": "9:16 Dikey", "callback_data": "f:9x16"},
                {"text": "16:9 Yatay", "callback_data": "f:16x9"},
            ]]},
        )

    def _show_categories(self, chat_id):
        self._send(
            chat_id,
            "Kategori seç.",
            {"inline_keyboard": [[
                {"text": "Casino Promo", "callback_data": "c:casino"},
                {"text": "Spor Bahisi", "callback_data": "c:sport"},
                {"text": "Slot", "callback_data": "c:slot"},
            ]]},
        )

    def _show_sticker_kinds(self, chat_id):
        self._send(
            chat_id,
            "Ne tür sticker?",
            {"inline_keyboard": [[
                {"text": "Maskot", "callback_data": "s:mascot"},
                {"text": "Obje", "callback_data": "s:object"},
            ]]},
        )

    def _ask_slogan(self, chat_id):
        self._send(
            chat_id,
            "Sticker üstünde slogan olsun mu?",
            {"inline_keyboard": [[
                {"text": "Evet", "callback_data": "s:yes"},
                {"text": "Hayır", "callback_data": "s:no"},
            ]]},
        )

    def _campaign_help(self, session):
        brand = BRANDS[session["brand"]]["name"]
        fmt = FORMATS[session["fmt"]][1]
        category = CATEGORIES[session["category"]]
        mode = session.get("mode")
        if mode == "video":
            lead = "Kampanya metnini yaz. Aynen videodaki afişe basılır."
        elif mode == "gif":
            lead = "Kampanya metnini yaz. Aynen banner’a basılır."
        else:
            lead = "Kampanya metnini yaz. Aynen görsele basılır."
        return (
            f"{brand} · {category} · {fmt}\n\n"
            f"{lead}\n"
            "Örnek: %100 Freespin Bonusu Seni Bekliyor!"
        )

    def _result_keyboard(self):
        return {"inline_keyboard": [
            [
                {"text": "HD indir", "callback_data": "a:hd"},
                {"text": "Yeni görsel", "callback_data": "a:new"},
            ],
            [
                {"text": "Revize et", "callback_data": "a:rev"},
                {"text": "Hareketlendir", "callback_data": "a:vid"},
            ],
            [
                {"text": "Sticker üret", "callback_data": "a:stk"},
                {"text": "Ana menü", "callback_data": "a:home"},
            ],
        ]}

    def _send(self, chat_id, text, reply_markup=None):
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        self._api("sendMessage", payload)

    def _send_photo(self, chat_id, data, caption, reply_markup):
        fields = {"chat_id": str(chat_id), "caption": caption}
        if reply_markup:
            fields["reply_markup"] = json.dumps(reply_markup, ensure_ascii=False)
        self._api("sendPhoto", fields, files={"photo": ("image.png", data, "image/png")})

    def _send_document(self, chat_id, data, filename, caption):
        self._api(
            "sendDocument",
            {"chat_id": str(chat_id), "caption": caption},
            files={"document": (filename, data, "image/png")},
        )

    def _send_sticker_file(self, chat_id, data):
        self._api(
            "sendSticker",
            {"chat_id": str(chat_id)},
            files={"sticker": ("sticker.webp", data, "image/webp")},
        )

    def _send_video(self, chat_id, data, caption):
        self._api(
            "sendVideo",
            {"chat_id": str(chat_id), "caption": caption},
            files={"video": ("kampanya.mp4", data, "video/mp4")},
        )

    def _send_animation(self, chat_id, data, caption):
        self._api(
            "sendAnimation",
            {"chat_id": str(chat_id), "caption": caption},
            files={"animation": ("banner.mp4", data, "video/mp4")},
        )

    def _call_with_deadline(self, fn, seconds=80):
        box = {}

        def run():
            try:
                box["value"] = fn()
            except Exception as exc:
                box["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(seconds)
        if worker.is_alive():
            raise GeminiError("Google zamanında cevap vermedi. Biraz sonra tekrar dene.")
        if box.get("error"):
            err = box["error"]
            raise err if isinstance(err, GeminiError) else GeminiError(str(err))
        return box.get("value")

    def _api(self, method, payload=None, files=None, timeout=60):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        if files:
            body, content_type = _multipart(payload or {}, files)
            req = urllib.request.Request(url, data=body, headers={"Content-Type": content_type}, method="POST")
        elif payload is not None:
            data = urllib.parse.urlencode({k: v for k, v in payload.items() if v is not None}).encode()
            req = urllib.request.Request(url, data=data, method="POST")
        else:
            req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            raise RuntimeError(detail or f"Telegram {exc.code}") from exc
        if not result.get("ok", True):
            raise RuntimeError(result.get("description") or "Telegram hatası")
        return result


def _chat_id(update):
    if "callback_query" in update:
        return ((update["callback_query"].get("message") or {}).get("chat") or {}).get("id")
    return ((update.get("message") or {}).get("chat") or {}).get("id")


def _multipart(fields, files):
    boundary = "----MediaBotBoundary7f3a"
    chunks = []
    for key, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        chunks.append(str(value).encode())
        chunks.append(b"\r\n")
    for key, (filename, data, mime) in files.items():
        chunks.append(f"--{boundary}\r\n".encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
        )
        chunks.append(f"Content-Type: {mime}\r\n\r\n".encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _draft_dir():
    from pathlib import Path
    directory = Path("/tmp/media-bot-drafts")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write_draft(chat_id, webp, brand, user_id):
    directory = _draft_dir()
    (directory / f"{chat_id}.webp").write_bytes(webp)
    (directory / f"{chat_id}.json").write_text(json.dumps({
        "brand": brand,
        "user_id": user_id,
    }))


def _read_draft(chat_id):
    directory = _draft_dir()
    blob = directory / f"{chat_id}.webp"
    if not blob.is_file():
        return None
    meta = {}
    sidecar = directory / f"{chat_id}.json"
    if sidecar.is_file():
        try:
            meta = json.loads(sidecar.read_text())
        except json.JSONDecodeError:
            meta = {}
    return {"webp": blob.read_bytes(), "brand": meta.get("brand"), "user_id": meta.get("user_id")}


def _clear_draft(chat_id):
    directory = _draft_dir()
    for suffix in (".webp", ".json"):
        path = directory / f"{chat_id}{suffix}"
        if path.is_file():
            path.unlink()


def _load_image(data):
    from PIL import Image
    return Image.open(BytesIO(data)).convert("RGBA")


def _corner_color(image):
    width, height = image.size
    pixels = image.load()
    points = ((1, 1), (width - 2, 1), (1, height - 2), (width - 2, height - 2))
    colors = [pixels[x, y][:3] for x, y in points]
    return tuple(sum(color[channel] for color in colors) // 4 for channel in range(3))


def _flood_clear(image, match, paint):
    """Kenardan başlayıp match olan pikselleri paint yapar."""
    width, height = image.size
    pixels = image.load()
    seen = bytearray(width * height)
    stack = []
    for x in range(width):
        stack.append((x, 0))
        stack.append((x, height - 1))
    for y in range(height):
        stack.append((0, y))
        stack.append((width - 1, y))
    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= width or y >= height:
            continue
        index = y * width + x
        if seen[index]:
            continue
        seen[index] = 1
        if not match(pixels[x, y]):
            continue
        pixels[x, y] = paint
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))
    return image


def _reference_on_magenta(data):
    """Maskotun kart zeminini düz macentaya çevirir. Model o zemini kopyalamasın."""
    image = _load_image(data)
    background = _corner_color(image)

    def match(pixel):
        if pixel[3] < 16:
            return True
        return (
            abs(pixel[0] - background[0])
            + abs(pixel[1] - background[1])
            + abs(pixel[2] - background[2])
        ) <= 55

    _flood_clear(image, match, (255, 0, 255, 255))
    width, height = image.size
    long_side = max(width, height)
    if long_side < 512 and long_side > 0:
        scale = 512 / long_side
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))))
    out = BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


def _knockout_magenta(image):
    def match(pixel):
        if pixel[3] < 16:
            return True
        return abs(pixel[0] - 255) + pixel[1] + abs(pixel[2] - 255) <= 140

    width, height = image.size
    pixels = image.load()
    corners = ((1, 1), (width - 2, 1), (1, height - 2), (width - 2, height - 2))
    if not any(match(pixels[x, y]) for x, y in corners):
        return image
    return _flood_clear(image, match, (255, 0, 255, 0))


def _transparent_ratio(image):
    histogram = image.getchannel("A").histogram()
    return histogram[0] / float(image.size[0] * image.size[1])


def _fit_sticker(image):
    from PIL import Image
    bounds = image.getchannel("A").getbbox()
    if not bounds:
        return None
    image = image.crop(bounds)
    width, height = image.size
    pad = max(4, int(max(width, height) * 0.08))
    canvas = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    canvas.paste(image, (pad, pad), image)
    width, height = canvas.size
    if width >= height:
        size = (512, max(1, round(512 * height / width)))
    else:
        size = (max(1, round(512 * width / height)), 512)
    return canvas.resize(size, Image.Resampling.LANCZOS)


def _encode_webp(image):
    limit = 512 * 1024
    for quality in (80, 60, 40, 25):
        out = BytesIO()
        image.save(out, format="WEBP", quality=quality, method=6)
        if out.tell() <= limit:
            return out.getvalue()
    out = BytesIO()
    image.save(out, format="WEBP", quality=15, method=6)
    return out.getvalue()


def _prepare_sticker(data):
    """Macenta zemini siler, bir kenarı 512 px olan şeffaf webp döner."""
    try:
        image = _load_image(data)
    except Exception:
        return None, False
    cut = _knockout_magenta(image.copy())
    cleaned = _transparent_ratio(cut) >= 0.08
    fitted = _fit_sticker(cut if cleaned else image)
    if fitted is None:
        return None, False
    return _encode_webp(fitted), cleaned


def _to_sticker_webp(data):
    webp, _cleaned = _prepare_sticker(data)
    return webp


def start_in_background():
    token = os.environ.get(TOKEN_ENV, "").strip()
    gemini = os.environ.get("GEMINI_API_KEY", "").strip()
    if not token or not gemini:
        print("media bot kapalı: MEDIA_BOT_TOKEN veya GEMINI_API_KEY eksik")
        return
    bot = MediaBot(token)
    threading.Thread(target=bot.run, name="media-bot", daemon=True).start()


def main():
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token or not os.environ.get("GEMINI_API_KEY", "").strip():
        raise SystemExit("MEDIA_BOT_TOKEN ve GEMINI_API_KEY gerekli")
    MediaBot(token).run()


if __name__ == "__main__":
    main()
