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

from creative.generate_deal_creative import (
    load_candidates,
    money,
    output_path_for,
    render_candidate_bundle,
    validate_candidate,
)

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
APPROVAL_CHAT_ID = os.getenv("TELEGRAM_APPROVAL_CHAT_ID", "").strip()
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


def persist_publish_request(candidate_id):
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {
            "deal_candidate_id": candidate_id,
            "platform": platform,
            "status": "pending",
            "external_post_id": None,
            "error_message": None,
            "published_at": None,
            "updated_at": now,
        }
        for platform in PLATFORMS
    ]
    # Unique(deal_candidate_id, platform) makes repeated PAYLAS presses idempotent.
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
            answer_callback(callback_id, "PAYLAŞ alındı. Yayın kuyruğuna eklendi.")
            print(f"APPROVAL PUBLISH | {candidate_id} | DB=pending")
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
    """Advance Telegram's update offset so stale button presses are not replayed."""
    updates = api(
        "getUpdates",
        data={"timeout": 0, "allowed_updates": '["callback_query"]'},
        timeout=15,
    )
    if not updates:
        return None

    offset = max(update["update_id"] for update in updates) + 1
    # Confirm the new offset once; Telegram then forgets all older updates.
    api(
        "getUpdates",
        data={"offset": offset, "timeout": 0, "allowed_updates": '["callback_query"]'},
        timeout=15,
    )
    print(f"STALE CALLBACKS CLEARED | count={len(updates)}")
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


def show_chat_ids():
    """Print chats seen by the bot without exposing the bot token."""
    require_config(require_chat_id=False)
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
    parser.add_argument("--candidate-id")
    parser.add_argument("--limit", type=int, default=1)
    args = parser.parse_args()
    if args.get_chat_id:
        show_chat_ids()
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
