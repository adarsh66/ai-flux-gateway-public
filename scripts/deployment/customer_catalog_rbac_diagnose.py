"""Checkpoint the failed read-only collector without replaying deployment stages."""
import json
import traceback

from scripts.deployment import customer_catalog_rbac_followthrough as f
from scripts.deployment import glm_resume


def main():
    stage = 'bestpractices'
    try:
        glm_resume.bestpractices()
        stage = 'account'
        f.r.account()
        stage = 'source_check'
        f.r.source_check()
        stage = 'assignment_read'
        status, _ = f.get(f.ASSIGNMENT)
        stage = 'role_definition_read'
        code, definition = f.get('/subscriptions/' + f.r.rt.SUB
                                 + '/providers/Microsoft.Authorization/roleDefinitions/' + f.ROLE)
        print(json.dumps({'assignment_status': status, 'definition_status': code,
                          'actual_role': definition.get('properties') if definition else None}), flush=True)
        stage = 'assignment_list'
        # Capture diagnostics only, never raw metadata or authentication output.
        import subprocess
        p = subprocess.run(f.r.rt.CLI + ['role', 'assignment', 'list', '--assignee-object-id', f.PRINCIPAL,
            '--scope', f.APIM, '--include-inherited', '--include-groups', '--all',
            '--subscription', f.r.rt.SUB, '--only-show-errors', '-o', 'json'],
            env=f.r.rt.ENV, capture_output=True, text=True, encoding='utf-8', errors='replace')
        allowed = ['usage error', '--all', '--scope', '--include-groups', '--include-inherited',
                   'unrecognized arguments', 'not supported', 'cannot be used', 'AADSTS', 'AuthorizationFailed']
        result = {'at': f.r.fs.stamp(), 'stage': stage, 'exit_code': p.returncode,
                  'diagnostic_lines': [line for line in p.stderr.splitlines()
                      if any(s in line for s in allowed) and not any(s in line.lower() for s in ('token', 'secret', 'password'))],
                  'assignment_count': len(json.loads(p.stdout)) if p.returncode == 0 else None}
    except Exception as e:
        result = {'at': f.r.fs.stamp(), 'stage': stage, 'error_type': type(e).__name__,
                  'reason': str(e) if isinstance(e, RuntimeError) else 'detail_suppressed',
                  'frames': [{'function': x.name, 'line': x.lineno} for x in traceback.extract_tb(e.__traceback__)]}
    path = f.r.HOME / 'rbac-failed-execution-diagnosis.json'
    with path.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()