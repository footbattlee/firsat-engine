import base64
import os
from uuid import UUID
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()
SHARE_ORIGIN = "https://fırsatcı.com"
CHANNELS = {"telegram", "facebook", "instagram", "story", "whatsapp", "other"}

def tracked_deal_url(data, channel):
    """Brand the published deal+offer pair; attribution continues in the existing tracker."""
    deal_id = str(data.get("id") or "").strip()
    offer_id = str(data.get("offer_id") or data.get("cheapest_offer_id") or "").strip()
    try:
        pair = UUID(deal_id).bytes + UUID(offer_id).bytes
    except (ValueError, AttributeError) as error:
        raise ValueError("tracking link requires valid deal and offer UUIDs") from error
    code = base64.urlsafe_b64encode(pair).decode("ascii").rstrip("=")
    source = str(channel or "other").strip().casefold()
    if source not in CHANNELS:
        source = "other"
    return SHARE_ORIGIN + "/f/" + code + "?" + urlencode({"s": source})
