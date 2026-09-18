import base64
import mimetypes
import os

import requests

X_API_BASE = "https://api.x.com/2"


def _token():
    token = os.getenv("X_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("X_ACCESS_TOKEN tanimli degil")
    return token


def _headers(json_content=False):
    headers = {"Authorization": f"Bearer {_token()}"}
    if json_content:
        headers["Content-Type"] = "application/json"
    return headers


def _raise_x(response, operation):
    if response.ok:
        return
    detail = response.text[:1500]
    raise RuntimeError(f"X {operation} HTTP {response.status_code}: {detail}")


def verify_x_user():
    response = requests.get(f"{X_API_BASE}/users/me", headers=_headers(), timeout=30)
    _raise_x(response, "users/me")
    return response.json()["data"]


def upload_image(image_path):
    image_path = str(image_path)
    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
    with open(image_path, "rb") as fh:
        raw = fh.read()

    # X API v2 one-shot media upload. Images are small enough to avoid
    # the INIT/APPEND/FINALIZE flow used for large media/video.
    payload = {
        "media": base64.b64encode(raw).decode("ascii"),
        "media_category": "tweet_image",
        "media_type": mime_type,
    }
    response = requests.post(
        f"{X_API_BASE}/media/upload",
        headers=_headers(json_content=True),
        json=payload,
        timeout=90,
    )
    _raise_x(response, "media upload")
    body = response.json()
    data = body.get("data") or body
    media_id = data.get("id") or data.get("media_id") or data.get("media_id_string")
    if not media_id:
        raise RuntimeError(f"X media upload media_id dondurmedi: {body}")
    return str(media_id)


def create_post(text, media_id=None):
    payload = {"text": text}
    if media_id:
        payload["media"] = {"media_ids": [str(media_id)]}

    response = requests.post(
        f"{X_API_BASE}/tweets",
        headers=_headers(json_content=True),
        json=payload,
        timeout=45,
    )
    _raise_x(response, "create post")
    body = response.json()
    post_id = (body.get("data") or {}).get("id")
    if not post_id:
        raise RuntimeError(f"X post id dondurmedi: {body}")
    return str(post_id)


def publish_x_post(text, image_path):
    verify_x_user()
    media_id = upload_image(image_path)
    return create_post(text, media_id=media_id)
