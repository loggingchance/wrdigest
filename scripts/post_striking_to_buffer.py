#!/usr/bin/env python3
"""Publish one standout Woods Run observation to X through Buffer.

The morning Woods Run job writes a `strikingText` field into the newest issue in
`data/issues.json`. This script publishes that text later in the morning as a
standalone native X post — no newsletter boilerplate and no required link.

Safety/quality behavior:
- only considers the newest issue;
- only posts when that issue is dated today in America/Denver;
- skips cleanly when `strikingText` is blank;
- prevents duplicate posting by comparing recent Buffer posts;
- scheduled runs may start late, so a 10:25-11:20 America/Denver window is used
  rather than requiring the job to start at exactly 10:30;
- manual/trigger runs may set FORCE_RUN=true to bypass the local-time guard.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from post_to_buffer import fail, get_organization_id, get_x_channel, graphql

LOCAL_TZ = ZoneInfo("America/Denver")
WINDOW_START_MINUTES = 10 * 60 + 25
WINDOW_END_MINUTES = 11 * 60 + 20
MAX_X_TEXT = 280


def normalize(text: str) -> str:
    return " ".join((text or "").split()).strip()


def load_latest_issue() -> dict:
    path = Path("data/issues.json")
    if not path.exists():
        fail("data/issues.json is missing")
    issues = json.loads(path.read_text(encoding="utf-8"))
    if not issues:
        fail("data/issues.json contains no issues")
    return issues[0]


def local_time_is_target(now: datetime) -> bool:
    minutes = now.hour * 60 + now.minute
    return WINDOW_START_MINUTES <= minutes <= WINDOW_END_MINUTES


def recent_posts_contain_text(organization_id: str, channel_id: str, text: str) -> bool:
    query = """
    query RecentPosts($organizationId: OrganizationId!, $channelId: ChannelId!) {
      posts(
        first: 50
        input: {
          organizationId: $organizationId
          filter: { status: [sent, scheduled], channelIds: [$channelId] }
          sort: [{ field: createdAt, direction: desc }]
        }
      ) {
        edges { node { id text status createdAt channelId } }
      }
    }
    """
    data = graphql(
        query,
        {"organizationId": organization_id, "channelId": channel_id},
    )
    target = normalize(text)
    for edge in data.get("posts", {}).get("edges", []):
        post = edge.get("node", {})
        if normalize(post.get("text") or "") == target:
            print(f"Striking-item post already present in Buffer ({post.get('status')}): {post.get('id')}")
            return True
    return False


def publish(channel_id: str, text: str) -> dict:
    mutation = """
    mutation PublishWoodsRunStriking($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id text status dueAt externalLink }
        }
        ... on MutationError { message }
      }
    }
    """
    data = graphql(
        mutation,
        {
            "input": {
                "text": text,
                "channelId": channel_id,
                "schedulingType": "automatic",
                "mode": "shareNow",
                "source": "woods-run-striking",
            }
        },
    )
    payload = data.get("createPost") or {}
    if payload.get("message"):
        fail(f"Buffer rejected the striking-item post: {payload['message']}")
    post = payload.get("post")
    if not post:
        fail(f"Unexpected Buffer createPost response: {json.dumps(payload)}")
    return post


def main() -> None:
    now = datetime.now(LOCAL_TZ)
    force = os.environ.get("FORCE_RUN", "").strip().lower() in {"1", "true", "yes"}

    if not force and not local_time_is_target(now):
        print(
            f"Local time is {now:%Y-%m-%d %H:%M %Z}; scheduled publishing window is "
            "10:25-11:20 America/Denver. Skipping this cron pass."
        )
        return

    issue = load_latest_issue()
    issue_date = (issue.get("date") or "").strip()
    if issue_date != now.date().isoformat():
        print(f"Newest issue is {issue_date or '(undated)'}, not today's {now.date().isoformat()}. No striking-item post sent.")
        return

    text = (issue.get("strikingText") or "").strip()
    if not text:
        print("No strikingText supplied for today's issue; deliberately skipping the second X post.")
        return

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > MAX_X_TEXT:
        fail(f"strikingText is too long for X ({len(text)} characters; max {MAX_X_TEXT})")

    organization_id = get_organization_id()
    channel = get_x_channel(organization_id)

    if recent_posts_contain_text(organization_id, channel["id"], text):
        print("No action needed; today's striking-item post already exists.")
        return

    print("Publishing Woods Run striking-item post to X through Buffer:")
    print(text)
    post = publish(channel["id"], text)
    print(
        f"Buffer accepted striking-item post {post.get('id')} with status {post.get('status')}. "
        f"External link: {post.get('externalLink') or '(pending)'}"
    )


if __name__ == "__main__":
    main()
