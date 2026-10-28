"""Fresh image-only plan after rejecting legacy Always On default; no old replay."""
import argparse
from datetime import UTC, datetime, timedelta
import json

from scripts.deployment import fireworks_runtime as release
from scripts.deployment import runtime_rollout as rt

ORIGINAL = release.HOME
HOME = ORIGINAL / 'preserved-image-plan'
ARTIFACTS = ('acceptance.json', 'native.json', 'sources.json', 'build.json',
             'corrected-build.json', 'ingestion-correction-intent.json',
             'readback.json', 'release-tests.xml', 'scanner.json', 'corrected-scanner.json')


def configure():
    release.HOME = HOME
    release.ROOT = HOME / 'infra/terraform'
    release.PLAN = HOME / 'runtime.tfplan'
    release.TESTS = HOME / 'release-tests.xml'


def review_existing():
    """Recover review only after real full-plan preconditions resolve unknowns."""
    rt.require(not (HOME / 'review.json').exists()
               and not (HOME / 'apply-intent.json').exists()
               and not (ORIGINAL / 'apply-intent.json').exists(), 'never_review_attempted_apply')
    intent = release.load(HOME / 'plan-intent.json')
    rt.require(timedelta(0) <= datetime.now(UTC) - datetime.fromisoformat(intent['at'])
               < timedelta(hours=2), 'existing_plan_expired')
    images = release.built()
    release.verify_external_metadata()
    plan = release.load_plan()
    release.guard(plan, images)
    before = release.baseline()
    paths = [*release.ROOT.glob('*.tf'), *release.ROOT.glob('*.tf.json'),
             release.ROOT / '.terraform.lock.hcl', HOME / 'runtime.tfvars.json',
             HOME / 'validation-only-refreshed-never-apply.tfplan']
    review = {'at': datetime.now(UTC).isoformat(), 'plan_sha256': release.sha(release.PLAN.read_bytes()),
              'sources': release.sources(), 'images': images, 'baseline': before,
              'tests': release.tests(), 'guard': 'exact_api_and_ingestion_images_only',
              'target_unknown_checks_resolved_from_identical_input_companion': True,
              'companion_apply_prohibited': True,
              'artifacts': {p.relative_to(HOME).as_posix(): release.sha(p.read_bytes()) for p in paths}}
    rt.save(HOME / 'review.json', review)
    print(json.dumps({k: review[k] for k in ('at', 'plan_sha256', 'images', 'guard')}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'review', 'validate', 'apply', 'verify'])
    action = parser.parse_args().action
    if action == 'plan':
        rt.require(not (ORIGINAL / 'apply-intent.json').exists()
                   and not (ORIGINAL / 'review.json').exists(), 'original_failed_unapplied_required')
        HOME.mkdir(exist_ok=False)
        for name in ARTIFACTS:
            (HOME / name).write_bytes((ORIGINAL / name).read_bytes())
    configure()
    if action == 'validate':
        from scripts.deployment.fireworks_runtime_validation import main as validate
        validate()
    else:
        {'plan': release.plan, 'review': review_existing,
         'apply': release.apply, 'verify': release.verify}[action]()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'error_type': type(error).__name__, 'reason': str(error)
                          if isinstance(error, RuntimeError) else 'preserved_release_failed_sensitive_detail_suppressed'}), flush=True)
        raise SystemExit(1)