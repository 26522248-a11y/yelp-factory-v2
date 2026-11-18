"""Pool integrity audit (2026-11-09 + batch 2): metro/ASN/proxy binding, derived trust,
and cross-account cluster detection.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from db.models import Account, Profile, Proxy, ReviewAttempt, Assignment
from db.session import session_scope


def pool_audit(*, trust_threshold: int = 75) -> dict:
    issues: list[dict] = []
    with session_scope() as session:
        profiles = {p.id: p for p in session.query(Profile).all()}
        proxies = {p.id: p for p in session.query(Proxy).all()}
        accounts = session.query(Account).all()

        asn_by_metro: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        accounts_no_metro = 0
        accounts_no_proxy = 0
        for account in accounts:
            if account.metro_id is None:
                accounts_no_metro += 1
                continue
            profile = profiles.get(account.profile_id) if account.profile_id else None
            proxy = proxies.get(profile.proxy_id) if profile and profile.proxy_id else None
            if proxy is None or not proxy.asn:
                accounts_no_proxy += 1
                issues.append({"kind": "proxy_asn_missing", "account": str(account.id), "email": account.email})
                continue
            asn_by_metro[str(account.metro_id)][proxy.asn].append(str(account.id))

        for metro_id, by_asn in asn_by_metro.items():
            for asn, ids in by_asn.items():
                if len(ids) > 1:
                    issues.append({"kind": "asn_shared_in_metro", "metro": metro_id, "asn": asn, "accounts": ids})

        low_trust = 0
        for account in accounts:
            if account.state in ("READY", "ACTIVE"):
                from core.trust import compute_trust

                if compute_trust(account.id).score < trust_threshold:
                    low_trust += 1
                    issues.append({"kind": "trust_below_review", "account": str(account.id), "email": account.email})

        # batch 2: cross-account cluster detection
        cluster_issues = _detect_review_clusters(session)
        issues.extend(cluster_issues)

    return {
        "accounts": len(accounts),
        "no_metro": accounts_no_metro,
        "no_proxy_asn": accounts_no_proxy,
        "low_trust": low_trust,
        "issues": issues[:200],
        "ok": not issues,
    }


def _detect_review_clusters(session, *, days: int = 30, threshold: int = 3) -> list[dict]:
    """Detect accounts reviewing the same businesses in suspicious patterns.

    Cluster signal: 3+ accounts reviewed the same business within 30 days.
    This catches coordinated farms that rotate through the same target set.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent_reviews = (
        session.query(ReviewAttempt.business_id, ReviewAttempt.account_id, ReviewAttempt.created_at)
        .filter(ReviewAttempt.created_at >= cutoff)
        .all()
    )

    # Group by business_id
    by_business: dict[str, list[tuple[str, datetime]]] = defaultdict(list)
    for biz_id, acc_id, ts in recent_reviews:
        by_business[biz_id].append((str(acc_id), ts))

    clusters = []
    for biz_id, reviews in by_business.items():
        unique_accounts = set(acc_id for acc_id, _ in reviews)
        if len(unique_accounts) >= threshold:
            clusters.append({
                "kind": "review_cluster_detected",
                "business_id": biz_id,
                "accounts": sorted(unique_accounts),
                "count": len(reviews),
                "window_days": days,
            })

    return clusters[:50]  # cap at 50 clusters to avoid huge output
