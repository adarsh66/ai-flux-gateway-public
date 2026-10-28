"""Offline orchestrator safety tests. All credentials here are synthetic."""

import json
from types import SimpleNamespace

import pytest

from scripts.deployment import run_private_sql as runner


def test_redactor_removes_secrets_and_unknown_jwt():
    redactor = runner.Redactor()
    redactor.add("synthetic-secret-password")
    redactor.add("synthetic-secret")
    result = redactor.text("synthetic-secret-password synthetic-secret abcdefghijk.abcdefghijk.abcdefghijk")
    assert "synthetic-secret" not in result
    assert "abcdefghijk" not in result
    assert "REDACTED" in result


def test_aci_body_has_only_secure_secret_values_and_no_ingress():
    body = runner.container_body("a" * 32, "identity-id", "client-id", "image@sha256:digest",
                                 "synthetic-token", 12345, "synthetic-seeds")
    props = body["properties"]
    container = props["containers"][0]["properties"]
    env = {item["name"]: item for item in container["environmentVariables"]}
    assert env["AIFLUX_SQL_OPERATOR_TOKEN"] == {
        "name": "AIFLUX_SQL_OPERATOR_TOKEN", "secureValue": "synthetic-token"}
    assert "value" not in env["AIFLUX_PORTAL_SEED_USERS"]
    assert "synthetic-token" not in json.dumps(container["command"])
    assert "synthetic-seeds" not in json.dumps(container["command"])
    assert "--verify-api-mi" in container["command"]
    assert "ipAddress" not in props and "ports" not in container
    assert props["restartPolicy"] == "Never"
    assert props["subnetIds"] == [{"id": runner.SUBNET}]
    assert container["resources"]["requests"] == {"cpu": 1, "memoryInGB": 1.5}


@pytest.mark.parametrize("content", [
    "synthetic-token", '{"status":"ok","checks":["synthetic-token"]}',
    '{"status":"synthetic-token","checks":[]}',
])
def test_job_logs_do_not_relay_unrecognized_output(content):
    assert runner.parse_job_log(content) == {"status": "unverified", "checks": []}


def test_job_log_accepts_only_known_failure_codes():
    value = runner.parse_job_log(json.dumps({
        "status": "failed", "code": "synthetic-token", "checks": ["private_dns_validated"],
        "exception": "synthetic-password"}))
    assert value == {"status": "failed", "code": "unrecognized_job_error",
                     "checks": ["private_dns_validated"]}
    assert runner.parse_job_log('{"status":"failed","code":"runtime_roles_rejected","checks":[]}')[
        "code"] == "runtime_roles_rejected"


def test_token_acquisition_error_never_echoes_stdout_or_stderr(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=1, stdout="synthetic-token", stderr="synthetic-token"))
    with pytest.raises(runner.RunnerError) as caught:
        runner.cli(["account", "get-access-token"], runner.Redactor())
    assert "synthetic-token" not in json.dumps(caught.value.details)


def test_secret_cli_options_rejected_without_starting_process(monkeypatch):
    monkeypatch.setattr(runner.subprocess, "run", lambda *a, **k: pytest.fail("unsafe CLI executed"))
    with pytest.raises(runner.RunnerError, match="unsafe_cli_arguments"):
        runner.cli(["rest", "--body", "synthetic-secret"], runner.Redactor())


def test_cleanup_does_not_delete_unowned_resources(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HOME", tmp_path)
    deletes = []
    arm = SimpleNamespace(get=lambda *a: {"tags": {runner.OWNER_KEY: "other-run"}},
                          operation=lambda *a, **k: deletes.append(a))
    execution = runner.Execution(arm, runner.Redactor(), "a" * 32)
    execution.report["resources"] = [{"id": runner.IP, "version": runner.NET_API}]
    execution.cleanup()
    assert not deletes
    assert execution.report["cleanup"][0]["code"] == "cleanup_ownership_mismatch"


def test_cleanup_only_deletes_journaled_owned_resource(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HOME", tmp_path)
    deleted = []

    def get(resource, version):
        assert resource == runner.IP
        return None if deleted else {"tags": {runner.OWNER_KEY: "a" * 32}}

    arm = SimpleNamespace(get=get, operation=lambda *a, **k: deleted.append(a))
    execution = runner.Execution(arm, runner.Redactor(), "a" * 32)
    execution.report["resources"] = [{"id": runner.IP, "version": runner.NET_API}]
    execution.cleanup()
    assert deleted == [("DELETE", runner.IP, runner.NET_API)]
    assert execution.report["cleanup"] == [{"id": runner.IP, "status": "verified_absent"}]


def test_arm_rejects_foreign_polling_host_before_sending_token():
    arm = object.__new__(runner.Arm)
    arm.redactor = runner.Redactor()
    arm.session = SimpleNamespace(request=lambda *a, **k: pytest.fail("token sent to foreign host"))
    with pytest.raises(runner.RunnerError, match="arm_url_rejected"):
        arm.request("GET", "https://attacker.invalid/poll")


def test_build_uses_absolute_dockerfile_in_minimal_public_context(monkeypatch):
    from pathlib import Path

    def cli(args, redactor, timeout=180):
        if args[:3] == ["acr", "repository", "list"]:
            return []
        if args[:2] == ["acr", "build"]:
            context = Path(args[-1])
            dockerfile = Path(args[args.index("--file") + 1])
            assert dockerfile.is_absolute() and dockerfile.parent == context
            assert dockerfile.is_file()
            files = {str(p.relative_to(context)).replace("\\", "/")
                     for p in context.rglob("*") if p.is_file()}
            assert files == {"Dockerfile", "scripts/deployment/private_sql_job.py",
                             "scripts/deployment/private_sql_diagnostic.py"}
            assert "RUN python -c" in dockerfile.read_text()
            assert "--no-logs" in args
            return {"runId": "synthetic-build", "status": "Succeeded"}
        return {"digest": "sha256:" + "a" * 64}

    monkeypatch.setattr(runner, "cli", cli)
    result = runner.build_image(runner.Redactor())
    assert result["build_id"] == "synthetic-build"
    assert "@sha256:" in result["image"]


def test_diagnostic_emits_only_sqlstate_and_numeric_codes():
    content = json.dumps({"diagnostic": "sql_driver", "sqlstate": "42000",
                          "native_codes": [102, 15151], "message": "synthetic-secret"})
    assert runner.parse_diagnostic(content) == {"sqlstate": "42000", "native_codes": [102, 15151]}
    assert runner.parse_diagnostic(content.replace('"42000"', '"synthetic-secret"')) == {}


def test_diagnostic_only_accepts_fixed_statement_labels():
    value = {"diagnostic": "sql_driver", "sqlstate": "42000", "native_codes": [102],
             "stage": "runtime_deny_database_ddl"}
    assert runner.parse_diagnostic(json.dumps(value))["stage"] == "runtime_deny_database_ddl"
    value["stage"] = "synthetic-sensitive-sql"
    assert "stage" not in runner.parse_diagnostic(json.dumps(value))


def test_credentials_cannot_be_regenerated(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "HOME", tmp_path)
    monkeypatch.setattr(runner, "protect_directory", lambda path: None)
    with pytest.raises(runner.RunnerError, match="existing_credentials_required"):
        runner.credentials(runner.Redactor())
    assert not (tmp_path / "credentials.json").exists()


def test_runtime_evidence_rejects_syntax_failure_as_permission_denial():
    value = {"runtime_probe": "SQL_DENY_DDL", "operation": "create_sequence",
             "sqlstate": "42000", "native_codes": [102], "message": "synthetic-secret"}
    assert runner.parse_runtime_evidence(json.dumps(value)) == []
    value["native_codes"] = [262]
    assert runner.parse_runtime_evidence(json.dumps(value)) == [
        {"result": "SQL_DENY_DDL", "operation": "create_sequence",
         "sqlstate": "42000", "native_codes": [262]}]
    value["operation"] = "synthetic-secret"
    assert runner.parse_runtime_evidence(json.dumps(value)) == []


def test_documented_15247_is_permission_denial_not_syntax():
    value = {"runtime_probe": "SQL_DENY_DDL", "operation": "create_sequence",
             "sqlstate": "42000", "native_codes": [15247]}
    assert runner.parse_runtime_evidence(json.dumps(value))[0]["native_codes"] == [15247]
    value["native_codes"] = [15247, 102]
    assert runner.parse_runtime_evidence(json.dumps(value)) == []
    value["native_codes"] = [99999]
    assert runner.parse_runtime_evidence(json.dumps(value)) == []


def test_build_never_overwrites_existing_tag(monkeypatch):
    def cli(args, redactor, timeout=180):
        if args[:3] == ["acr", "repository", "list"]:
            return ["aiflux-sql-runner"]
        if args[:3] == ["acr", "repository", "show-tags"]:
            return [runner.IMAGE_TAG]
        pytest.fail("existing tag must stop before build")

    monkeypatch.setattr(runner, "cli", cli)
    with pytest.raises(runner.RunnerError, match="runner_image_tag_preexists"):
        runner.build_image(runner.Redactor())