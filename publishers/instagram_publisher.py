import os
from pathlib import Path
from urllib.parse import quote

import requests

GRAPH_BASE = os.getenv("INSTAGRAM_GRAPH_BASE", "https://graph.instagram.com").rstrip("/")
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
BUCKET = os.getenv("INSTAGRAM_MEDIA_BUCKET", "instagram-media").strip()


def _token():
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("INSTAGRAM_ACCESS_TOKEN tanimli degil")
    return token


def _user_id():
    user_id = os.getenv("INSTAGRAM_USER_ID", "").strip()
    if not user_id:
        raise RuntimeError("INSTAGRAM_USER_ID tanimli degil")
    return user_id


def _raise(response, operation):
    if response.ok:
        return
    raise RuntimeError(f"Instagram {operation} HTTP {response.status_code}: {response.text[:1500]}")


def verify_instagram_user():
    response = requests.get(
        f"{GRAPH_BASE}/me",
        headers={"Authorization": f"Bearer {_token()}"},
        params={"fields": "id,username"},
        timeout=30,
    )
    _raise(response, "me")
    return response.json()


def upload_public_image(image_path, candidate_id):
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("Supabase Storage config eksik")

    image_path = Path(image_path)
    object_path = f"deals/{candidate_id}/{image_path.name}"
    encoded_path = quote(object_path, safe="/")
    response = requests.post(
        f"{SUPABASE_URL}/storage/v1/object/{BUCKET}/{encoded_path}",
        headers={
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "image/png",
            "x-upsert": "true",
        },
        data=image_path.read_bytes(),
        timeout=90,
    )
    _raise(response, "storage upload")
    return f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET}/{encoded_path}"


def create_image_container(image_url, caption):
    response = requests.post(
        f"{GRAPH_BASE}/{_user_id()}/media",
        headers={"Authorization": f"Bearer {_token()}"},
        data={"image_url": image_url, "caption": caption},
        timeout=45,
    )
    _raise(response, "create media container")
    creation_id = response.json().get("id")
    if not creation_id:
        raise RuntimeError(f"Instagram creation id dondurmedi: {response.text[:1000]}")
    return str(creation_id)


def publish_container(creation_id):
    response = requests.post(
        f"{GRAPH_BASE}/{_user_id()}/media_publish",
        headers={"Authorization": f"Bearer {_token()}"},
        data={"creation_id": creation_id},
        timeout=45,
    )
    _raise(response, "media publish")
    media_id = response.json().get("id")
    if not media_id:
        raise RuntimeError(f"Instagram media id dondurmedi: {response.text[:1000]}")
    return str(media_id)


def publish_instagram_post(caption, image_path, candidate_id):
    account = verify_instagram_user()
    if str(account.get("id")) != str(_user_id()):
        raise RuntimeError(
            f"INSTAGRAM_USER_ID uyusmuyor: env={_user_id()} api={account.get('id')}"
        )
    image_url = upload_public_image(image_path, candidate_id)
    creation_id = create_image_container(image_url, caption)
    return publish_container(creation_id)
