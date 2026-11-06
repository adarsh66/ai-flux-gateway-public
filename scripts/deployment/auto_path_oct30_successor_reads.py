"""Isolated timing at open AND body-read boundaries; no retry or token logging."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import monotonic_ns
from urllib.parse import urlsplit

from scripts.deployment import auto_path_oct30_collector as old_reads
from scripts.deployment import auto_path_diagnostic_oct30 as old

d = old.d
_context = ContextVar("oct30_successor_read_context", default=None)
_stage = ContextVar("oct30_successor_stage", default="prepare")
STAGES = {"prepare", *d.STAGES}


@contextmanager
def diagnostics(folder, stage):
    d.require(stage in STAGES, "finite_read_stage")
    target = folder.with_name(folder.name + "-" + stage + "-read-diagnostics")
    d.require(not target.is_symlink(), "diagnostic_directory_not_link")
    target.mkdir(exist_ok=False)
    token = _context.set({"folder": target, "sequence": 0})
    stage_token = _stage.set(stage)
    try:
        yield
    finally:
        _stage.reset(stage_token)
        _context.reset(token)


def label(request):
    url = urlsplit(request.full_url)
    method = request.get_method()
    d.require(url.scheme == "https" and not url.username and not url.password and not url.fragment
              and url.port in (None, 443), "strict_read_destination")
    arm = url.netloc == "management.azure.com" and (
        url.path.startswith("/subscriptions/" + d.r.rt.SUB + "/")
        or url.path.startswith("/providers/Microsoft.Authorization/roleDefinitions/"))
    blob = request.full_url == "https://projpoctokenex.blob.core.windows.net/tfstate/poc-ids-token-ex/main.tfstate"
    settings = {d.r.rt.RG + "/providers/Microsoft.Web/sites/poc-ids-token-ex-" + name
                + "/config/appsettings/list" for name in ("api", "admin", "customer", "ingestion")}
    d.require((arm and (method == "GET" or (method == "POST" and url.path in settings)))
              or (blob and method in ("GET", "HEAD")), "existing_read_only_scope")
    operation = "metadata"
    fmt = "none"
    if arm and url.path.endswith("/policies/policy"):
        operation = "revision_policy" if "/apis/" in url.path else "global_policy"
        # Never retain arbitrary query text, even inside a legitimate URL.
        fmt = "rawxml" if "format=rawxml" in url.query.split("&") else (
            "xml" if "format=xml" in url.query.split("&") else "none")
    return {"service": "ARM" if arm else "STATE_BLOB", "operation": operation,
            "format": fmt, "method": method}


class TimedOpen:
    def __init__(self, opener):
        self.opener = opener

    @contextmanager
    def open(self, request, *, timeout):
        descriptor = label(request)
        # Policy arm() is45s; inherited API get() is60s; full13/state is90s.
        # Preserve the caller's exact value, never increase or retry it.
        d.require(timeout in (45, 60, 90), "unchanged_finite_read_timeout")
        context = _context.get()
        d.require(context is not None and _stage.get() in STAGES, "read_diagnostics_required")
        context["sequence"] += 1
        prefix = str(context["sequence"]).zfill(6)
        start, tick = d.now().isoformat(), monotonic_ns()
        record = {**descriptor, "stage": _stage.get(), "started_at_utc": start,
                  "monotonic_start_ns": tick, "timeout_seconds": timeout,
                  "opens": 1, "retries": 0, "redirects": 0}
        d.exclusive(context["folder"] / (prefix + "-start.json"), record)
        status, failure = None, None
        try:
            # Original strict CA/hostname/no-redirect opener. Exactly ONE open.
            with self.opener.open(request, timeout=timeout) as response:
                status = response.status if type(response.status) is int else None
                yield response  # Includes caller's bounded read in measured interval.
        except Exception as error:
            failure = old_reads.safe_exception_type(error)
            raise
        finally:
            end = monotonic_ns()
            d.exclusive(context["folder"] / (prefix + "-end.json"), {
                **record, "ended_at_utc": d.now().isoformat(), "monotonic_end_ns": end,
                "elapsed_ns": end - tick, "http_status": status, "failure_type": failure})


def private_controller(progress):
    private, product = old_reads.private_controller(progress)
    private.a = old_reads.copy_module(private.a)
    strict_opener = private.a.opener
    private.a.opener = lambda ca: TimedOpen(strict_opener(ca))
    private.c = old_reads.copy_module(private.c)

    class Reads(d.c.Reads):
        def __init__(self):
            super().__init__()
            self.http = TimedOpen(self.http)

    private.c.Reads = Reads
    # collect() and remote_state() MUST both see the private helper namespaces.
    private.collect = old_reads.bind(d.collect, vars(private))
    private.remote_state = old_reads.bind(d.remote_state, vars(private))
    return private, product


def collect(progress=None):
    progress = {} if progress is None else progress
    private, product = private_controller(progress)
    transport = private.read_transport

    @contextmanager
    def scoped():
        private.read_transport = transport
        try:
            with old_reads.strict_read_context(private, product, progress):
                yield
        finally:
            private.read_transport = scoped

    private.read_transport = scoped
    capture = private.collect()
    _, account = old.storage_transition()
    d.require(len(capture["baseline"]) == 13
              and capture["storage_sha256"] == d.r.fs.sha(account)
              and capture["baseline"]["state_network"] == old.state_network(account), "actual_full13_five_rule_account")
    return capture


class ProductionAdapter(d.ProductionAdapter):
    def capture(self):
        self.ready = None
        self.value = collect()
        self.captured = d.deepcopy(self.value)
        return self.value

    def last(self, stage):
        # Rebind only the function's c namespace; retain all last-target guards.
        private, _ = private_controller({})
        return old_reads.bind(d.ProductionAdapter.last, {**vars(d), "c": private.c})(self, stage)


class Stages(d.Stages):
    def execute(self, stage):
        token = _stage.set(stage)
        try:
            # Rebound below to successor controller globals, not original d.
            return self._execute(stage)
        finally:
            _stage.reset(token)


def retain_prepare_failure(folder, error, progress):
    return old_reads.retain_prepare_failure(folder, error, progress)