import os

import requests

GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v26.0").strip()
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _token():
    token = os.getenv("FACEBOOK_SYSTEM_USER_TOKEN", "").strip()
    if not token:
        raise RuntimeError("FACEBOOK_SYSTEM_USER_TOKEN tanimli degil")
    return token


def _page_id():
    page_id = os.getenv("FACEBOOK_PAGE_ID", "").strip()
    if not page_id:
        raise RuntimeError("FACEBOOK_PAGE_ID tanimli degil")
    return page_id


def _raise(response, operation):
    if response.ok:
        return
    raise RuntimeError(
        f"Facebook {operation} HTTP {response.status_code}: {response.text[:1500]}"
    )


def verify_page_access():
    response = requests.get(
        f"{GRAPH_BASE}/{_page_id()}",
        params={"access_token": _token(), "fields": "id,name"},
        timeout=30,
    )
    _raise(response, "page verify")
    data = response.json()
    if str(data.get("id")) != str(_page_id()):
        raise RuntimeError(
            f"FACEBOOK_PAGE_ID uyusmuyor: env={_page_id()} api={data.get('id')}"
        )
    return data


def publish_facebook_photo(message, image_path):
    verify_page_access()
    with open(image_path, "rb") as image:
        response = requests.post(
            f"{GRAPH_BASE}/{_page_id()}/photos",
            data={
                "access_token": _token(),
                "caption": message,
                "published": "true",
            },
            files={"source": ("fiyatzade.png", image, "image/png")},
            timeout=90,
        )
    _raise(response, "photo publish")
    body = response.json()
    post_id = body.get("post_id") or body.get("id")
    if not post_id:
        raise RuntimeError(f"Facebook post id dondurmedi: {body}")
    return str(post_id)
