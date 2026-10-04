import os
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv(
    "SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co"
).rstrip("/")
CLICK_TRACKING_BASE_URL = os.getenv(
    "CLICK_TRACKING_BASE_URL",
    f"{SUPABASE_URL}/functions/v1/deal-click",
).strip()


def tracked_deal_url(data, channel):
    """Build a non-secret redirect URL keyed to the published deal and offer."""
    deal_id = str(data.get("id") or "").strip()
    offer_id = str(data.get("offer_id") or data.get("cheapest_offer_id") or "").strip()
    if not deal_id or not offer_id:
        raise ValueError("tracking link requires deal and offer ids")
    safe_channel = str(channel or "other").strip().casefold()
    if safe_channel not in {"telegram", "facebook", "instagram", "story", "whatsapp", "other"}:
        safe_channel = "other"
    return CLICK_TRACKING_BASE_URL + "?" + urlencode(
        {"deal": deal_id, "offer": offer_id, "channel": safe_channel}
    )
