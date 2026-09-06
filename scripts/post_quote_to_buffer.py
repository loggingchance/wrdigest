#!/usr/bin/env python3
"""Publish the prepared FBS quote card to X through Buffer.

The daily ChatGPT task chooses a source-balanced unused quote from Dropbox and writes
its public/raw image URL to data/quote_post.json. This script publishes that image
immediately and records it in data/quote_history.json only after Buffer accepts it.
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
TARGET_SERVICE = "twitter"
TARGET_NAME = "ForestBizSchool"
TIMEZONE = ZoneInfo("America/Denver")
POST_FILE = Path("data/quote_post.json")
HISTORY_FILE = Path("data/quote_history.json")


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


def x_channel(org_id: str) -> dict:
    query = """
    query Channels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) { id name service }
    }
    """
    data = graphql(query, {"organizationId": org_id})
    channels = [c for c in data.get("channels", []) if c.get("service") == TARGET_SERVICE]
    exact = [c for c in channels if (c.get("name") or "").casefold() == TARGET_NAME.casefold()]
    if len(exact) == 1:
        return exact[0]
    if len(channels) == 1:
        return channels[0]
    fail(f"Could not uniquely select X channel {TARGET_NAME}")


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


def recent_buffer_post_exists(org_id: str, channel_id: str, today: str) -> bool:
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
            id text status createdAt
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
        # The quote series is intentionally media-only. A media-only post already
        # created today is sufficient duplicate protection for workflow reruns.
        if created == today and not text and assets:
            print(f"Quote-style media post already exists in Buffer today: {post.get('id')}")
            return True
    return False


def publish(channel_id: str, image_url: str) -> dict:
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
    data = graphql(
        mutation,
        {
            "input": {
                "text": "",
                "channelId": channel_id,
                "schedulingType": "automatic",
                "mode": "shareNow",
                "source": "woods-run-quote",
                "assets": [{"image": {"url": image_url}}],
            }
        },
    )
    payload = data.get("createPost") or {}
    if payload.get("message"):
        fail(f"Buffer rejected quote image: {payload['message']}")
    post = payload.get("post")
    if not post:
        fail(f"Unexpected Buffer response: {json.dumps(payload)}")
    return post


def record_success(history: dict, prepared: dict, post: dict) -> None:
    used = history.setdefault("used", [])
    used.append(
        {
            "date": prepared["date"],
            "quoteIndex": int(prepared["quoteIndex"]),
            "filename": prepared["filename"],
            "source": prepared["source"],
            "bufferPostId": post.get("id"),
            "externalLink": post.get("externalLink"),
        }
    )
    history["version"] = 1
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
    history = load_json(HISTORY_FILE, {"version": 1, "used": []})
    if already_recorded(history, today, quote_index):
        print("This quote/date is already recorded as posted; no action needed.")
        return

    org_id = organization_id()
    channel = x_channel(org_id)
    if recent_buffer_post_exists(org_id, channel["id"], today):
        print("A media-only quote post already exists today; no duplicate will be created.")
        return

    print(f"Publishing quote {quote_index}: {prepared['filename']}")
    print(f"Source: {prepared['source']}")
    post = publish(channel["id"], prepared["imageUrl"])
    print(f"Buffer accepted post {post.get('id')} with status {post.get('status')}.")
    print(f"External link: {post.get('externalLink') or '(pending)'}")
    record_success(history, prepared, post)


if __name__ == "__main__":
    main()
