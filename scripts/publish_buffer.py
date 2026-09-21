"""نشر أصول الحلقة الجديدة عبر Buffer.

الترتيب:
- الفيديو الكامل الأفقي أولًا.
- short_1 بعد FULL_TO_SHORT_1_HOURS (افتراضيًا 3 ساعات).
- short_2 بعد FULL_TO_SHORT_2_HOURS (افتراضيًا 7 ساعات).

لا يوجد هنا منطق part1/part2. كل أصل يرفع وينشر Native على كل قناة.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
EPISODE_PATH = ROOT_DIR / "state" / "current_episode.json"
OUTPUT_DIR = ROOT_DIR / "output"
BUFFER_GRAPHQL_API = "https://api.buffer.com"
GITHUB_API = "https://api.github.com"
RELEASE_TAG = "media-assets"
CHANNEL_PENDING_LIMIT = int(os.environ.get("CHANNEL_PENDING_LIMIT", "10"))
ENABLE_PREFLIGHT_CHECK = os.environ.get("ENABLE_PREFLIGHT_CHECK", "true").lower() != "false"

FULL_TO_SHORT_1_HOURS = float(os.environ.get("FULL_TO_SHORT_1_HOURS", "3"))
FULL_TO_SHORT_2_HOURS = float(os.environ.get("FULL_TO_SHORT_2_HOURS", "7"))


def build_channel_services() -> dict[str, str]:
    result = {}
    for env_name, service in {
        "BUFFER_YOUTUBE_CHANNEL_ID": "youtube",
        "BUFFER_FACEBOOK_CHANNEL_ID": "facebook",
        "BUFFER_INSTAGRAM_CHANNEL_ID": "instagram",
    }.items():
        value = os.environ.get(env_name, "").strip()
        if value:
            result[value] = service
    # توافق مع المعرّفات القديمة الموجودة في النسخة السابقة.
    result.setdefault("6aaa8778ea19ca0bde57da16", "youtube")
    result.setdefault("6aaa853fea19ca0bde57b5f7", "facebook")
    return result


CHANNEL_SERVICES = build_channel_services()

CREATE_POST_MUTATION = """
mutation CreatePost($text: String!, $channelId: ChannelId!, $videoUrl: String!, $metadata: PostInputMetaData, $dueAt: DateTime!) {
  createPost(input: {
    text: $text
    channelId: $channelId
    schedulingType: automatic
    mode: customScheduled
    dueAt: $dueAt
    metadata: $metadata
    assets: [{ video: { url: $videoUrl } }]
  }) {
    ... on PostActionSuccess { post { id text dueAt } }
    ... on MutationError { message }
  }
}
"""
GET_ORGANIZATIONS_QUERY = "query GetOrganizations { account { organizations { id name } } }"
GET_PENDING_QUERY = """
query GetPendingPosts($organizationId: OrganizationId!, $channelId: ChannelId!) {
  posts(first: 10, input: {organizationId: $organizationId, filter: {status: [scheduled], channelIds: [$channelId]}}) {
    edges { node { id } }
  }
}
"""


def graphql(query: str, variables: dict, api_key: str) -> dict:
    response = requests.post(
        BUFFER_GRAPHQL_API,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={"query": query, "variables": variables},
        timeout=40,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("errors"):
        raise RuntimeError(str(data["errors"]))
    return data.get("data", {})


def github_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


def upload_media(video_path: Path, token: str) -> str:
    repo = os.environ.get("MEDIA_REPOSITORY") or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise RuntimeError("MEDIA_REPOSITORY أو GITHUB_REPOSITORY غير موجود.")
    release_response = requests.get(f"{GITHUB_API}/repos/{repo}/releases/tags/{RELEASE_TAG}", headers=github_headers(token), timeout=20)
    if release_response.status_code == 404:
        release_response = requests.post(
            f"{GITHUB_API}/repos/{repo}/releases",
            headers=github_headers(token),
            json={"tag_name": RELEASE_TAG, "name": "Media Assets", "body": "Temporary hosting for Buffer assets.", "prerelease": True},
            timeout=20,
        )
    release_response.raise_for_status()
    release = release_response.json()
    asset_name = f"video_{video_path.stem}_{os.environ.get('GITHUB_RUN_ID', 'local')}.mp4"
    with video_path.open("rb") as handle:
        response = requests.post(
            release["upload_url"].split("{")[0], headers={**github_headers(token), "Content-Type": "video/mp4"},
            params={"name": asset_name}, data=handle, timeout=300,
        )
    response.raise_for_status()
    return response.json()["browser_download_url"]


def metadata_for(channel_id: str, asset_type: str, title: str) -> dict | None:
    service = CHANNEL_SERVICES.get(channel_id)
    if service == "youtube":
        return {"youtube": {"title": title[:100] or "Horror Episode", "categoryId": "24", "privacy": "public", "madeForKids": False, "notifySubscribers": asset_type == "full_video", "isAiGenerated": True}}
    if service == "facebook":
        # الشورت Reel، والفيديو الكامل فيديو أصلي عادي.
        return {"facebook": {"type": "reel" if asset_type == "short" else "video"}}
    if service == "instagram":
        # نوع video يحاول إبقاء الفيديو الكامل Feed video؛ الشورت Reel.
        return {"instagram": {"type": "reel" if asset_type == "short" else "video", "shouldShareToFeed": True}}
    return None


def build_post_text(service: str, asset_type: str, title: str, caption: str, full_url: str | None = None) -> str:
    hashtags = " ".join(dict.fromkeys(re.findall(r"(?<!\w)#\S+", caption)))
    if asset_type == "full_video":
        parts = [title.strip(), caption.strip()]
    elif service == "youtube":
        parts = [f"{title.strip()} — مقتطف", "عايز تعرف النهاية؟ شاهد الحلقة كاملة على YouTube."]
        if full_url:
            parts.append(f"🔗 الحلقة الكاملة: {full_url}")
    elif service == "facebook":
        parts = [f"{title.strip()} — مقتطف", "عايز تعرف النهاية؟ شاهد الحلقة كاملة على صفحتنا."]
        if full_url:
            parts.append(f"🔗 الحلقة الكاملة: {full_url}")
    else:
        parts = [f"{title.strip()} — مقتطف", "عايز تعرف النهاية؟ الحلقة كاملة على صفحتنا."]
    if hashtags and hashtags not in "\n".join(parts):
        parts.append(hashtags)
    return "\n\n".join(part for part in parts if part).strip()


def iso_after(hours: float) -> str:
    due = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=1 if hours == 0 else 0)
    return due.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def organization_id(api_key: str) -> str:
    organizations = graphql(GET_ORGANIZATIONS_QUERY, {}, api_key).get("account", {}).get("organizations", [])
    if not organizations:
        raise RuntimeError("لم يتم العثور على Buffer organization.")
    return organizations[0]["id"]


def pending_count(org_id: str, channel_id: str, api_key: str) -> int:
    data = graphql(GET_PENDING_QUERY, {"organizationId": org_id, "channelId": channel_id}, api_key)
    return len(data.get("posts", {}).get("edges", []))


def create_post(video_url: str, text: str, title: str, channel_id: str, api_key: str, due_at: str, asset_type: str) -> dict:
    variables = {"text": text, "channelId": channel_id, "videoUrl": video_url, "metadata": metadata_for(channel_id, asset_type, title), "dueAt": due_at}
    data = graphql(CREATE_POST_MUTATION, variables, api_key)
    result = data.get("createPost") or {}
    if result.get("message"):
        raise RuntimeError(result["message"])
    if not result.get("post"):
        raise RuntimeError(f"لم يُرجع Buffer منشورًا: {result}")
    return result["post"]


def channel_ids() -> list[str]:
    raw = os.environ.get("BUFFER_CHANNEL_ID", "").replace(";", ",").replace("\n", ",")
    ids = [x.strip().strip("\"'") for x in raw.split(",") if x.strip()]
    return list(dict.fromkeys(ids or CHANNEL_SERVICES.keys()))


def main() -> None:
    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    github_token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not api_key or not github_token:
        sys.exit("BUFFER_API_KEY و GITHUB_TOKEN مطلوبان.")
    if not EPISODE_PATH.exists():
        sys.exit("state/current_episode.json غير موجود.")

    episode = json.loads(EPISODE_PATH.read_text(encoding="utf-8"))
    title = str(episode.get("title", "Horror Episode")).strip()
    caption = str(episode.get("caption", "")).strip()
    if not caption:
        sys.exit("current_episode.json لا يحتوي caption.")

    full_path = OUTPUT_DIR / "final_video_full.mp4"
    if not full_path.exists() or full_path.stat().st_size == 0:
        sys.exit(f"الفيديو الكامل غير موجود: {full_path}")

    shorts = sorted(OUTPUT_DIR.glob("short_*_*.mp4"))
    if not shorts:
        sys.exit("لا توجد شورتس جاهزة للنشر.")
    # ترتيب ثابت: short_1 ثم short_2، وداخل كل رقم المنصات.
    shorts = sorted(shorts, key=lambda p: (int(p.stem.split("_")[1]), p.stem))

    ids = channel_ids()
    unknown = [cid for cid in ids if cid not in CHANNEL_SERVICES]
    if unknown:
        sys.exit("قنوات غير معروفة الخدمة؛ أضفها إلى BUFFER_*_CHANNEL_ID: " + ", ".join(unknown))

    org_id = organization_id(api_key) if ENABLE_PREFLIGHT_CHECK else None
    services = {cid: CHANNEL_SERVICES[cid] for cid in ids}
    full_urls = {}
    for service in set(services.values()):
        full_urls[service] = os.environ.get(f"FULL_VIDEO_URL_{service.upper()}", "").strip() or None

    assets: list[tuple[str, Path, float]] = [("full_video", full_path, 0.0)]
    short_numbers = sorted({int(p.stem.split("_")[1]) for p in shorts})
    for number in short_numbers:
        delay = FULL_TO_SHORT_1_HOURS if number == 1 else FULL_TO_SHORT_2_HOURS
        for path in [p for p in shorts if int(p.stem.split("_")[1]) == number]:
            assets.append(("short", path, delay))

    successes = 0
    failures = []
    for asset_type, path, delay in assets:
        url = upload_media(path, github_token)
        due_at = iso_after(delay)
        platform_hint = path.stem.rsplit("_", 1)[-1] if asset_type == "short" else None
        print(f"📤 {path.name} → {due_at} UTC")
        for cid in ids:
            service = services[cid]
            if platform_hint and platform_hint != service:
                continue
            try:
                if org_id is not None and pending_count(org_id, cid, api_key) >= CHANNEL_PENDING_LIMIT:
                    raise RuntimeError(f"قائمة Buffer ممتلئة ({CHANNEL_PENDING_LIMIT}) للقناة {service}")
                text = build_post_text(service, asset_type, title, caption, full_urls.get(service))
                post = create_post(url, text, title, cid, api_key, due_at, asset_type)
                print(f"  ✅ {service}: {post.get('id')} عند {post.get('dueAt', due_at)}")
                successes += 1
            except Exception as exc:
                failures.append((path.name, service, str(exc)))
                print(f"  ❌ {service}: {exc}")

    print(f"نجاح النشر: {successes}")
    for item in failures:
        print("فشل:", " | ".join(item))
    if successes == 0:
        sys.exit("لم ينجح نشر أي أصل.")


if __name__ == "__main__":
    main()
