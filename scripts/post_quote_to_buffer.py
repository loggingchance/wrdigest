#!/usr/bin/env python3
"""Publish the prepared FBS quote card to X and Instagram through Buffer.

The daily ChatGPT task chooses a source-balanced unused quote from Dropbox and writes
its public/raw image URL to data/quote_post.json. This script publishes the same card
to both social channels and records the quote in data/quote_history.json only after
both channels are confirmed as posted (either newly created or already present).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BUFFER_API = "https://api.buffer.com"
TIMEZONE = ZoneInfo("America/Denver")
POST_FILE = Path("data/quote_post.json")
HISTORY_FILE = Path("data/quote_history.json")

TARGETS = (
    {"service": "twitter", "name": "ForestBizSchool", "label": "X"},
    {"service": "instagram", "name": "northeastforests", "label": "Instagram"},
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def graphql(query: str, variables: dict | None = None) -> dict:
    api_key = os.environ.get("BUFFER_API_KEY", "").strip()
    if not api_key:
        fail("BUFFER_API_KEY is not set")
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    request = urllib.request.Request(
        BUFFER_API,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "WoodsRunDigest/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"Buffer HTTP {exc.code}: {body}")
    except Exception as exc:
        fail(f"Buffer request failed: {exc}")
    if result.get("errors"):
        fail(f"Buffer GraphQL error: {json.dumps(result['errors'])}")
    return result.get("data", {})


def organization_id() -> str:
    data = graphql("query { account { organizations { id name } } }")
    orgs = data.get("account", {}).get("organizations", [])
    if not orgs:
        fail("No Buffer organization found")
    return orgs[0]["id"]


def channels(org_id: str) -> list[dict]:
    query = """
    query Channels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) { id name service }
    }
    """
    data = graphql(query, {"organizationId": org_id})
    return data.get("channels", [])


def select_channel(all_channels: list[dict], service: str, name: str, label: str) -> dict:
    matching_service = [c for c in all_channels if c.get("service") == service]
    exact = [c for c in matching_service if (c.get("name") or "").casefold() == name.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(matching_service) == 1:
        candidate = matching_service[0]
        print(f"{label}: expected {name!r}, using the only connected {service} channel {candidate.get('name')!r}.")
        return candidate
    visible = ", ".join(f"{c.get('name')} ({c.get('service')})" for c in all_channels) or "(none)"
    fail(f"Could not uniquely select {label} channel {name!r}. Connected: {visible}")


def load_json(path: Path, default=None):
    if not path.exists():
        if default is not None:
            return default
        fail(f"Missing required file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def already_recorded(history: dict, date: str, quote_index: int) -> bool:
    for item in history.get("used", []):
        if item.get("date") == date or int(item.get("quoteIndex", -1)) == quote_index:
            return True
    return False


def recent_media_post(org_id: str, channel_id: str, today: str) -> dict | None:
    query = """
    query RecentQuotePosts($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(
        first: 30
        input: {
          organizationId: $organizationId
          filter: { status: [sent, scheduled], channelIds: [$channelId] }
          sort: [{ field: createdAt, direction: desc }]
        }
      ) {
        edges {
          node {
            id text status createdAt externalLink
            assets { source mimeType }
          }
        }
      }
    }
    """
    data = graphql(query, {"organizationId": org_id, "channelId": channel_id})
    for edge in data.get("posts", {}).get("edges", []):
        post = edge.get("node", {})
        created = (post.get("createdAt") or "")[:10]
        text = (post.get("text") or "").strip()
        assets = post.get("assets") or []
        if created == today and not text and assets:
            return post
    return None


def publish(channel_id: str, image_url: str, service: str) -> dict:
    mutation = """
    mutation PublishQuote($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id text status externalLink assets { source mimeType } }
        }
        ... on MutationError { message }
      }
    }
    """
    post_input = {
        "text": "",
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow",
        "source": "woods-run-quote",
        "assets": [{"image": {"url": image_url}}],
    }
    if service == "instagram":
        post_input["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}

    data = graphql(mutation, {"input": post_input})
    payload = data.get("createPost") or {}
    if payload.get("message"):
        fail(f"Buffer rejected {service} quote image: {payload['message']}")
    post = payload.get("post")
    if not post:
        fail(f"Unexpected Buffer response for {service}: {json.dumps(payload)}")
    return post


def record_success(history: dict, prepared: dict, posts: dict[str, dict]) -> None:
    used = history.setdefault("used", [])
    x_post = posts.get("twitter") or {}
    instagram_post = posts.get("instagram") or {}
    used.append({
        "date": prepared["date"],
        "quoteIndex": int(prepared["quoteIndex"]),
        "filename": prepared["filename"],
        "source": prepared["source"],
        "bufferPostId": x_post.get("id"),
        "externalLink": x_post.get("externalLink"),
        "xBufferPostId": x_post.get("id"),
        "xExternalLink": x_post.get("externalLink"),
        "instagramBufferPostId": instagram_post.get("id"),
        "instagramExternalLink": instagram_post.get("externalLink"),
    })
    history["version"] = 2
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    prepared = load_json(POST_FILE)
    required = ("date", "quoteIndex", "filename", "source", "imageUrl")
    for field in required:
        if prepared.get(field) in (None, ""):
            fail(f"{POST_FILE} is missing {field}")

    today = datetime.now(TIMEZONE).date().isoformat()
    if prepared["date"] != today:
        fail(f"Prepared quote is dated {prepared['date']}, but today in America/Denver is {today}")

    quote_index = int(prepared["quoteIndex"])
    history = load_json(HISTORY_FILE, {"version": 2, "used": []})
    if already_recorded(history, today, quote_index):
        print("This quote/date is already recorded as posted to both channels; no action needed.")
        return

    org_id = organization_id()
    all_channels = channels(org_id)
    selected = {
        target["service"]: select_channel(all_channels, target["service"], target["name"], target["label"])
        for target in TARGETS
    }

    print(f"Publishing quote {quote_index}: {prepared['filename']}")
    print(f"Source: {prepared['source']}")

    posts: dict[str, dict] = {}
    for target in TARGETS:
        service = target["service"]
        label = target["label"]
        channel = selected[service]

        existing = recent_media_post(org_id, channel["id"], today)
        if existing:
            print(f"{label}: media-only post already exists today ({existing.get('id')}); treating it as complete.")
            posts[service] = existing
            continue

        post = publish(channel["id"], prepared["imageUrl"], service)
        posts[service] = post
        print(f"{label}: Buffer accepted post {post.get('id')} with status {post.get('status')}.")
        print(f"{label} external link: {post.get('externalLink') or '(pending)'}")

    if len(posts) != len(TARGETS):
        fail("Not all quote-card destinations were confirmed.")
    record_success(history, prepared, posts)
    print("Quote card confirmed on X and Instagram; history updated.")


if __name__ == "__main__":
    main()
