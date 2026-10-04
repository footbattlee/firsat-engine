import argparse
import html
import json
import os
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from creative.generate_deal_reel import render_reel
from creative.generate_deal_creative import (
    load_candidates,
    money,
    output_path_for,
    render_candidate_bundle,
    validate_candidate,
)

from publishers.instagram_publisher import publish_instagram_post
from publishers.facebook_publisher import publish_facebook_photo
from tracking_links import tracked_deal_url

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
APPROVAL_CHAT_ID = os.getenv("TELEGRAM_APPROVAL_CHAT_ID", "").strip()
PUBLISH_CHAT_ID = os.getenv("TELEGRAM_PUBLISH_CHAT_ID", "").strip()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PLATFORMS = ("telegram", "instagram", "facebook", "story")
MEDIA_BUCKET = os.getenv("INSTAGRAM_MEDIA_BUCKET", "instagram-media").strip() or "instagram-media"


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
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(params, safe="(),.*:-")
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


def require_safe_candidate(data):
    validation = validate_candidate(data)
    if not validation["ok"]:
        raise RuntimeError(
            "Validation gate candidate'i engelledi: " + ", ".join(validation["errors"])
        )


def is_redispatch(data):
    return data.get("notification_reason") == "redispatch_price_drop"


def discount_text(data):
    if is_redispatch(data):
        drop = f"{float(data.get('redispatch_drop_percent') or 0):.2f}".replace(".", ",")
        return f"Son paylaşımdan sonra %{drop} düştü"
    gap = f"{float(data['gap_percent']):.2f}".replace(".", ",")
    return f"Rakip mağazadan %{gap} daha ucuz"


def comparison_price(data):
    if is_redispatch(data):
        return "Önceki paylaşım fiyatı", data.get("previous_notified_price")
    return "Rakip fiyat", data["competitor_price"]


def public_caption(data):
    old_label, old_value = comparison_price(data)
    return (
        "🔥 <b>FİYATZADE FIRSATI</b>\n\n"
        f"<b>{html.escape(str(data['title']))}</b>\n\n"
        f"🛒 {html.escape(str(data['merchant']))}\n"
        f"💸 {old_label}: <s>{html.escape(money(old_value))}</s>\n"
        f"🔥 <b>{html.escape(money(data['cheapest_price']))}</b>\n"
        f"📉 <b>{html.escape(discount_text(data))}</b>\n\n"
        f"🔗 <a href=\"{html.escape(tracked_deal_url(data, 'telegram'), quote=True)}\">Fırsata Git</a>\n\n"
        "<i>Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.</i>\n"
        "#işbirliği #reklam"
    )


def publish_to_telegram(data):
    if not PUBLISH_CHAT_ID:
        raise RuntimeError("TELEGRAM_PUBLISH_CHAT_ID tanimli degil")

    outputs = render_candidate_bundle(data)
    preview = outputs["instagram"]
    upload_story_assist(data["id"], outputs["story"])
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


def instagram_caption(data):
    old_label, old_value = comparison_price(data)
    return (
        f"🔥 FİYATZADE FIRSATI\n\n"
        f"{data['title']}\n\n"
        f"🛒 {data['merchant']}\n"
        f"💸 {old_label}: {money(old_value)}\n"
        f"🔥 Fırsat fiyatı: {money(data['cheapest_price'])}\n"
        f"📉 {discount_text(data)}\n\n"
        f"🔗 Fırsata git: {tracked_deal_url(data, 'instagram')}\n\n"
        "Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.\n\n"
        "#işbirliği #reklam #fiyatzade #indirim #fırsat"
    )


def publish_story_assist(data):
    outputs = render_candidate_bundle(data)
    upload_story_assist(data["id"], outputs["story"])
    with open(outputs["story"], "rb") as image:
        result = api(
            "sendPhoto",
            data={
                "chat_id": APPROVAL_CHAT_ID,
                "caption": (f"📱 STORY HAZIR\n\n{data['title']}\n\n"
                            f"🔗 Ürüne git: {tracked_deal_url(data, 'story')}"),
            },
            files={"photo": image},
        )
    return str(result["message_id"])


def publish_to_instagram(data):
    outputs = render_candidate_bundle(data)
    image = outputs["instagram"]
    return publish_instagram_post(instagram_caption(data), image, data["id"])


def facebook_caption(data, channel="facebook"):
    old_label, old_value = comparison_price(data)
    link = tracked_deal_url(data, channel)
    return (
        f"🔥 FİYATZADE FIRSATI\n\n"
        f"{data['title']}\n\n"
        f"🛒 {data['merchant']}\n"
        f"💸 {old_label}: {money(old_value)}\n"
        f"🔥 Fırsat fiyatı: {money(data['cheapest_price'])}\n"
        f"📉 {discount_text(data)}\n\n"
        f"🔗 Fırsata git: {link}\n\n"
        "Fiyatlar değişebilir. Satın almadan önce mağaza fiyatını kontrol edin.\n\n"
        "#işbirliği #reklam #fiyatzade #indirim #fırsat"
    )


def publish_to_facebook(data):
    outputs = render_candidate_bundle(data)
    image = outputs["instagram"]
    return publish_facebook_photo(facebook_caption(data), image)


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
    old_label, old_value = comparison_price(data)
    detail = ""
    if is_redispatch(data):
        gap = f"{float(data['gap_percent']):.2f}".replace(".", ",")
        detail = f"\n🏪 Rakip mağaza farkı: %{gap}"
    return (
        "🟠 <b>YENİ FIRSAT</b>\n\n"
        f"<b>{html.escape(str(data['title']))}</b>\n\n"
        f"🏷 Marka: {html.escape(str(data.get('brand') or '-'))}\n"
        f"🛒 Mağaza: {html.escape(str(data['merchant']))}\n"
        f"💸 {old_label}: <s>{html.escape(money(old_value))}</s>\n"
        f"🔥 Fırsat fiyatı: <b>{html.escape(money(data['cheapest_price']))}</b>\n"
        f"📉 <b>{html.escape(discount_text(data))}</b>{detail}"
        f"{warning}\n\n"
        f"🔗 <a href=\"{html.escape(str(data['product_url']), quote=True)}\">Ürüne Git</a>"
    )


def keyboard(candidate_id):
    return {
        "inline_keyboard": [
            [

                {"text": "🎬 REELS PAYLAŞ", "callback_data": f"reel:{candidate_id}"},
            ],
            [
                {"text": "❌ REDDET", "callback_data": f"reject:{candidate_id}"},
                {"text": "🟢 WHATSAPP", "callback_data": f"whatsapp:{candidate_id}"},
            ],
        ]
    }


def upload_story_assist(candidate_id, story_path):
    """Upload the ready 1080x1920 Story creative for the cloud webhook."""
    object_path = f"deals/{candidate_id}/story.png"
    url = f"{SUPABASE_URL}/storage/v1/object/{MEDIA_BUCKET}/{object_path}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "image/png",
        "x-upsert": "true",
    }
    with open(story_path, "rb") as handle:
        response = requests.post(url, headers=headers, data=handle, timeout=45)
    response.raise_for_status()
    print(f"STORY READY | {candidate_id} | {story_path}")
    return object_path


def upload_reel_assist(candidate_id, reel_path):
    """Upload the prepared MP4 so the cloud PAYLAS webhook can publish it."""
    object_path = f"deals/{candidate_id}/reel.mp4"
    url = f"{SUPABASE_URL}/storage/v1/object/{MEDIA_BUCKET}/{object_path}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "video/mp4",
        "x-upsert": "true",
    }
    with open(reel_path, "rb") as handle:
        response = requests.post(url, headers=headers, data=handle, timeout=180)
    response.raise_for_status()
    current = publication_state(candidate_id, "reel")
    if not current or current.get("status") != "published":
        sb_upsert(
            "deal_publications",
            [{
                "deal_candidate_id": candidate_id,
                "platform": "reel",
                "status": "pending",
                "external_post_id": None,
                "error_message": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }],
            "deal_candidate_id,platform",
        )
    print(f"REEL READY | {candidate_id} | {reel_path}")
    return object_path


def send_candidate(data):
    validation = validate_candidate(data)
    if not validation["ok"]:
        print(f"VALIDATION FAILED | {data['id']} | " + " | ".join(validation["errors"]))
        return False

    outputs = render_candidate_bundle(data)
    preview = outputs["instagram"]
    # Prepare Story asset while the candidate is being dispatched. The cloud
    # PAYLAS webhook cannot render Python creatives, so it reads this file later.
    try:
        upload_story_assist(data["id"], outputs["story"])
    except Exception as exc:
        print(f"STORY PREP WARNING | {data['id']} | {exc}")
    try:
        reel_path = render_reel(data, outputs["story"])
        upload_reel_assist(data["id"], reel_path)
    except Exception as exc:
        print(f"REEL PREP WARNING | {data['id']} | {exc}")
    with open(preview, "rb") as image:
        result = api(
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
    return str(result["message_id"])



def dispatch_pending_candidates(limit=50):
    """Send pending deals; deal engine can reopen one after a meaningful new price drop."""
    # Read lightweight candidate IDs first. Loading full product/offer details
    # for already-dispatched rows made each pipeline spend minutes on work it
    # would immediately skip. The limit now means new cards to send.
    pipeline_started_at = os.getenv("PIPELINE_STARTED_AT", "").strip()
    if not pipeline_started_at:
        pipeline_started_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        print(f"APPROVAL SCOPE | son 1 saatte güncellenen adaylar: {pipeline_started_at}")
    else:
        print(f"APPROVAL SCOPE | mevcut pipeline adayları: {pipeline_started_at}")
    candidate_refs = sb_get(
        "deal_candidates",
        {
            "select": "id",
            "status": "eq.candidate",
            "updated_at": f"gte.{pipeline_started_at}",
            "order": "gap_percent.desc",
            "limit": "1000",
        },
    )
    dispatch_rows = sb_get(
        "deal_approval_dispatches",
        {"select": "deal_candidate_id,status", "limit": "10000"},
    )
    dispatch_by_candidate = {row["deal_candidate_id"]: row for row in dispatch_rows}
    sent = 0
    skipped = 0
    failed = 0
    for ref in candidate_refs:
        if sent + failed >= limit:
            break
        candidate_id = ref["id"]
        dispatch = dispatch_by_candidate.get(candidate_id)
        if dispatch and dispatch.get("status") == "sent":
            skipped += 1
            continue
        data = load_candidates(1, candidate_id)[0]
        now = datetime.now(timezone.utc).isoformat()
        if not dispatch:
            sb_upsert(
                "deal_approval_dispatches",
                [{"deal_candidate_id": candidate_id, "status": "pending", "updated_at": now}],
                "deal_candidate_id",
            )
        try:
            message_id = send_candidate(data)
            if not message_id:
                sb_patch(
                    "deal_candidates", {"id": f"eq.{candidate_id}"},
                    {"status": "expired", "verified": False,
                     "verified_at": None, "updated_at": now},
                )
                raise RuntimeError("Validation gate candidate'i engelledi")
            sb_patch(
                "deal_approval_dispatches",
                {"deal_candidate_id": f"eq.{candidate_id}"},
                {"status": "sent", "telegram_message_id": message_id, "error_message": None,
                 "sent_at": now, "updated_at": now},
            )
            sent += 1
        except Exception as exc:
            sb_patch(
                "deal_approval_dispatches",
                {"deal_candidate_id": f"eq.{candidate_id}"},
                {"status": "failed", "error_message": str(exc)[:1000], "updated_at": now},
            )
            failed += 1
            print(f"APPROVAL DISPATCH ERROR | {candidate_id} | {exc}")
    print(f"APPROVAL DISPATCH DONE | sent={sent} | skipped={skipped} | failed={failed}")
    return failed == 0

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
        # Telegram callback queries expire quickly. Acknowledge the button press
        # before the slower Telegram/Meta publishing work starts.
        answer_callback(callback_id, "Normal gönderi otomatik kuyrukta; yarım saatlik yayın sırasını bekliyor.")
        return
    elif action == "whatsapp":
        answer_callback(callback_id, "WhatsApp paylaşım paketi hazırlanıyor.")
        try:
            data = load_candidate_for_publish(candidate_id)
            require_safe_candidate(data)
            outputs = render_candidate_bundle(data)
            with open(outputs["instagram"], "rb") as image:
                api(
                    "sendPhoto",
                    data={
                        "chat_id": APPROVAL_CHAT_ID,
                        "caption": facebook_caption(data, "whatsapp"),
                    },
                    files={"photo": image},
                )
            print(f"APPROVAL WHATSAPP READY | {candidate_id}")
        except Exception as exc:
            print(f"APPROVAL WHATSAPP ERROR | {candidate_id} | {exc}")
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
    parser.add_argument("--dispatch-pending", action="store_true", help="Yeni candidate fırsatları admin onayına bir kez gönder")
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
    if args.dispatch_pending:
        dispatch_pending_candidates(args.limit)
    if args.listen:
        poll()
    if not args.send and not args.listen and not args.dispatch_pending:
        parser.error("--send, --dispatch-pending, --listen veya --get-chat-id kullan")


if __name__ == "__main__":
    main()
