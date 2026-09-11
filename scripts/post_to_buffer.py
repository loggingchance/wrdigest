#!/usr/bin/env python3
"""Publish the newest Woods Run issue to X and Instagram through Buffer.

The same dated Woods Run social card is used on both platforms. X receives the
normal teaser plus dated issue URL. Instagram receives a short caption directing
readers to the Woods Run link in the profile bio.
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
MAX_X_TEXT = 280
WAIT_ATTEMPTS = 30
WAIT_SECONDS = 10

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
    data = graphql("query GetOrganizations { account { organizations { id name } } }")
    organizations = data.get("account", {}).get("organizations", [])
    if not organizations:
        fail("No Buffer organization found")
    organization = organizations[0]
    print(f"Buffer organization: {organization.get('name', '(unnamed)')}")
    return organization["id"]


def get_channels(organization_id: str) -> list[dict]:
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
    return data.get("channels", [])


def select_channel(all_channels: list[dict], service: str, name: str, label: str) -> dict:
    matching = [c for c in all_channels if c.get("service") == service]
    exact = [c for c in matching if (c.get("name") or "").casefold() == name.casefold()]
    if len(exact) == 1:
        channel = exact[0]
    elif len(matching) == 1:
        channel = matching[0]
        print(f"{label}: expected {name!r}, using the only connected {service} channel {channel.get('name')!r}.")
    elif not matching:
        fail(f"No {label} channel is connected in Buffer")
    else:
        names = ", ".join(c.get("name", "(unnamed)") for c in matching)
        fail(f"Multiple {label} channels found and none uniquely matched {name}: {names}")
    print(f"Target {label} channel: {channel.get('name')} [{channel.get('id')}]")
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
            print("Dated page and social card are live with the expected metadata.")
            return

        print(
            f"Attempt {attempt}/{WAIT_ATTEMPTS}: page={page_status}, "
            f"card={card_status}, og-card={'yes' if has_card_meta else 'no'}, "
            f"large-card={'yes' if has_large_card else 'no'}"
        )
        if attempt < WAIT_ATTEMPTS:
            time.sleep(WAIT_SECONDS)

    fail("Timed out waiting for the dated issue page/social card to be deployed")


def recent_post_exists(
    organization_id: str,
    channel_id: str,
    service: str,
    page_url: str,
    card_url: str,
) -> bool:
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
        edges {
          node {
            id text status createdAt channelId externalLink
            assets { source mimeType }
          }
        }
      }
    }
    """
    data = graphql(query, {"organizationId": organization_id, "channelId": channel_id})
    for edge in data.get("posts", {}).get("edges", []):
        post = edge.get("node", {})
        text = post.get("text") or ""
        assets = post.get("assets") or []
        sources = {(asset.get("source") or "").strip() for asset in assets}
        if service == "twitter" and page_url in text:
            print(f"X already contains this issue ({post.get('status')}): {post.get('id')}")
            return True
        if service == "instagram" and card_url in sources:
            print(f"Instagram already contains this issue card ({post.get('status')}): {post.get('id')}")
            return True
    return False


def shorten_at_word(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    candidate = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return candidate + "…"


def compose_x_post(issue: dict, page_url: str) -> str:
    teaser = (issue.get("socialText") or issue.get("summary") or "").strip()
    allowance = MAX_X_TEXT - len(page_url) - 2
    teaser = shorten_at_word(teaser, allowance)
    text = f"{teaser}\n\n{page_url}"
    if len(text) > MAX_X_TEXT:
        fail(f"Composed X post is too long ({len(text)} characters)")
    return text


def compose_instagram_post(issue: dict) -> str:
    return (
        f"Woods Run Digest — {issue['displayDate']}\n\n"
        "Daily North American forestry & forest-products intelligence from The Forest Business School.\n\n"
        "Read today’s edition: link in bio.\n"
        "woodsrun.forestenterprise.org"
    )


def publish(channel_id: str, text: str, card_url: str, service: str) -> dict:
    mutation = """
    mutation PublishWoodsRun($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id text status dueAt externalLink assets { source mimeType } }
        }
        ... on MutationError { message }
      }
    }
    """
    post_input = {
        "text": text,
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow",
        "source": "woods-run-digest",
        "assets": [{"image": {"url": card_url}}],
    }
    if service == "instagram":
        post_input["metadata"] = {"instagram": {"type": "post", "shouldShareToFeed": True}}

    data = graphql(mutation, {"input": post_input})
    payload = data.get("createPost") or {}
    if payload.get("message"):
        fail(f"Buffer rejected the {service} post: {payload['message']}")
    post = payload.get("post")
    if not post:
        fail(f"Unexpected Buffer createPost response for {service}: {json.dumps(payload)}")
    assets = post.get("assets") or []
    if not assets:
        fail(f"Buffer accepted the {service} post but did not attach the social-card image")
    return post


def main() -> None:
    issue = load_latest_issue()
    page_url, card_url = issue_urls(issue)
    print(f"Latest Woods Run issue: {issue['displayDate']}")

    organization_id = get_organization_id()
    all_channels = get_channels(organization_id)
    selected = {
        target["service"]: select_channel(
            all_channels, target["service"], target["name"], target["label"]
        )
        for target in TARGETS
    }

    wait_until_live(page_url, card_url)

    texts = {
        "twitter": compose_x_post(issue, page_url),
        "instagram": compose_instagram_post(issue),
    }

    for target in TARGETS:
        service = target["service"]
        label = target["label"]
        channel = selected[service]

        if recent_post_exists(organization_id, channel["id"], service, page_url, card_url):
            print(f"No {label} action needed; this dated issue is already present.")
            continue

        print(f"Publishing Woods Run to {label} through Buffer with the dated social card attached:")
        print(texts[service])
        post = publish(channel["id"], texts[service], card_url, service)
        print(
            f"{label}: Buffer accepted post {post.get('id')} with status {post.get('status')} and "
            f"{len(post.get('assets') or [])} attached asset(s). "
            f"External link: {post.get('externalLink') or '(pending)'}"
        )


if __name__ == "__main__":
    main()
