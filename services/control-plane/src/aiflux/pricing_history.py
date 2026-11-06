"""Admin-only, detached historical drafts. No initialization or price writes.

External snapshots are bounded by *both* owner versions before calling the
existing resolver. Internal bundled defaults are not historical evidence.
Only immutable, hash-bound frozen baseline metadata can establish identity for
old internal entries which did not themselves store model version/SKU.
"""
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from aiflux import external_pricing as external, rate_card
from aiflux.auth import Principal
from aiflux.config import Settings
from aiflux.models import ExternalPriceCardRevision, GatewaySettings, GatewaySettingsRevision, Organization


class HistoryPoint(BaseModel):
    id: str
    source: str
    effective_at: datetime
    reason: str | None = None
    internal_version: int | None = None
    default_version: int | None = None
    organization_version: int | None = None
    simultaneous: bool = False


class HistoryPage(BaseModel):
    items: list[HistoryPoint]
    total: int
    next_offset: int | None = None


class HistoricalRow(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    canonical_model: str
    provider: str
    region: str
    model_version: str | None = None
    sku: str | None = None
    model_kind: Literal['chat', 'scoring'] = 'chat'
    billing_dimensions: list[str] = Field(default_factory=lambda: ['input', 'output'])
    state: Literal['known', 'unknown', 'unavailable']
    input: str | None = None
    output: str | None = None
    cached: str | None = None
    write: str | None = None
    note: str | None = None


class HistoryDetail(BaseModel):
    source: HistoryPoint
    items: list[HistoricalRow]
    skipped: list[str]
    current_version: int
    requires_acknowledgement: bool


def _admin(principal: Principal) -> None:
    external._admin(principal)


def _time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError('Missing effective timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return external._utc(parsed)  # Reject naive/malformed historical timestamps.


def _data(raw: str, member: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate historical field')
            result[key] = value
        return result
    data = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(data, dict) or data.get('schema') != 1 or not isinstance(data.get(member), list):
        raise ValueError('Unsupported historical document')
    return data


def _identity(raw: dict) -> tuple:
    return tuple(raw.get(k) for k in ('model', 'provider', 'region', 'model_version', 'sku')) + (
        raw.get('model_kind', 'chat'), tuple(raw.get('billing_dimensions', ['input', 'output'])))


def _vector(raw: dict, scoring: bool, unknown: bool = False) -> dict:
    if unknown:
        if any(raw.get(f) is not None for f in rate_card.FIELDS):
            raise ValueError('Unknown history contains prices')
        return {f: None for f in rate_card.FIELDS}
    if raw.get('input') is None or (not scoring and raw.get('output') is None):
        raise ValueError('Incomplete historical vector')
    if scoring and any(raw.get(f) is not None for f in ('output', 'cached', 'write')):
        raise ValueError('Invalid scoring history')
    return {f: rate_card.fmt(rate_card.parse_rate(raw[f])) if raw.get(f) is not None else None
            for f in rate_card.FIELDS}


def _external_rows(db: Session, organization_id: str | None):
    owner = external._owner(organization_id)
    if organization_id is not None and db.get(Organization, organization_id) is None:
        raise HTTPException(404, 'Organization not found')
    rows = db.scalars(select(ExternalPriceCardRevision).where(
        ExternalPriceCardRevision.owner.in_({'default', owner}),
    ).order_by(ExternalPriceCardRevision.owner, ExternalPriceCardRevision.version)
      .execution_options(autoflush=False)).all()
    # Validate selected owners only; never return raw delta/provenance/supplier data.
    for row in rows:
        data = _data(row.delta, 'entries')
        for raw in data['entries']:
            if not isinstance(raw, dict) or raw.get('operation') not in ('set', 'unknown', 'inherit'):
                raise ValueError('Invalid historical operation')
            if not all(isinstance(raw.get(k), str) and raw[k] for k in ('model', 'provider', 'region')):
                raise ValueError('Invalid canonical history scope')
            if raw.get('model_kind', 'chat') not in ('chat', 'scoring'):
                raise ValueError('Invalid billing kind')
            _time(raw['valid_from'])
            if raw['operation'] == 'inherit':
                if row.owner == 'default' or any(raw.get(f) is not None for f in rate_card.FIELDS):
                    raise ValueError('Invalid inheritance history')
            else:
                _vector(raw, raw.get('model_kind') == 'scoring', raw['operation'] == 'unknown')
    return rows


def _external_points(rows, organization_id: str | None) -> list[HistoryPoint]:
    """Union default/org boundaries, including baseline's backdated raw events.

    Same-clock cross-owner commits have no provable order. Individual points
    exclude the other owner's same-clock revisions; a separately labelled joint
    bound includes the cohort, without inventing a serial commit order.
    """
    owner = external._owner(organization_id)
    boundaries = []
    for row in rows:
        times = {external._stored_time(row.effective_at)}
        times.update(_time(e['valid_from']) for e in _data(row.delta, 'entries')['entries'])
        for at in times:
            if at <= datetime.now(UTC):
                boundaries.append((at, row))
    points = []
    for at, row in boundaries:
        versions = {'default': 0, owner: 0}
        for other in rows:
            if external._stored_time(other.effective_at) < at:
                versions[other.owner] = max(versions[other.owner], other.version)
        # A baseline boundary belongs to its exact owning revision, not later
        # revisions with backdated valid_from entries or the same clock value.
        versions[row.owner] = row.version
        dv, ov = versions['default'], versions[owner] if owner != 'default' else 0
        same = owner != 'default' and any(r.owner != row.owner and external._stored_time(r.effective_at) == at for r in rows)
        source = 'default' if row.owner == 'default' else 'organization'
        token = f'd{dv}-o{ov}-{source}-{at.isoformat()}'
        points.append(HistoryPoint(id=token, source=source, effective_at=at, reason=row.reason,
                                   default_version=dv, organization_version=ov, simultaneous=same))
    # Joint bounds expose the complete same-clock cohort explicitly.
    for at in sorted({at for at, _ in boundaries}):
        cohort = [r for r in rows if external._stored_time(r.effective_at) == at]
        if owner == 'default' or {r.owner for r in cohort} != {'default', owner}:
            continue
        dv = max((r.version for r in rows if r.owner == 'default' and external._stored_time(r.effective_at) <= at), default=0)
        ov = max((r.version for r in rows if r.owner == owner and external._stored_time(r.effective_at) <= at), default=0)
        points.append(HistoryPoint(id=f'd{dv}-o{ov}-cohort-{at.isoformat()}', source='simultaneous cohort',
            effective_at=at, reason='Explicit joint bound; cross-owner commit order is unavailable',
            default_version=dv, organization_version=ov, simultaneous=True))
    unique = {p.id: p for p in points}
    return sorted(unique.values(), key=lambda p: (p.effective_at, p.default_version or 0,
                  p.organization_version or 0, p.source), reverse=True)


def _internal_rows(db: Session):
    return db.scalars(select(GatewaySettingsRevision).where(
        GatewaySettingsRevision.scope == rate_card.SCOPE,
        GatewaySettingsRevision.state == 'published',
    ).order_by(GatewaySettingsRevision.version.desc()).execution_options(autoflush=False)).all()


def _internal_entries(row):
    entries = _data(row.configuration, 'entries')['entries']
    seen = set()
    for raw in entries:
        if not isinstance(raw, dict) or not all(isinstance(raw.get(k), str) and raw[k]
                for k in ('model', 'provider', 'region', 'origin')):
            raise ValueError('Invalid internal history scope')
        at = _time(raw['valid_from'])
        key = (*rate_card.key_of(raw), at)
        if key in seen:
            raise ValueError('Ambiguous internal history')
        seen.add(key)
        # Identity may be unavailable, but malformed numbers must still fail closed.
        _vector(raw, raw.get('model_kind') == 'scoring' or raw['model'] == 'Decision-1')
    return entries


def _internal_points(rows):
    return [HistoryPoint(id=f'i{row.version}', source='internal', internal_version=row.version,
        effective_at=max((_time(e['valid_from']) for e in _internal_entries(row)),
                         default=external._stored_time(row.occurred_at)), reason=row.reason) for row in rows]


def _frozen_metadata(db: Session, row) -> dict:
    """No inference from today's packaged catalog; prove the selected config hash."""
    baseline = db.scalar(select(ExternalPriceCardRevision).where(
        ExternalPriceCardRevision.owner == 'default', ExternalPriceCardRevision.version == 1,
    ).execution_options(autoflush=False))
    if baseline is None:
        return {}
    data = _data(baseline.delta, 'entries')
    digest = hashlib.sha256(row.configuration.encode('utf-8')).hexdigest()
    proofs = data.get('provenance', {}).get('internal_revisions', [])
    if not data.get('baseline') or not any(p.get('version') == row.version and
            p.get('raw_configuration_sha256') == digest for p in proofs):
        return {}
    result = {}
    for raw in data['entries']:
        key = rate_card.key_of(raw)
        if key in result and _identity(result[key]) != _identity(raw):
            raise ValueError('Ambiguous frozen canonical identity')
        result[key] = raw
    return result


def _project(settings: Settings, historical: dict) -> tuple[list[HistoricalRow], list[str]]:
    items, used = [], set()
    for alias, scope in rate_card.listed_scopes(settings):
        key = rate_card.key_of(scope)
        raw = historical.get(key)
        common = dict(model=alias, canonical_model=key[0], provider=key[1], region=key[2],
                      model_kind=scope.get('model_kind', 'chat'),
                      billing_dimensions=scope.get('billing_dimensions', ['input', 'output']))
        if raw is None:
            items.append(HistoricalRow(**common, state='unavailable', note='No proven historical vector; current row stays unchanged'))
            continue
        used.add(key)
        if _identity(raw) != _identity(scope):
            items.append(HistoricalRow(**common, state='unavailable', note='Canonical identity changed or cannot be proven; current row stays unchanged'))
            continue
        unknown = raw.get('operation') == 'unknown'
        items.append(HistoricalRow(**common, model_version=raw['model_version'], sku=raw['sku'],
            state='unknown' if unknown else 'known', **_vector(raw, common['model_kind'] == 'scoring', unknown)))
    skipped = [f'{k[0]} ({k[1]} / {k[2]}): retired or unlisted scope' for k in sorted(historical.keys() - used)]
    return items, skipped


def history(db: Session, settings: Settings, principal: Principal, *, external_card: bool = False,
            organization_id: str | None = None, offset: int = 0, limit: int = 25,
            revision: str | None = None) -> HistoryPage | HistoryDetail:
    _admin(principal)  # Also enforced by routes; never resolve ownership before auth.
    try:
        with db.no_autoflush:
            if external_card:
                rows = _external_rows(db, organization_id)
                points = _external_points(rows, organization_id)
            else:
                rows = _internal_rows(db)
                points = _internal_points(rows)
            if revision is None:
                page = points[offset:offset + limit]
                return HistoryPage(items=page, total=len(points),
                    next_offset=offset + limit if offset + limit < len(points) else None)
            point = next((p for p in points if p.id == revision), None)
            if point is None:
                raise HTTPException(404, 'Historical pricing revision not found for this scope')
            historical = {}
            if external_card:
                owner = external._owner(organization_id)
                bounded = [r for r in rows if r.version <= (point.default_version if r.owner == 'default'
                           else point.organization_version)]
                context = external._context_from_revisions(bounded, organization_id, point.effective_at)
                for key in {external._key(e) for e in context._events}:
                    event = context._resolve(key, point.effective_at)
                    if event is not None:
                        historical[key] = event
                head = db.scalar(select(external.ExternalPriceCard).where(
                    external.ExternalPriceCard.owner == owner).execution_options(autoflush=False))
            else:
                row = next(r for r in rows if r.version == point.internal_version)
                frozen = _frozen_metadata(db, row)
                for raw in sorted(_internal_entries(row), key=lambda e: _time(e['valid_from'])):
                    key = rate_card.key_of(raw)
                    # Preserve vectors even for reset/default-origin entries; never
                    # substitute the current base because origin isn't configured.
                    historical[key] = {**{k: v for k, v in frozen.get(key, {}).items()
                                         if k not in (*rate_card.FIELDS, 'operation', 'valid_from')},
                                       **raw, 'operation': 'set'}
                head = db.scalar(select(GatewaySettings).where(GatewaySettings.scope == rate_card.SCOPE)
                                 .execution_options(autoflush=False))
            items, skipped = _project(settings, historical)
            return HistoryDetail(source=point, items=items, skipped=skipped,
                current_version=head.version if head else 0,
                requires_acknowledgement=bool(skipped or any(i.state == 'unavailable' for i in items)))
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise HTTPException(409, 'Historical pricing is malformed or unavailable; current prices were not substituted') from exc