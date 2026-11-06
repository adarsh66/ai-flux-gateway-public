"""Exact XML transport regression; stock C# alone cannot validate APIM format."""
import xml.etree.ElementTree as ET

import httpx
import pytest

from aiflux.apim import ApimClient, ApimError
from aiflux.config import Settings


def client():
    return ApimClient(Settings(_env_file=None,
        apim_resource_id='/subscriptions/00000000-0000-0000-0000-000000000000/'
            'resourceGroups/test/providers/Microsoft.ApiManagement/service/test',
        gateway_settings_scopes=['dev-unified'], gateway_controls_poc_enabled=True))


def test_xml_encoded_csharp_expression_is_not_submitted_as_rawxml(monkeypatch):
    c = client()
    root = ET.Element('fragment')
    ET.SubElement(root, 'set-variable', name='price', value='@(@"{""input"":""0""}")')
    xml = ET.tostring(root, encoding='unicode')
    assert '&quot;' in xml
    calls = []
    def send(method, url, body=None, etag=None):
        calls.append((method, url, body, etag))
        return httpx.Response(200, json={'properties': {'provisioningState': 'Succeeded'}},
                              headers={'ETag': '"next"'})
    monkeypatch.setattr(c, '_send', send)
    c.put_settings_fragment('dev-unified', xml, '"before"')
    body = calls[0][2]
    assert body['properties']['format'] == 'xml'
    assert body['properties']['value'] == xml
    assert ET.fromstring(body['properties']['value'])[0].get('value') == '@(@"{""input"":""0""}")'
    assert calls[0][3] == '"before"'


@pytest.mark.parametrize('state', ['Failed', 'Canceled', 'Cancelled', 'InProgress'])
def test_exact_xml_in_failed_or_unready_resource_is_not_success(monkeypatch, state):
    c = client()
    desired = '<fragment><set-variable name="x" value="@(1)" /></fragment>'
    responses = iter([httpx.Response(200, headers={'Location': c._fragment_url('dev-unified') + '&asyncId=abc&asyncCode=200'}),
        *[httpx.Response(200, json={'properties': {'value': desired, 'provisioningState': state}},
                        headers={'ETag': '"next"'}) for _ in range(12)]])
    calls = []
    def send(method, url, *args):
        calls.append((method, url))
        return next(responses)
    monkeypatch.setattr(c, '_send', send)
    monkeypatch.setattr('aiflux.apim.time.sleep', lambda _: None)
    with pytest.raises(ApimError):
        c.put_settings_fragment('dev-unified', desired, '"before"')
    assert sum(method == 'PUT' for method, _ in calls) == 1
    assert all('/policyFragments/' in url for _, url in calls)


def test_basicv2_signed_operation_uses_only_exact_fragment_readiness(monkeypatch):
    c = client()
    resource = c._fragment_url('dev-unified')
    operation = resource.split('/policyFragments/', 1)[0] + '/entityOperationResults/6ae702aededbcc0fdc6a09e8?api-version=2024-05-01&t=1&c=synthetic'
    desired = '<fragment><set-variable name="x" value="@(&quot;json&quot;)" /></fragment>'
    responses = iter([httpx.Response(200, headers={'Azure-AsyncOperation': operation}),
        httpx.Response(200, json={'properties': {'value': desired, 'provisioningState': 'Succeeded'}},
                       headers={'ETag': '"next"'})])
    calls = []
    def send(method, url, *args):
        calls.append((method, url))
        return next(responses)
    monkeypatch.setattr(c, '_send', send)
    c.put_settings_fragment('dev-unified', desired, '"before"')
    assert calls == [('PUT', resource), ('GET', resource + '&format=xml')]
    assert c.get_settings_fragment.__name__ == 'get_settings_fragment'