"""Exclusive offline validation/report runner. Never prepare or live transport.

This process denies non-loopback socket connections and external subprocesses
except explicitly installed Node/.NET used for offline tests/compilation.
"""
from __future__ import annotations
import io
import json
from pathlib import Path
import socket
import subprocess
import sys
import unittest

from scripts.deployment import auto_resume06_parent as p


def native(folder: Path) -> dict:
    # csc does not create its output directory. Reserve it before invocation;
    # never reuse an earlier compile receipt or overwrite an existing binary.
    p.safe(folder)
    folder.mkdir(parents=True, exist_ok=False)
    dotnet = Path('C:/Program Files/dotnet')
    sdk = dotnet / 'sdk/10.0.303'
    roslyn = sdk / 'Roslyn/bincore'
    references = sorted((dotnet / 'packs/Microsoft.NETCore.App.Ref').iterdir())[-1] / 'ref/net10.0'
    runtime = sorted((dotnet / 'shared/Microsoft.NETCore.App').iterdir())[-1]
    newtonsoft = sdk / 'Newtonsoft.Json.dll'
    def command(name, argv):
        value = subprocess.run(argv, capture_output=True, timeout=90)
        p.exclusive(folder / (name + '.stdout.txt'), value.stdout)
        p.exclusive(folder / (name + '.stderr.txt'), value.stderr)
        p.exclusive(folder / (name + '-result.json'), {'argv': argv, 'exit_code': value.returncode})
        return value
    dll = folder / 'Resume06Native.dll'
    result = command('compile', [str(dotnet / 'dotnet.exe'), str(roslyn / 'csc.dll'), '-nologo', '-target:exe',
        '-out:' + str(dll), *['-r:' + str(path) for path in references.glob('*.dll')],
        *['-r:' + str(roslyn / name) for name in ('Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll')],
        str(p.ROOT / 'scripts/deployment/auto_resume06_native.cs')])
    if result.returncode:
        return {'compile_exit': result.returncode, 'semantic_exit': None}
    for name in ('Microsoft.CodeAnalysis.dll', 'Microsoft.CodeAnalysis.CSharp.dll'):
        p.exclusive(folder / name, (roslyn / name).read_bytes())
    p.exclusive(folder / 'Resume06Native.runtimeconfig.json', {'runtimeOptions': {
        'tfm': 'net10.0', 'framework': {'name': 'Microsoft.NETCore.App', 'version': runtime.name}}})
    retained, frozen = p.old.retained()
    values = [(retained / name).read_bytes() for name in ('global-actual.xml', 'revision-2-actual.xml', 'active-actual.xml')]
    rendered = p.render.render(*values, dict(zip(('global', 'owned', 'explicit'), map(p.render.sha, values))),
        '2026-10-31T12:00:00Z', '2026-10-31T12:30:00Z', 'c' * 32, p.auto_inputs())
    expressions = []
    # Include the unchanged current22 active policy, not only diagnostic writes.
    for name in ('global.xml', 'revision.xml', 'explicit.xml'):
        p.exclusive(folder / name, rendered[name])
        for node in p.render.tree(rendered[name], name == 'explicit.xml').iter():
            expressions.extend(value for value in node.attrib.values() if value.startswith('@'))
            if (node.text or '').startswith('@'):
                expressions.append(node.text)
    p.exclusive(folder / 'expressions.json', expressions)
    result = command('semantic', [str(dotnet / 'dotnet.exe'), str(dll), 'compile',
        str(folder / 'expressions.json'), str(references), str(newtonsoft)])
    inputs = [dotnet / 'dotnet.exe', roslyn / 'csc.dll', roslyn / 'csc.deps.json',
        roslyn / 'csc.runtimeconfig.json', newtonsoft,
        p.ROOT / 'scripts/deployment/auto_resume06_native.cs', *references.glob('*.dll'),
        *roslyn.glob('*.dll')]
    outputs = [path for path in folder.iterdir() if path.is_file()]
    p.exclusive(folder / 'build-provenance.json', {'schema': 1,
        'inputs': {str(path): p.render.sha(path.read_bytes()) for path in inputs},
        'outputs': {str(path): p.render.sha(path.read_bytes()) for path in outputs},
        'compile_exit': 0, 'semantic_exit': result.returncode, 'expressions': len(expressions)})
    return {'compile_exit': 0, 'semantic_exit': result.returncode, 'expressions': len(expressions),
        'newtonsoft_sha256': p.render.sha(newtonsoft.read_bytes()),
        'fixture': 'typed_APIM_contract_full_Newtonsoft_not_service_acceptance'}


def main():
    folder = p.HOME / sys.argv[1]
    p.a.require(not folder.exists(), 'new_exclusive_validation_directory')
    folder.mkdir(parents=True, exist_ok=False)
    before = p.sources()
    p.exclusive(folder / 'full-source-hashes-before.json', before)
    protected = {name: digest for name, digest in before.items() if name not in p.NEW}
    p.exclusive(folder / 'immutable-before.json', protected)
    def deny(event, args):
        if event == 'socket.connect':
            address = args[1]
            if isinstance(address, tuple) and address[0] not in ('127.0.0.1', '::1'):
                raise RuntimeError('OFFLINE_EXTERNAL_NETWORK_DENIED')
        if event == 'socket.getaddrinfo' and args[0] not in ('127.0.0.1', '::1', None):
            raise RuntimeError('OFFLINE_EXTERNAL_DNS_DENIED')
        if event == 'subprocess.Popen':
            # Windows passes executable=None and a fully quoted command line.
            command = str(args[1]).lower().replace('\\', '/')
            executable = str(args[0]).lower().replace('\\', '/')
            allowed = executable in ('node', 'c:/program files/dotnet/dotnet.exe')
            allowed = allowed or (args[0] is None and (command.startswith('node ')
                or command.startswith('"c:/program files/dotnet/dotnet.exe" ')))
            p.a.require(allowed, 'OFFLINE_SUBPROCESS_DENIED')
    sys.addaudithook(deny)
    suite = unittest.defaultTestLoader.discover(str(p.ROOT / 'tests/unit'), pattern='test_auto_resume06.py')
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    p.exclusive(folder / 'python-tests.txt', stream.getvalue().encode())
    node = subprocess.run(['node', '--test', str(p.ROOT / 'tests/auto_resume06_browser.test.mjs')],
        capture_output=True, timeout=60)
    p.exclusive(folder / 'browser-tests.stdout.txt', node.stdout)
    p.exclusive(folder / 'browser-tests.stderr.txt', node.stderr)
    native_result = native(folder / 'native')
    after = p.sources()
    changed = [name for name, digest in protected.items() if after.get(name) != digest]
    p.exclusive(folder / 'full-source-hashes-after.json', after)
    prior = p.old.load(p.ROOT / '.deployment/auto-resume07/validation01/source-hashes-before.json')
    frozen_changed = [name for name, digest in prior.items() if name not in p.NEW and after.get(name) != digest]
    _, frozen = p.old.retained()
    original_changed = [name for name, digest in frozen['current280_sources'].items()
        if p.render.sha((p.ROOT / name).read_bytes()) != digest]
    report = {'scope': 'IMPLEMENTED_CAPABILITIES_MOCK_TESTED_NOT_LIVE', 'task_complete': False,
        'independent_source_review': 'NEXT_REQUIRED_NOT_SELF_APPROVED',
        'source_count': len(after), 'source_hashes': after, 'protected_count': len(protected),
        'protected_changed': changed, 'original280_count': 280,
        'resume07_protected_changed': frozen_changed, 'original280_changed': original_changed,
        'tests': {'count': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
            'skipped': len(result.skipped), 'browser_exit': node.returncode}, 'native': native_result,
        'live_prepare_calls': 0, 'cloud_reads': 0, 'cloud_mutations': 0, 'paid_calls': 0,
        'budget_remaining': {'isolated_score': 1, 'Auto_chats': 2, 'completion': 0, 'retries': 0},
        'remaining': ['parent assigns independent actual source audit; NOT self-approved',
            'parent pins actual reviewer identity/allowlist, exact receipt and recursive build receipt hashes',
            'fresh prepare (explicit entrypoint, no scoring/writes)',
            'exact package independent manual packageAudit plus actual parent browser tool inspection',
            'parent-owned direct native browser tool bridge with server correlation evidence',
            'separately authorized run-reviewed-window; one score then finally cleanup',
            'separately reviewed production Auto/two-chat phase; diagnostic route never completes that task'],
        'guidance': 'Offline only; no auth, identity, cert or dependency installation'}
    p.exclusive(folder / 'REPORT.json', report)
    ok = (result.wasSuccessful() and node.returncode == 0 and native_result['semantic_exit'] == 0
        and native_result['expressions'] == 225 and not changed and not frozen_changed and not original_changed)
    print(json.dumps({key: value for key, value in report.items() if key != 'source_hashes'}, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())