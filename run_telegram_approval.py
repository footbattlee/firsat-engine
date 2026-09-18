import argparse
import html
import json
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from creative.generate_deal_creative import (
    load_candidates,
    money,
    output_path_for,
    render_candidate_bundle,
    validate_candidate,
)

from publishers.x_publisher import publish_x_post
from publishers.instagram_publisher import publish_instagram_post

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
APPROVAL_CHAT_ID = os.getenv("TELEGRAM_APPROVAL_CHAT_ID", "").strip()
PUBLISH_CHAT_ID = os.getenv("TELEGRAM_PUBLISH_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PLATFORMS = ("telegram", "instagram", "x", "whatsapp")


def require_config(require_chat_id=True):
    missing = []
    if not BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if require_chat_id and not APPROVAL_CHAT_ID:
        missing.append("TELEGRAM_APPROVAL_CHAT_ID")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(".env eksik: " + ", ".join(missing))


def api(method, *, data=None, files=None, timeout=45):
    response = requests.post(f"{API}/{method}", data=data, files=files, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram {method}: {payload}")
    return payload["result"]


def sb_headers(extra=None):
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


def sb_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(params, safe="(),.*:-+")
    response = requests.get(url, headers=sb_headers(), timeout=30)
    response.raise_for_status()
    return response.json()


def sb_patch(table, filters, values):
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(filters, safe=".*:-+")
    response = requests.patch(url, headers=sb_headers({"Prefer": "return=minimal"}), json=values, timeout=30)
    response.raise_for_status()


def sb_upsert(table, rows, on_conflict):
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
    response = requests.post(
        url,
        headers=sb_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        json=rows,
        timeout=30,
    )
    response.raise_for_status()


def load_candidate_for_publish(candidate_id):
    candidates = load_candidates(1, candidate_id)
    if not candidates:
        raise RuntimeError("Candidate bulunamadi")
    return candidates[0]


def public_caption(data):
    return (
        "🔥 <b>FİYATZADE FIRSATI</b>\n\n"
        f"<b>{html.escape(str(data['title']))}</b>\n\n"
        f"🛒 {html.escape(str(data['merchant']))}\n"
        f"💸 <s>{html.escape(money(data['competitor_price']))}</s>\n"
        f"🔥 <b>{html.escape(money(data['cheapest_price']))}</b>\n"
        f"📉 <b>%{float(data['gap_percent']):.2f}".replace(".", ",") + " daha ucuz</b>\n\n"
        f"🔗 <a href=\"{html.escape(str(data['product_url']), quote=True)}\">Fırsata Git</a>\n\n"
        "<i>Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.</i>\n"
        "#işbirliği #reklam"
    )


def publish_to_telegram(data):
    if not PUBLISH_CHAT_ID:
        raise RuntimeError("TELEGRAM_PUBLISH_CHAT_ID tanimli degil")

    outputs = render_candidate_bundle(data)
    preview = outputs["instagram"]
    with open(preview, "rb") as image:
        result = api(
            "sendPhoto",
            data={
                "chat_id": PUBLISH_CHAT_ID,
                "caption": public_caption(data),
                "parse_mode": "HTML",
            },
            files={"photo": image},
        )
    return str(result["message_id"])


def x_caption(data):
    gap = f"{float(data['gap_percent']):.2f}".replace(".", ",")
    text = (
        f"🔥 FİYATZADE FIRSATI\n\n"
        f"{data['title']}\n\n"
        f"🛒 {data['merchant']}\n"
        f"🔥 {money(data['cheapest_price'])}\n"
        f"📉 %{gap} daha ucuz\n\n"
        f"🔗 {data['product_url']}\n\n"
        "#işbirliği #reklam"
    )
    # Keep room for X's URL counting/normalization and avoid API rejection.
    return text[:270]


def instagram_caption(data):
    gap = f"{float(data['gap_percent']):.2f}".replace(".", ",")
    return (
        f"🔥 FİYATZADE FIRSATI\n\n"
        f"{data['title']}\n\n"
        f"🛒 {data['merchant']}\n"
        f"💸 Rakip fiyat: {money(data['competitor_price'])}\n"
        f"🔥 Fırsat fiyatı: {money(data['cheapest_price'])}\n"
        f"📉 %{gap} daha ucuz\n\n"
        "Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.\n\n"
        "#işbirliği #reklam #fiyatzade #indirim #fırsat"
    )


def publish_to_instagram(data):
    outputs = render_candidate_bundle(data)
    image = outputs["instagram"]
    return publish_instagram_post(instagram_caption(data), image, data["id"])


def publish_to_x(data):
    outputs = render_candidate_bundle(data)
    image = outputs["site"]
    return publish_x_post(x_caption(data), image)


def mark_publication(candidate_id, platform, status, *, external_post_id=None, error_message=None):
    now = datetime.now(timezone.utc).isoformat()
    values = {
        "status": status,
        "external_post_id": external_post_id,
        "error_message": error_message,
        "updated_at": now,
    }
    if status == "published":
        values["published_at"] = now
    sb_patch(
        "deal_publications",
        {"deal_candidate_id": f"eq.{candidate_id}", "platform": f"eq.{platform}"},
        values,
    )


def publication_state(candidate_id, platform):
    rows = sb_get(
        "deal_publications",
        {
            "select": "status,external_post_id,published_at",
            "deal_candidate_id": f"eq.{candidate_id}",
            "platform": f"eq.{platform}",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def persist_publish_request(candidate_id):
    """Create missing platform rows without resetting existing publication state."""
    existing = sb_get(
        "deal_publications",
        {
            "select": "platform",
            "deal_candidate_id": f"eq.{candidate_id}",
        },
    )
    existing_platforms = {row["platform"] for row in existing}
    missing = [platform for platform in PLATFORMS if platform not in existing_platforms]
    if not missing:
        return

    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "deal_candidate_id": candidate_id,
            "platform": platform,
            "status": "pending",
            "updated_at": now,
        }
        for platform in missing
    ]
    sb_upsert("deal_publications", rows, "deal_candidate_id,platform")


def persist_rejection(candidate_id):
    now = datetime.now(timezone.utc).isoformat()
    sb_patch("deal_candidates", {"id": f"eq.{candidate_id}"}, {"status": "rejected", "updated_at": now})
    # A rejection cancels only work that has not been published yet.
    sb_patch(
        "deal_publications",
        {"deal_candidate_id": f"eq.{candidate_id}", "status": "in.(pending,publishing)"},
        {"status": "failed", "error_message": "Rejected by admin", "updated_at": now},
    )


def caption(data, validation):
    warning = ""
    if validation["warnings"]:
        warning = "\n\n⚠️ <b>KONTROL GEREKLİ</b>\n" + "\n".join(
            html.escape(item) for item in validation["warnings"]
        )
    return (
        "🟠 <b>YENİ FIRSAT</b>\n\n"
        f"<b>{html.escape(str(data['title']))}</b>\n\n"
        f"🏷 Marka: {html.escape(str(data.get('brand') or '-'))}\n"
        f"🛒 Mağaza: {html.escape(str(data['merchant']))}\n"
        f"💸 Rakip fiyat: <s>{html.escape(money(data['competitor_price']))}</s>\n"
        f"🔥 Fırsat fiyatı: <b>{html.escape(money(data['cheapest_price']))}</b>\n"
        f"📉 <b>%{float(data['gap_percent']):.2f}".replace(".", ",") + " daha ucuz</b>"
        f"{warning}\n\n"
        f"🔗 <a href=\"{html.escape(str(data['product_url']), quote=True)}\">Ürüne Git</a>"
    )


def keyboard(candidate_id):
    return {
        "inline_keyboard": [[
            {"text": "🚀 PAYLAŞ", "callback_data": f"publish:{candidate_id}"},
            {"text": "❌ REDDET", "callback_data": f"reject:{candidate_id}"},
        ]]
    }


def send_candidate(data):
    validation = validate_candidate(data)
    if not validation["ok"]:
        print(f"VALIDATION FAILED | {data['id']} | " + " | ".join(validation["errors"]))
        return False

    outputs = render_candidate_bundle(data)
    preview = outputs["instagram"]
    with open(preview, "rb") as image:
        api(
            "sendPhoto",
            data={
                "chat_id": APPROVAL_CHAT_ID,
                "caption": caption(data, validation),
                "parse_mode": "HTML",
                "reply_markup": json.dumps(keyboard(data["id"]), ensure_ascii=False),
            },
            files={"photo": image},
        )
    print(f"TELEGRAM SENT | {data['id']} | {preview}")
    return True


def answer_callback(callback_id, text):
    try:
        api("answerCallbackQuery", data={"callback_query_id": callback_id, "text": text})
    except requests.HTTPError as exc:
        # Telegram callback queries expire quickly. An old button press may still
        # reach getUpdates but can no longer be acknowledged. Do not crash the bot.
        response = getattr(exc, "response", None)
        detail = response.text if response is not None else str(exc)
        print(f"CALLBACK ACK WARNING | {detail}")


def handle_callback(query):
    raw = query.get("data", "")
    callback_id = query["id"]
    if ":" not in raw:
        answer_callback(callback_id, "Bilinmeyen işlem")
        return
    action, candidate_id = raw.split(":", 1)

    if action == "publish":
        try:
            persist_publish_request(candidate_id)
            data = load_candidate_for_publish(candidate_id)
            results = []

            telegram_state = publication_state(candidate_id, "telegram")
            if telegram_state and telegram_state.get("status") == "published":
                message_id = telegram_state.get("external_post_id") or "-"
                results.append("Telegram zaten yayınlandı")
                print(f"APPROVAL PUBLISH SKIP | {candidate_id} | telegram=already_published | message_id={message_id}")
            else:
                try:
                    mark_publication(candidate_id, "telegram", "publishing")
                    message_id = publish_to_telegram(data)
                    mark_publication(candidate_id, "telegram", "published", external_post_id=message_id)
                    results.append("Telegram yayınlandı")
                    print(f"APPROVAL PUBLISH | {candidate_id} | telegram=published | message_id={message_id}")
                except Exception as publish_exc:
                    mark_publication(candidate_id, "telegram", "failed", error_message=str(publish_exc)[:1000])
                    results.append("Telegram başarısız")
                    print(f"TELEGRAM PUBLISH ERROR | {candidate_id} | {publish_exc}")

            instagram_state = publication_state(candidate_id, "instagram")
            if instagram_state and instagram_state.get("status") == "published":
                media_id = instagram_state.get("external_post_id") or "-"
                results.append("Instagram zaten yayınlandı")
                print(f"APPROVAL PUBLISH SKIP | {candidate_id} | instagram=already_published | media_id={media_id}")
            else:
                try:
                    mark_publication(candidate_id, "instagram", "publishing")
                    media_id = publish_to_instagram(data)
                    mark_publication(candidate_id, "instagram", "published", external_post_id=media_id)
                    results.append("Instagram yayınlandı")
                    print(f"APPROVAL PUBLISH | {candidate_id} | instagram=published | media_id={media_id}")
                except Exception as publish_exc:
                    mark_publication(candidate_id, "instagram", "failed", error_message=str(publish_exc)[:1000])
                    results.append("Instagram başarısız")
                    print(f"INSTAGRAM PUBLISH ERROR | {candidate_id} | {publish_exc}")

            x_state = publication_state(candidate_id, "x")
            if x_state and x_state.get("status") == "published":
                post_id = x_state.get("external_post_id") or "-"
                results.append("X zaten yayınlandı")
                print(f"APPROVAL PUBLISH SKIP | {candidate_id} | x=already_published | post_id={post_id}")
            else:
                try:
                    mark_publication(candidate_id, "x", "publishing")
                    post_id = publish_to_x(data)
                    mark_publication(candidate_id, "x", "published", external_post_id=post_id)
                    results.append("X yayınlandı")
                    print(f"APPROVAL PUBLISH | {candidate_id} | x=published | post_id={post_id}")
                except Exception as publish_exc:
                    mark_publication(candidate_id, "x", "failed", error_message=str(publish_exc)[:1000])
                    results.append("X başarısız")
                    print(f"X PUBLISH ERROR | {candidate_id} | {publish_exc}")

            answer_callback(callback_id, "PAYLAŞ: " + " | ".join(results))
        except Exception as exc:
            answer_callback(callback_id, "PAYLAŞ kaydedilemedi.")
            print(f"APPROVAL PUBLISH ERROR | {candidate_id} | {exc}")
    elif action == "reject":
        try:
            persist_rejection(candidate_id)
            answer_callback(callback_id, "REDDET kaydedildi.")
            print(f"APPROVAL REJECT | {candidate_id} | DB=rejected")
        except Exception as exc:
            answer_callback(callback_id, "REDDET kaydedilemedi.")
            print(f"APPROVAL REJECT ERROR | {candidate_id} | {exc}")
    else:
        answer_callback(callback_id, "Bilinmeyen işlem")


def discard_pending_callbacks():
    """Drain and acknowledge every queued Telegram update before listening."""
    offset = None
    cleared = 0

    while True:
        data = {"timeout": 0, "limit": 100, "allowed_updates": '["callback_query"]'}
        if offset is not None:
            data["offset"] = offset
        updates = api("getUpdates", data=data, timeout=15)
        if not updates:
            break

        cleared += len(updates)
        offset = max(update["update_id"] for update in updates) + 1

        # A positive offset confirms all preceding updates. Keep draining in case
        # Telegram had more than one page of stale callbacks queued.
        api(
            "getUpdates",
            data={"offset": offset, "timeout": 0, "limit": 100, "allowed_updates": '["callback_query"]'},
            timeout=15,
        )

    if cleared:
        print(f"STALE CALLBACKS CLEARED | count={cleared}")
    return offset


def poll():
    offset = discard_pending_callbacks()
    print("TELEGRAM APPROVAL BOT READY | Ctrl+C ile durdur")
    while True:
        data = {"timeout": 30, "allowed_updates": '["callback_query"]'}
        if offset is not None:
            data["offset"] = offset
        updates = api("getUpdates", data=data, timeout=40)
        for update in updates:
            offset = update["update_id"] + 1
            if update.get("callback_query"):
                handle_callback(update["callback_query"])
        time.sleep(0.2)


def show_chat_ids(chat_username=None):
    """Resolve a public @username or print chats seen by the bot."""
    require_config(require_chat_id=False)

    if chat_username:
        username = chat_username.strip()
        if not username.startswith("@"):
            username = "@" + username
        chat = api("getChat", data={"chat_id": username}, timeout=15)
        name = chat.get("title") or chat.get("username") or "-"
        print(f"CHAT | {name} | CHAT_ID={chat['id']} | TYPE={chat.get('type', '-')}")
        return

    updates = api("getUpdates", data={"timeout": 0}, timeout=15)
    chats = {}
    for update in updates:
        message = update.get("message") or update.get("channel_post") or {}
        chat = message.get("chat")
        if chat:
            chats[str(chat["id"])] = chat
        callback = update.get("callback_query") or {}
        callback_chat = (callback.get("message") or {}).get("chat")
        if callback_chat:
            chats[str(callback_chat["id"])] = callback_chat

    if not chats:
        print("CHAT BULUNAMADI | Bota/gruba bir mesaj gonderip tekrar dene.")
        return

    for chat_id, chat in chats.items():
        name = chat.get("title") or chat.get("username") or chat.get("first_name") or "-"
        print(f"CHAT | {name} | CHAT_ID={chat_id} | TYPE={chat.get('type', '-')}")


def main():
    parser = argparse.ArgumentParser(description="Fiyatzade Telegram approval V1")
    parser.add_argument("--send", action="store_true", help="Candidate'lari Telegram onayina gonder")
    parser.add_argument("--listen", action="store_true", help="PAYLAS/REDDET butonlarini dinle")
    parser.add_argument("--get-chat-id", action="store_true", help="Botun gordugu chat ID'lerini listele")
    parser.add_argument("--chat-username", help="Public Telegram @kullanici adini getChat ile coz")
    parser.add_argument("--candidate-id")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.get_chat_id:
        show_chat_ids(args.chat_username)
        return
    require_config()

    if args.send:
        candidates = load_candidates(args.limit, args.candidate_id)
        sent = sum(1 for item in candidates if send_candidate(item))
        print(f"TELEGRAM BATCH DONE | candidates={len(candidates)} | sent={sent}")
    if args.listen:
        poll()
    if not args.send and not args.listen:
        parser.error("--send, --listen veya --get-chat-id kullan")


if __name__ == "__main__":
    main()
