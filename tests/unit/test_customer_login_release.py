from copy import deepcopy
import pytest
from scripts.deployment import customer_login_release as r

IMAGE = r.portals.HOST + '/aiflux-customer@sha256:' + 'b' * 64
OLD = 'aiflux-customer@sha256:' + r.PINS['customer']


def fixture():
    old = {'app_settings': {'preserved': 'yes'}, 'identity': {'type': 'UserAssigned'},
           'site_config': [{'always_on': True, 'application_stack': [{'docker_image_name': OLD,
                          'docker_registry_url': 'https://' + r.portals.HOST}]}]}
    new = deepcopy(old)
    new['site_config'][0]['application_stack'][0]['docker_image_name'] = IMAGE.split('/', 1)[1]
    p = {'applyable': True, 'checks': [{'status': 'pass'}], 'resource_changes': [
        {'address': r.ADDRESS, 'mode': 'managed', 'change': {'actions': ['update'], 'before': old, 'after': new, 'after_unknown': {}}}]}
    before = {'runtime': {'sites': {'customer': {'image': 'DOCKER|' + r.portals.HOST + '/' + OLD}}}}
    return p, before


def test_exact_customer_image():
    p, before = fixture()
    r.guard(p, IMAGE, before)


@pytest.mark.parametrize('mutation', ['settings', 'network', 'identity', 'always_on', 'api', 'create', 'unknown', 'checks', 'errored', 'mutable'])
def test_reject_unapproved_mutations(mutation):
    p, before = fixture()
    item = p['resource_changes'][0]
    c = item['change']
    image = IMAGE
    if mutation == 'settings': c['after']['app_settings']['preserved'] = 'no'
    if mutation == 'network': c['after']['public_network_access_enabled'] = True
    if mutation == 'identity': c['after']['identity'] = {}
    if mutation == 'always_on': c['after']['site_config'][0]['always_on'] = False
    if mutation == 'api': item['address'] = 'azurerm_linux_web_app.main["api"]'
    if mutation == 'create': c['actions'] = ['create']
    if mutation == 'unknown': c['after_unknown'] = {'app_settings': True}
    if mutation == 'checks': p['checks'][0]['status'] = 'unknown'
    if mutation == 'errored': p['errored'] = True
    if mutation == 'mutable': image = r.portals.HOST + '/aiflux-customer:latest'
    with pytest.raises(RuntimeError): r.guard(p, image, before)


def test_reject_duplicate_and_missing():
    p, before = fixture()
    p['resource_changes'] *= 2
    with pytest.raises(RuntimeError): r.guard(p, IMAGE, before)
    p['resource_changes'] = []
    with pytest.raises(RuntimeError): r.guard(p, IMAGE, before)


def test_fresh_name_only():
    with pytest.raises(RuntimeError): r.Release('../customer-catalog-release-20261028')