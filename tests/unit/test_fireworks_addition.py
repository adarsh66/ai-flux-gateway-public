"""Synthetic and actual-render contracts, never live inference acceptance."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from aiflux.display_pricing import catalog_price, detail_estimates, manifest
from aiflux.models import Base, UsageRecord
from scripts.deployment import fireworks_release as release
from scripts.deployment import runtime_rollout as rt

ROOT = rt.ROOT
spec = importlib.util.spec_from_file_location('fireworks_approved_catalog', ROOT / 'services/usage-ingestion/approved_catalog.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def candidate():
    return json.loads(release.MANIFEST.read_text())


def test_candidate_is_additive_not_accepted():
    release.manifest_guard(candidate(), json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text()))
    accepted = json.loads((ROOT / 'gateway/catalog/foundry-inventory-20261026.json').read_text())
    new_routes = [r for r in accepted['routes'] if r['alias'] in release.NEW]
    assert {r['alias'] for r in new_routes} in (set(), set(release.NEW))
    assert all(r['gateway_validated'] and r['upstream_token_parameter'] == 'max_tokens'
               and r['endpoint_url'] == release.URL for r in new_routes)
    assert len(candidate()['routes']) == 12


def test_live_sku_precondition_has_exported_sku():
    text = (ROOT / 'infra/project-route/main.tf').read_text()
    block = text.split('data "azapi_resource" "route_deployment" {', 1)[1].split('\n}', 1)[0]
    assert 'response_export_values = ["properties", "sku"]' in block


def test_corrected_attempt_never_reuses_failed_plan():
    assert release.HOME != release.FAILED_HOME
    assert release.HOME.name == 'fireworks-models-20261028-formatted'


@pytest.mark.parametrize('defect', ['version', 'provider', 'upstream_url', 'model_name', 'token_parameter', 'old_route'])
def test_candidate_rejects_contract_or_predecessor_drift(defect):
    data = candidate()
    data['routes']['gpt-4o' if defect == 'old_route' else 'FW-GLM-5.3'][
        'version' if defect == 'old_route' else defect] = 'foreign'
    with pytest.raises(RuntimeError):
        release.manifest_guard(data, json.loads((ROOT / 'gateway/catalog/project-routes.json').read_text()))


def expanded_fixture(tmp_path):
    for path in ('gateway/catalog/foundry-inventory-20261026.json', 'gateway/catalog/external-inventory.json',
                 'services/usage-ingestion/catalog-bindings.json'):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    (tmp_path / 'gateway/catalog/project-routes.json').write_text(json.dumps(candidate()))
    bindings_path = tmp_path / 'services/usage-ingestion/catalog-bindings.json'
    bindings = json.loads(bindings_path.read_text())
    bindings['fireworks'] = {'url': release.URL, 'region': 'eastus'}
    bindings_path.write_text(json.dumps(bindings))
    path = tmp_path / 'gateway/catalog/foundry-inventory-20261026.json'
    data = json.loads(path.read_text())
    data['routes'] = [r for r in data['routes'] if r['alias'] not in release.NEW]
    data['deployments'] = [d for d in data['deployments'] if d['name'] not in release.NEW]
    for alias, (version, sku) in release.NEW.items():
        deployment = deepcopy(data['deployments'][1])
        deployment.update(id=data['account_resource_id'] + '/deployments/' + alias, name=alias,
                          model_name=alias, model_format='Fireworks', model_version=version, sku=sku)
        data['deployments'].append(deployment)
        route = deepcopy(data['routes'][0])
        route.update(alias=alias, deployment_id=deployment['id'], backend_model=alias, model_name=alias,
                     model_version=version, endpoint_url=release.URL, gateway_validated=True)
        data['routes'].append(route)
    path.write_text(json.dumps(data))
    return path, data


def test_reviewed_thirteen_plus_disabled_decision(tmp_path):
    expanded_fixture(tmp_path)
    result = builder.build(tmp_path)
    assert len([m for m in result['models'] if m['enabled']]) == 13
    assert {m['provider'] for m in result['models'] if m['id'] in release.NEW} == {'Fireworks'}
    assert next(m for m in result['models'] if m['id'] == 'glm-5.3')['provider'] == 'ModelArts'
    assert next(m for m in result['models'] if m['id'] == 'Decision-1')['enabled'] is False


@pytest.mark.parametrize('defect', ['pending', 'sku', 'provider', 'version', 'endpoint', 'model_name', 'partial'])
def test_new_catalog_rejects_pending_or_mismatched_evidence(tmp_path, defect):
    path, data = expanded_fixture(tmp_path)
    if defect == 'pending':
        data['routes'][-1]['gateway_validated'] = False
    elif defect == 'sku':
        data['deployments'][-1]['sku'] = 'GlobalStandard'
    elif defect == 'provider':
        data['deployments'][-1]['model_format'] = 'ModelArts'
    elif defect == 'version':
        data['routes'][-1]['model_version'] = '2'
    elif defect == 'endpoint':
        data['routes'][-1]['endpoint_url'] = candidate()['upstream_url']
    elif defect == 'model_name':
        data['routes'][-1]['model_name'] = 'glm-5.3'
    else:
        project_path = tmp_path / 'gateway/catalog/project-routes.json'
        project = json.loads(project_path.read_text())
        project['routes'].pop('FW-MiniMax-M3')
        project_path.write_text(json.dumps(project))
    path.write_text(json.dumps(data))
    with pytest.raises(AssertionError):
        builder.build(tmp_path)


@pytest.mark.parametrize('alias', list(release.NEW))
def test_unknown_fireworks_never_inherits_modelarts_price_or_writes_financials(alias):
    from datetime import UTC, datetime
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    assert catalog_price(alias, 'Fireworks', 'eastus') is None
    rate = next(r for r in manifest()['rates'] if r['model'] == alias)
    assert rate['status'] == 'unknown' and 'input' not in rate and 'output' not in rate
    with Session(engine) as db:
        row = UsageRecord(id=alias, organization_id='org', subscription_id='sub', model=alias,
                          provider='Fireworks', region='eastus', occurred_at=datetime.now(UTC),
                          input_tokens=25, output_tokens=52, cost=None, currency=None,
                          status_code=200, completeness='price_missing')
        db.add(row)
        db.flush()
        assert detail_estimates(db, [alias])[alias]['estimated_cost_usd'] is None
        assert db.scalar(select(UsageRecord)).cost is None and not db.dirty


@pytest.fixture(scope='module')
def renders():
    if not Path(rt.TF).exists():
        pytest.skip('installed Terraform required for real rendering')
    values = {}
    for key, path in [('old', ROOT / 'gateway/catalog/project-routes.json'), ('new', release.MANIFEST)]:
        command = [rt.TF, '-chdir=' + str(ROOT / 'infra/project-route'), 'console', '-no-color',
                   '-var-file=' + str(rt.HOME / 'product-subscription-access-20261027/inputs.tfvars.json'),
                   '-var=route_manifest_path=' + path.as_posix()]
        proc = subprocess.run(command, input='jsonencode({policy=local.policy,backends=local.route_backends})\n',
                              capture_output=True, text=True, env=rt.ENV, timeout=120)
        assert proc.returncode == 0, 'Terraform render failed'
        values[key] = json.loads(json.loads(proc.stdout[proc.stdout.find('"'):].strip()))
    return values


def test_actual_render_has_exact_new_mapping_and_no_path_duplication(renders):
    value = renders['new']
    assert {k for k, v in value['backends'].items() if v == 'aiflux-project-fireworks'} == set(release.NEW)
    assert all(v == 'aiflux-project-gpt-5-6-luna' for k, v in value['backends'].items() if k not in release.NEW)
    tree = ET.fromstring(value['policy'])
    assert not tree.findall('.//retry') and not tree.findall('.//include-fragment')
    assert len(tree.findall('.//forward-request')) == 1
    assert len(tree.findall('.//llm-content-safety')) == 3
    assert all(n.get('template') == '/chat/completions' for n in tree.findall('.//rewrite-uri'))
    assert 'Decision-1' not in value['policy']


@pytest.mark.parametrize('tag', ['cors', 'quota-by-key', 'rate-limit-by-key', 'llm-token-limit',
                                'llm-content-safety', 'send-request', 'forward-request'])
def test_actual_render_preserves_old_security_and_counters(renders, tag):
    structural = lambda key: [release.policy_structure(ET.tostring(n, encoding='unicode'))
                             for n in ET.fromstring(renders[key]['policy']).findall('.//' + tag)]
    assert structural('old') == structural('new')