"""Private successor11 function reuse with a source-bound12 transport.

Actual envelope02 supports bounded backends count; independent review precedes prepare.
No predecessor globals or frozen source files are modified.
"""
from pathlib import Path
from types import CodeType, FunctionType

from scripts.deployment import auto_resume11_parent as eleven
from scripts.deployment.auto_resume12_transport import Transport

ROOT = eleven.ROOT
HOME = ROOT / '.deployment/auto-resume12'
NEW = ('scripts/deployment/auto_resume12_parent.py',
       'scripts/deployment/auto_resume11_browser.js',
       'scripts/deployment/auto_resume12_transport.py',
       'scripts/deployment/auto_resume12_offline.py',
       'scripts/deployment/auto_resume12_diagnostic.py',
       'scripts/deployment/auto_resume12_evidence.py',
    'tests/unit/test_auto_resume12.py', 'docs/auto-resume12-handoff.md',
    'tests/unit/test_auto_resume12_stages.py', 'tests/auto_resume12_browser.test.mjs',
    '.deployment/auto-resume12/envelope02/result.json')
require, sha, load = eleven.require, eleven.sha, eleven.load


def frozen11():
    report = load(ROOT / '.deployment/auto-resume11/validation04/REPORT.json')
    require(report['status'] == 'OFFLINE_PASS', 'actual11_retained_validation')
    result = eleven.sources()
    require(result == report['sources'], 'immutable11_bound_bytes')
    return result


def sources():
    result = frozen11()
    result.update({name: sha((ROOT / name).read_bytes()) for name in NEW})
    return dict(sorted(result.items()))


def localcheck():
    prior = eleven.localcheck()
    retained = dict(prior['retained'])
    protected = [ROOT / '.deployment/auto-resume11', ROOT / '.deployment/auto-live02']
    protected.extend(HOME / label for label in ('validation01', 'validation02', 'validation03', 'envelope02'))
    for root in protected:
        for path in sorted(root.rglob('*')):
            eleven.ten.nine.safe(path)
            if path.is_file():
                retained[path.relative_to(ROOT).as_posix()] = sha(path.read_bytes())
    return {'sources': sources(), 'frozen': prior['frozen'], 'retained': retained,
            'authority': 'INTEGRITY_ONLY_NOT_APPROVAL'}


def envelope_evidence():
    path = HOME / 'envelope02/result.json'
    result = load(path)
    require(result['status'] == 'HTTP200_ENVELOPE_ONLY'
            and result['url'] == eleven.a.ARM.rstrip('/') + eleven.old.APIM + '/backends?api-version=2024-05-01'
            and result['key_types'] == {'count': 'int', 'value': 'list'}
            and result['count'] == result['row_count'] == 6 and result['nextLink'] is None
            and result['whole_rows_canonical_sha256'] ==
                'a077ddb740307d4084bc7f04df6d8cafeb948243935a569b5913b7293912819e',
            'actual12_envelope_evidence')
    return {'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path.read_bytes())}


def source_binding():
    return {**eleven.source_binding(), 'sources': localcheck()['sources'],
            'envelope': envelope_evidence(), 'manifest_schema': 12,
            'browser_template_schema': 11, 'emitted_browser_schema': 12}


_ns = dict(vars(eleven))
_ns.update(HOME=HOME, NEW=NEW, sources=sources, localcheck=localcheck, Transport=Transport)
_replacements = {'source11': 'source12', 'package11': 'package12',
    'successor11-author': 'successor12-author', 'successor11-': 'successor12-',
    'new11_package_scope': 'new12_package_scope',
    'scripts.deployment.auto_resume11_parent': 'scripts.deployment.auto_resume12_parent'}


def _code(code):
    def constant(value):
        if isinstance(value, CodeType): return _code(value)
        if isinstance(value, tuple): return tuple(constant(v) for v in value)
        if isinstance(value, frozenset): return frozenset(constant(v) for v in value)
        if type(value) is int and value == 11:
            return 12
        return _replacements.get(value, value) if isinstance(value, str) else value
    return code.replace(co_consts=tuple(constant(v) for v in code.co_consts))


for _name, _fn in vars(eleven).items():
    if isinstance(_fn, FunctionType) and _fn.__globals__ is vars(eleven):
        if _name not in ('sources', 'localcheck', 'source_binding', 'frozen10'):
            _ns[_name] = FunctionType(_code(_fn.__code__), _ns, _name, _fn.__defaults__, _fn.__closure__)
for _name, _value in _ns.items():
    if not _name.startswith('_'):
        globals().setdefault(_name, _value)
for _name, _value in list(globals().items()):
    if isinstance(_value, FunctionType) and _value.__globals__ is _ns:
        globals()[_name] = FunctionType(_value.__code__, globals(), _value.__name__,
                                      _value.__defaults__, _value.__closure__)
operation = eleven.ten.contextmanager(FunctionType(eleven.ten.operation.__wrapped__.__code__, globals(), 'operation'))
# main11 delegates through _base_main; bind the actual original dispatcher, not
# a closure/global reference that can resolve back to predecessor11 transport.
_base_main = FunctionType(_code(eleven._base_main.__code__), globals(), '_base_main',
                         eleven._base_main.__defaults__, eleven._base_main.__closure__)
_copied_prepare = prepare
_candidate_main = main
_copied_emit = emit


def emit(folder, digest, phase, clock=eleven.now):
    # The frozen11 standalone template stays byte-immutable. Adapt exactly its
    # protocol gate in the privately copied producer; no broader string rewrite.
    template = (ROOT / NEW[1]).read_text(encoding='utf-8').strip()
    require(template.count('request.schema === 11') == 1, 'frozen11_browser_schema_gate')
    original_put = put
    def write(target, name, value):
        if name == phase + '-tool.js':
            require(isinstance(value, bytes) and value.count(b'request.schema === 11') == 1,
                    'exact_browser_protocol_adapter')
            value = value.replace(b'request.schema === 11', b'request.schema === 12')
        return original_put(target, name, value)
    # Private function globals; never mutate production/frozen globals, even
    # temporarily. All other producer dependencies resolve through12.
    namespace = {**globals(), 'put': write}
    producer = FunctionType(_copied_emit.__code__, namespace, 'emit',
                            _copied_emit.__defaults__, _copied_emit.__closure__)
    return producer(folder, digest, phase, clock)


def main(argv=None):
    return _candidate_main(argv)


if __name__ == '__main__':
    import json
    print(json.dumps(main(), sort_keys=True))