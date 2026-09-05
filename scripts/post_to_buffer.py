#!/usr/bin/env python3
"""Publish the newest Woods Run issue to X through Buffer.

The script is intentionally conservative:
- it discovers the connected X channel rather than hard-coding an account ID;
- it waits for the dated issue page and social card to be live on GitHub Pages;
- it verifies the issue page points to the correct dated social card;
- it checks Buffer for an existing post containing the same dated URL before publishing;
- it publishes immediately with Buffer's automatic publishing mode.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BUFFER_API = "https://api.buffer.com"
SITE_ROOT = "https://woodsrun.forestenterprise.org"
TARGET_SERVICE = "twitter"
TARGET_NAME = "ForestBizSchool"
MAX_X_TEXT = 280
WAIT_ATTEMPTS = 30
WAIT_SECONDS = 10


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
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail(f"Buffer HTTP {exc.code}: {body}")
    except Exception as exc:
        fail(f"Buffer request failed: {exc}")

    if result.get("errors"):
        fail(f"Buffer GraphQL error: {json.dumps(result['errors'])}")
    return result.get("data", {})


def get_organization_id() -> str:
    data = graphql(
        "query GetOrganizations { account { organizations { id name } } }"
    )
    organizations = data.get("account", {}).get("organizations", [])
    if not organizations:
        fail("No Buffer organization found")
    organization = organizations[0]
    print(f"Buffer organization: {organization.get('name', '(unnamed)')}")
    return organization["id"]


def get_x_channel(organization_id: str) -> dict:
    query = """
    query GetChannels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) {
        id
        name
        service
      }
    }
    """
    data = graphql(query, {"organizationId": organization_id})
    channels = data.get("channels", [])
    twitter_channels = [c for c in channels if c.get("service") == TARGET_SERVICE]
    exact = [
        c for c in twitter_channels
        if (c.get("name") or "").casefold() == TARGET_NAME.casefold()
    ]
    if len(exact) == 1:
        channel = exact[0]
    elif len(twitter_channels) == 1:
        channel = twitter_channels[0]
    elif not twitter_channels:
        fail("No X/Twitter channel is connected in Buffer")
    else:
        names = ", ".join(c.get("name", "(unnamed)") for c in twitter_channels)
        fail(f"Multiple X channels found and none uniquely matched {TARGET_NAME}: {names}")

    print(f"Target X channel: {channel.get('name')} [{channel.get('id')}]")
    return channel


def load_latest_issue() -> dict:
    path = Path("data/issues.json")
    if not path.exists():
        fail("data/issues.json is missing")
    issues = json.loads(path.read_text(encoding="utf-8"))
    if not issues:
        fail("data/issues.json contains no issues")
    issue = issues[0]
    for field in ("date", "displayDate", "url", "summary"):
        if not issue.get(field):
            fail(f"Latest issue is missing required field: {field}")
    return issue


def issue_urls(issue: dict) -> tuple[str, str]:
    page_url = SITE_ROOT + issue["url"]
    card_url = f"{SITE_ROOT}/assets/cards/{issue['date']}.png"
    return page_url, card_url


def fetch_public(url: str) -> tuple[int, bytes, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "WoodsRunDigest/1.0 (+site-publish-check)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.read(), response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, b"", exc.headers.get("Content-Type", "")
    except Exception:
        return 0, b"", ""


def wait_until_live(page_url: str, card_url: str) -> None:
    print(f"Waiting for public issue: {page_url}")
    for attempt in range(1, WAIT_ATTEMPTS + 1):
        page_status, page_body, _ = fetch_public(page_url)
        card_status, card_body, card_type = fetch_public(card_url)

        page_text = page_body.decode("utf-8", errors="replace") if page_body else ""
        has_card_meta = card_url in page_text
        has_large_card = bool(
            re.search(
                r'<meta[^>]+name=["\']twitter:card["\'][^>]+content=["\']summary_large_image["\']',
                page_text,
                flags=re.IGNORECASE,
            )
            or re.search(
                r'<meta[^>]+content=["\']summary_large_image["\'][^>]+name=["\']twitter:card["\']',
                page_text,
                flags=re.IGNORECASE,
            )
        )
        card_is_image = card_status == 200 and bool(card_body) and "image" in card_type.lower()

        if page_status == 200 and has_card_meta and has_large_card and card_is_image:
            print("Dated page and social card are live with the expected X metadata.")
            return

        print(
            f"Attempt {attempt}/{WAIT_ATTEMPTS}: page={page_status}, "
            f"card={card_status}, og-card={'yes' if has_card_meta else 'no'}, "
            f"large-card={'yes' if has_large_card else 'no'}"
        )
        if attempt < WAIT_ATTEMPTS:
            time.sleep(WAIT_SECONDS)

    fail("Timed out waiting for the dated issue page/social card to be deployed")


def recent_posts_contain_url(organization_id: str, channel_id: str, page_url: str) -> bool:
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
    for edge in data.get("posts", {}).get("edges", []):
        post = edge.get("node", {})
        if page_url in (post.get("text") or ""):
            print(f"Already present in Buffer ({post.get('status')}): {post.get('id')}")
            return True
    return False


def shorten_at_word(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    candidate = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return candidate + "…"


def compose_post(issue: dict, page_url: str) -> str:
    teaser = (issue.get("socialText") or issue.get("summary") or "").strip()
    teaser = teaser.rstrip()
    # Leave generous room for the URL and line break. X ultimately t.co-wraps links,
    # but keeping the literal payload under 280 avoids scheduler-side surprises.
    allowance = MAX_X_TEXT - len(page_url) - 2
    teaser = shorten_at_word(teaser, allowance)
    text = f"{teaser}\n\n{page_url}"
    if len(text) > MAX_X_TEXT:
        fail(f"Composed X post is too long ({len(text)} characters)")
    return text


def publish(channel_id: str, text: str) -> dict:
    mutation = """
    mutation PublishWoodsRun($input: CreatePostInput!) {
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
                "source": "woods-run-digest",
            }
        },
    )
    payload = data.get("createPost") or {}
    if payload.get("message"):
        fail(f"Buffer rejected the post: {payload['message']}")
    post = payload.get("post")
    if not post:
        fail(f"Unexpected Buffer createPost response: {json.dumps(payload)}")
    return post


def main() -> None:
    issue = load_latest_issue()
    page_url, card_url = issue_urls(issue)
    print(f"Latest Woods Run issue: {issue['displayDate']}")

    organization_id = get_organization_id()
    channel = get_x_channel(organization_id)

    wait_until_live(page_url, card_url)

    if recent_posts_contain_url(organization_id, channel["id"], page_url):
        print("No action needed; this dated issue has already been sent to X through Buffer.")
        return

    text = compose_post(issue, page_url)
    print("Publishing Woods Run to X through Buffer:")
    print(text)
    post = publish(channel["id"], text)
    print(
        f"Buffer accepted post {post.get('id')} with status {post.get('status')}. "
        f"External link: {post.get('externalLink') or '(pending)'}"
    )


if __name__ == "__main__":
    main()
