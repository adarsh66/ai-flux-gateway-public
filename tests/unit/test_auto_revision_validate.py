"""Offline negative guards for the retained-revision validator; no Azure calls."""
import json

import pytest

from scripts.deployment import auto_revision_validate as v


@pytest.mark.parametrize("args", [("apply",), ("plan",), ("refresh",), ("destroy",),
                                  ("state", "rm"), ("state", "push"), ("state", "mv")])
def test_rejects_mutation_commands(args):
    with pytest.raises(RuntimeError):
        v.tf(*args)


def test_sanitized_terraform_environment(monkeypatch):
    monkeypatch.setattr(v.p.rt, "ENV", {"PATH": "keep", "TF_VAR_attack": "x", "TF_CLI_ARGS_apply": "x",
                                     "TF_WORKSPACE": "other", "TF_DATA_DIR": "other", "TF_LOG": "TRACE"})
    env = v.environment()
    assert env["PATH"] == "keep"
    assert env["TF_WORKSPACE"] == "default"
    assert env["TF_INPUT"] == "0"
    assert "TF_DATA_DIR" not in env
    assert not any(k.startswith(("TF_VAR_", "TF_CLI_ARGS", "TF_LOG")) for k in env)


def test_exclusive_save_cannot_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(v, "OUT", tmp_path)
    v.save("proof.json", {"real": True})
    with pytest.raises(FileExistsError):
        v.save("proof.json", {"real": False})
    assert json.loads((tmp_path / "proof.json").read_bytes()) == {"real": True}


def test_target_binding_is_exact():
    assert v.PLAN_SHA == "6675631640d48342ad5a55d38613e56c3393aaed67ae4889e98cdfbb1f400998"
    assert v.HOME.name == "auto-offline-revision-20261029T060302997824Z"