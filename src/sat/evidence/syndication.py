"""Syndication detection: cluster evidence items by source domain.

@decision DEC-SYNDICATION-001
@title Domain-based syndication clustering for evidence deconfliction
@status accepted
@rationale Multiple outlets syndicate AP/Reuters/AFP wire stories. When 10 outlets
publish the same AP story, the system sees 10 "independent" sources, inflating
confidence. Clustering by domain family detects this pattern. The cluster summary
is injected into technique prompts (Quality of Information Check and ACH) so
analysts and LLMs can weight evidence from clustered sources appropriately.
Wire service detection is based on a fixed set of known wire domains; domain
clustering uses registrable domain comparison (www. stripped).
The summary is appended to technique evidence text, keeping all technique
implementations unmodified — only the evidence preparation step changes.
"""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

# Known wire services / syndication networks.
# These domains often republish stories to hundreds of outlets simultaneously.
WIRE_SERVICES: frozenset[str] = frozenset(
    {
        "apnews.com",
        "ap.org",
        "reuters.com",
        "afp.com",
    }
)


def extract_domain(url: str) -> str:
    """Extract the registrable domain from a URL, stripping www. prefix.

    Args:
        url: A URL string (http/https or bare domain).

    Returns:
        The hostname with www. prefix removed, or empty string on failure.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        # Strip www. prefix so www.apnews.com and apnews.com cluster together
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def cluster_by_domain(items: list) -> dict[str, list[str]]:
    """Group evidence item_ids by their source domain.

    Only domains with 2 or more items are returned — single items cannot
    constitute a syndication cluster.

    Args:
        items: List of EvidenceItem objects (must have source_urls and item_id).

    Returns:
        dict mapping domain -> [item_id, ...] for domains with 2+ items.
        item_ids may appear more than once per domain if the item has multiple
        URLs from that domain.
    """
    domain_items: dict[str, list[str]] = defaultdict(list)
    for item in items:
        seen_domains: set[str] = set()
        for url in getattr(item, "source_urls", []):
            domain = extract_domain(url)
            if domain and domain not in seen_domains:
                domain_items[domain].append(item.item_id)
                seen_domains.add(domain)
    # Only return clusters with 2+ items (single items aren't syndication)
    return {d: ids for d, ids in domain_items.items() if len(ids) >= 2}


def detect_wire_service_items(items: list) -> list[str]:
    """Identify evidence items sourced from known wire services.

    An item is flagged if any of its source_urls resolves to a wire service
    domain. Each item_id appears at most once in the result even if it has
    multiple wire service URLs.

    Args:
        items: List of EvidenceItem objects.

    Returns:
        List of item_ids that are sourced from known wire services.
    """
    wire_items: list[str] = []
    for item in items:
        for url in getattr(item, "source_urls", []):
            domain = extract_domain(url)
            if domain in WIRE_SERVICES:
                wire_items.append(item.item_id)
                break  # Count each item once
    return wire_items


def build_syndication_summary(items: list) -> str:
    """Build a human-readable syndication warning for technique prompts.

    Returns an empty string if no syndication is detected. Otherwise returns
    a warning suitable for appending to technique evidence text.

    Wire service warning fires when any item is from AP/Reuters/AFP/etc.
    Domain cluster listing fires when a non-wire domain has 3+ items.

    Args:
        items: List of EvidenceItem objects.

    Returns:
        Multi-line warning string, or empty string if no syndication detected.
    """
    clusters = cluster_by_domain(items)
    wire_items = detect_wire_service_items(items)

    if not clusters and not wire_items:
        return ""

    parts: list[str] = []

    if wire_items:
        parts.append(
            f"SYNDICATION WARNING: {len(wire_items)} evidence item(s) originate from wire "
            "services (AP, Reuters, AFP). These are often republished by multiple outlets — "
            "treat as a single source, not multiple independent confirmations."
        )

    # Only list domains with 3+ items to avoid noise from routine two-source corroboration
    multi_domain = {d: ids for d, ids in clusters.items() if len(ids) >= 3}
    if multi_domain:
        for domain, ids in sorted(multi_domain.items(), key=lambda x: -len(x[1])):
            parts.append(f"  - {domain}: {len(ids)} items share this source domain")

    return "\n".join(parts)
