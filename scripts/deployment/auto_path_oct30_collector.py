"""Private Oct30 upstream ACL compatibility; import performs no reads or writes.

Only the old protected() function sees a historical four-rule COPY, after exact
whole-account verification. Neither the transport response nor retained full13
is normalized. The original controller/module/class/functions stay untouched.
"""
from contextlib import contextmanager
from copy import deepcopy
from collections import deque
from pathlib import Path
from types import FunctionType, ModuleType
import re
import ssl
from urllib.error import HTTPError

from scripts.deployment.apim_route_repair import RepairBlocked

HISTORICAL_STORAGE_API = "2023-05-01"
APPROVED_STORAGE_API = "2025-06-01"


def copy_module(module):
    private = ModuleType(module.__name__ + "_oct30_private")
    private.__dict__.update(vars(module))
    return private


def bind(function, namespace):
    private = FunctionType(function.__code__, namespace, function.__name__,
                           function.__defaults__, function.__closure__)
    private.__kwdefaults__ = function.__kwdefaults__
    return private


def private_controller(progress):
    from scripts.deployment import auto_path_diagnostic_oct30 as s
    from scripts.deployment import poc_publisher_recheck_oct29 as reads
    from scripts.deployment import project_route_product_access as product

    d = s.d
    before, after = s.storage_transition()  # pinned audit transitively pins result
    private = copy_module(d)
    private.r = copy_module(d.r)
    private.r.persistence = copy_module(d.r.persistence)
    release = private.r.persistence.release = copy_module(d.r.persistence.release)
    historical_rt = copy_module(product.rt)
    globals_ = {**vars(product), "rt": historical_rt}
    protected = bind(product.ProductRun.protected, globals_)
    storage_args = ["rest", "--method", "get", "--url",
        "https://management.azure.com" + d.r.rt.RG
        + "/providers/Microsoft.Storage/storageAccounts/projpoctokenex?api-version=" + HISTORICAL_STORAGE_API]
    approved_args = [*storage_args[:-1], storage_args[-1].removesuffix(HISTORICAL_STORAGE_API)
                     + APPROVED_STORAGE_API]
    # The independent arm_read already uses the approved read representation.
    # Fail closed if its exact account/version ever changes; do not rebind it.
    d.require(d.r.persistence.backend.URL == approved_args[-1],
              "oct30_separate_storage_read_exact_approved_API")
    d.require(after["properties"]["allowCrossTenantDelegationSas"] is False,
              "oct30_pinned_delegation_exact_false")

    class Oct30ProductRun(reads.ReadOnlyProductRun):
        def protected(self):
            calls = []

            def cli(args):
                # All other reads retain the original strict read transport.
                if args != storage_args:
                    return d.r.rt.cli(args)
                d.require(not calls, "oct30_single_snapshot_storage_read")
                response = d.r.rt.cli(approved_args)
                d.require(response == after
                          and response["properties"]["allowCrossTenantDelegationSas"] is False,
                          "oct30_whole_account_exact_approved_after")
                progress["phase"] = "WHOLE_ACCOUNT_VERIFIED"
                calls.append(True)
                historical = deepcopy(response)
                rules = historical["properties"]["networkAcls"]["ipRules"]
                d.require(len(rules) == 5 and rules[-1] == {"value": s.IP, "action": "Allow"},
                          "oct30_exact_five_rules_known_added_last")
                rules.pop()  # Only after full equality; never filter arbitrary IPs.
                d.require(historical == before, "oct30_exact_historical_account_copy")
                return historical

            saved = historical_rt.cli
            try:
                historical_rt.cli = cli
                result = protected(self)  # Original require and every other guard.
                d.require(len(calls) == 1 and result["state_network"] == s.state_network(before),
                          "oct30_old_guard_exact_historical_projection")
                result["state_network"] = s.state_network(after)
                return result
            finally:
                historical_rt.cli = saved

    release.snapshot = bind(release.snapshot, vars(release))
    # Rebind the generator, NOT contextlib's decorator wrapper: the latter
    # requires contextlib's own globals and would lose _GeneratorContextManager.
    private.read_transport = contextmanager(bind(d.read_transport.__wrapped__, vars(private)))
    private.collect = bind(d.collect, vars(private))
    return private, Oct30ProductRun


@contextmanager
def strict_read_context(private, product_class, progress):
    """Use unchanged strict TLS/read allowlist, restore bindings on every exit."""
    release = private.r.persistence.release
    original = release.ProductRun
    try:
        with private.read_transport():
            release.ProductRun = product_class
            progress["phase"] = "STRICT_READ_CONTEXT"
            yield
    finally:
        release.ProductRun = original


def collect(progress=None):
    from scripts.deployment import auto_path_diagnostic_oct30 as s
    progress = {} if progress is None else progress
    progress["phase"] = "PINNED_STORAGE_PROOF"
    private, product_class = private_controller(progress)
    transport = private.read_transport

    @contextmanager
    def scoped():
        # Avoid recursively entering this replacement; only private binding.
        private.read_transport = transport
        try:
            with strict_read_context(private, product_class, progress):
                yield
        finally:
            private.read_transport = scoped

    private.read_transport = scoped
    capture = private.collect()
    _, after = s.storage_transition()
    s.require(len(capture["baseline"]) == 13
              and capture["storage_sha256"] == s.d.r.fs.sha(after)
              and capture["baseline"]["state_network"] == s.state_network(after),
              "oct30_retained_full13_actual_five_pinned_account")
    progress["phase"] = "ACTUAL_FULL13_VERIFIED"
    return capture


def failure_code(error):
    # Never serialize str(error), HTTP bodies, arbitrary class names or locals.
    if isinstance(error, ssl.SSLError):
        return "TLS_FAILURE"
    if isinstance(error, TimeoutError):
        return "READ_TIMEOUT"
    if isinstance(error, HTTPError):
        return "HTTP_READ_FAILURE"
    if isinstance(error, RepairBlocked):
        return "GUARD_REJECTED"
    if isinstance(error, RuntimeError):
        return "GUARD_OR_RUNTIME_FAILURE"
    return "UNCLASSIFIED_FAILURE"


def safe_failure_frames(error):
    """Descriptors only: no traceback formatting, source lines or frame locals.

    Resolve containment against the actual workspace, not a string prefix.
    Keep the innermost 16 accepted frames, scanning at most 256 traceback nodes.
    Exception chains and synthetic/nonexistent/outside filenames are omitted.
    """
    from scripts.deployment import auto_path_diagnostic_oct30 as s
    root = s.ROOT.resolve()
    frames = deque(maxlen=16)
    trace = error.__traceback__
    for _ in range(256):
        if trace is None:
            break
        code = trace.tb_frame.f_code
        try:
            path = Path(code.co_filename)
            if not path.is_absolute() or ".." in path.parts:
                continue
            path = path.resolve(strict=True)
            if not path.is_file() or not path.is_relative_to(root):
                continue
            name = path.relative_to(root).as_posix()
            function = code.co_name
            if (len(name) <= 240 and re.fullmatch(r"[A-Za-z0-9_.\-/]+", name)
                    and (re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,79}", function)
                         or function in ("<module>", "<lambda>", "<genexpr>", "<dictcomp>", "<listcomp>"))
                    and 0 < trace.tb_lineno <= 10_000_000):
                frames.append({"file": name, "function": function, "line": trace.tb_lineno})
        except (OSError, ValueError, RuntimeError):
            pass  # Failure reporting must not replace the original exception.
        finally:
            trace = trace.tb_next
    return list(frames)


def safe_exception_type(error):
    # Exact types only; never export a custom/subclass-controlled class name.
    known = {RuntimeError: "RuntimeError", ValueError: "ValueError",
             TypeError: "TypeError", KeyError: "KeyError", OSError: "OSError",
             FileNotFoundError: "FileNotFoundError", TimeoutError: "TimeoutError",
             ssl.SSLError: "SSLError", ssl.SSLCertVerificationError: "SSLCertVerificationError",
             HTTPError: "HTTPError", RepairBlocked: "RepairBlocked"}
    return known.get(type(error), "UNKNOWN_EXCEPTION_TYPE")


def retain_prepare_failure(folder, error, progress):
    from scripts.deployment import auto_path_diagnostic_oct30 as s
    phases = {"PREPARE_VALIDATION", "PINNED_STORAGE_PROOF", "WHOLE_ACCOUNT_VERIFIED",
              "STRICT_READ_CONTEXT", "ACTUAL_FULL13_VERIFIED", "CAPTURE_RETURNED"}
    s.d.exclusive(folder.with_name(folder.name + "-prepare-failure.json"), {
        "status": "STOP_RECONCILE_DURABLE_EVIDENCE_NO_RETRY",
        "at_utc": s.controller.now().isoformat(), "pid": s.d.os.getpid(),
        "error_code": failure_code(error),
        "exception_type": safe_exception_type(error),
        "frames": safe_failure_frames(error),
        "phase": progress.get("phase") if progress.get("phase") in phases else "UNKNOWN",
        "partial_capture_not_acceptance": True,
        "original_PID27864_exception": "UNKNOWN_NOT_RECOVERED",
        "cloud_mutations": 0, "browser_Send_invocations": 0})