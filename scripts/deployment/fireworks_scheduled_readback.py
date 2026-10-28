"""Finite read-only Fireworks timer evidence; no trigger/configuration operations."""
import io
import json
import zipfile
from datetime import UTC, datetime

from scripts.deployment import finops_live_runtime as live
from scripts.deployment import finops_scheduled_diagnosis as schedule
from scripts.deployment import runtime_rollout as rt


def main():
    status, raw = live.request('/containerlogs/zip/download', 'POST')
    archive = zipfile.ZipFile(io.BytesIO(raw))
    rt.require(sum(f.file_size for f in archive.infolist()) <= 24_000_000, 'bounded_logs')
    combined = {'scheduled_starts': [], 'executions': []}
    expected_image_seen = False
    categories = set()
    for member in archive.infolist():
        if member.is_dir():
            continue
        text = archive.read(member).decode('utf-8', 'replace')
        expected_image_seen |= 'fad3faca72297752779b0ecddee05bf50a5504670ebc0b5a4222c7dddc6e8b90' in text
        parsed = live.summarize(text)
        for key in combined:
            combined[key].extend(parsed[key])
        categories.update(live.classify_failures(text))
    boundary = '2026-10-28T02:57:25.945420+00:00'
    result = {
        'at_utc': datetime.now(UTC).isoformat(),
        'read_only': True,
        'console_http_status': status,
        'expected_ingestion_image_seen_in_console': expected_image_seen,
        'scheduled_since_image_apply': schedule.scheduled_evidence(combined, boundary),
        'log_categories_historical_not_current_failure_assertions': sorted(categories),
        'manual_invocations': 0,
        'configuration_writes': 0,
    }
    host = rt.arm(live.RID + '/hostruntime/admin/host/status')
    result['host_status'] = {key: host.get(key) for key in ('state', 'version')}
    path = rt.ROOT / 'gateway/validation/fireworks-scheduled-runtime-20261028.json'
    rt.save(path, result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'readback_failed_detail_suppressed'}), flush=True)
        raise SystemExit(1)