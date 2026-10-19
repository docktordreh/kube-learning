"""Check evaluation against live cluster state.

Every check is read-only: kubectl get/exec with the grader identity, SubjectAccessReviews
(never persisted), or read-only commands on nodes. Checks report *why* they failed.
"""

import json
import re
import shlex
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cka_labs import proc
from cka_labs.backends.base import Cluster
from cka_labs.engine.generator import render_tree, to_json
from cka_labs.kube import Kube
from cka_labs.models import (
    CanICheck,
    Check,
    DeploymentReadyCheck,
    ExecCheck,
    ExistsCheck,
    JsonPathCheck,
    NodeExecCheck,
    NodeReadyCheck,
    PodsReadyCheck,
    ScriptCheck,
    ServiceEndpointsCheck,
)

MAX_DETAIL = 400

RC_MARKER = "__CKA_RC="


@dataclass(frozen=True)
class CheckResult:
    id: str
    description: str
    role: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class GradeContext:
    cluster: Cluster
    grader: Kube
    captured: Mapping[str, str]


def resolve(check: Check, captured: Mapping[str, str]) -> Check:
    """Substitute {{captured.*}} values recorded during setup."""
    if not captured:
        return check
    values = {f"captured.{key}": value for key, value in captured.items()}
    rendered = render_tree(to_json(check.model_dump()), values)
    return type(check).model_validate(rendered)


def evaluate(check: Check, ctx: GradeContext) -> CheckResult:
    check = resolve(check, ctx.captured)
    try:
        passed, detail = _dispatch(check, ctx)
    except Exception as exc:  # a crashing check is a failed check, with the reason shown
        passed, detail = False, f"check error: {exc}"
    if len(detail) > MAX_DETAIL:
        detail = detail[:MAX_DETAIL] + " …"
    return CheckResult(check.id, check.description, check.role, passed, detail)


def evaluate_all(checks: Sequence[Check], ctx: GradeContext, *, settle: bool = True) -> list[CheckResult]:
    """Evaluate all checks; with settle, re-evaluate failing checks up to their timeout."""
    results = {check.id: evaluate(check, ctx) for check in checks}
    if settle:
        deadline = time.monotonic() + max((c.timeout for c in checks if not results[c.id].passed), default=0)
        while time.monotonic() < deadline:
            pending = [c for c in checks if not results[c.id].passed and time.monotonic() < deadline]
            if not pending:
                break
            time.sleep(3)
            for check in pending:
                results[check.id] = evaluate(check, ctx)
    return [results[c.id] for c in checks]


def wait_for(check: Check, ctx: GradeContext, timeout: float) -> CheckResult:
    deadline = time.monotonic() + timeout
    while True:
        result = evaluate(check, ctx)
        if result.passed or time.monotonic() >= deadline:
            return result
        time.sleep(2)


# --- implementations ---------------------------------------------------------------------


def _dispatch(check: Check, ctx: GradeContext) -> tuple[bool, str]:
    match check:
        case JsonPathCheck():
            return _jsonpath(check, ctx.grader)
        case ExistsCheck():
            return _exists(check, ctx.grader)
        case PodsReadyCheck():
            return _pods_ready(check, ctx.grader)
        case ServiceEndpointsCheck():
            return _service_endpoints(check, ctx.grader)
        case DeploymentReadyCheck():
            return _deployment_ready(check, ctx.grader)
        case ExecCheck():
            return _exec(check, ctx.grader)
        case CanICheck():
            return _can_i(check, ctx.grader)
        case NodeReadyCheck():
            return _node_ready(check, ctx)
        case NodeExecCheck():
            return _node_exec(check, ctx.cluster)
        case ScriptCheck():
            return _script(check, ctx.grader)


def _ns(namespace: str | None) -> list[str]:
    return ["-n", namespace] if namespace else []


def _jsonpath(check: JsonPathCheck, kube: Kube) -> tuple[bool, str]:
    result = kube.kubectl(["get", *shlex.split(check.resource), *_ns(check.namespace), "-o", f"jsonpath={check.jsonpath}"])
    if not result.ok:
        return False, f"{check.resource} not readable: {result.output()}"
    actual = result.stdout.strip()
    expected = check.value or ""
    match check.op:
        case "equals":
            ok = actual == expected
        case "not_equals":
            ok = actual != expected
        case "matches":
            ok = re.search(expected, actual) is not None
        case "not_matches":
            ok = re.search(expected, actual) is None
        case "contains":
            ok = expected in actual
        case "nonempty":
            ok = actual != ""
        case "empty":
            ok = actual == ""
        case "gte" | "lte":
            try:
                number, bound = float(actual), float(expected)
            except ValueError:
                return False, f"{check.jsonpath} is {actual!r}, not a number"
            ok = number >= bound if check.op == "gte" else number <= bound
    shown = actual if len(actual) < 200 else actual[:200] + "…"
    return ok, f"{check.resource} {check.jsonpath} = {shown!r} (expected {check.op} {expected!r})"


def _exists(check: ExistsCheck, kube: Kube) -> tuple[bool, str]:
    result = kube.kubectl(["get", *shlex.split(check.resource), *_ns(check.namespace), "--ignore-not-found", "-o", "name"])
    if not result.ok:
        return False, result.output()
    present = result.stdout.strip() != ""
    where = f" in {check.namespace}" if check.namespace else ""
    return present == check.present, f"{check.resource}{where} {'exists' if present else 'does not exist'}"


def _items(kube: Kube, args: list[str]) -> list[dict[str, object]] | None:
    data = kube.get_json(args)
    if data is None:
        return None
    items = data.get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _get(obj: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _condition(obj: object, kind: str) -> str | None:
    conditions = _get(obj, "status", "conditions")
    if isinstance(conditions, list):
        for condition in conditions:
            if isinstance(condition, dict) and condition.get("type") == kind:
                status = condition.get("status")
                return status if isinstance(status, str) else None
    return None


def _pods_ready(check: PodsReadyCheck, kube: Kube) -> tuple[bool, str]:
    pods = _items(kube, ["get", "pods", "-n", check.namespace, "-l", check.selector])
    if pods is None:
        return False, f"cannot list pods in {check.namespace}"
    live = [p for p in pods if _get(p, "metadata", "deletionTimestamp") is None]
    ready = [p for p in live if _condition(p, "Ready") == "True"]
    unready = [str(_get(p, "metadata", "name")) for p in live if _condition(p, "Ready") != "True"]
    detail = f"{len(ready)}/{len(live)} pods ready for selector {check.selector!r} in {check.namespace}"
    if unready:
        detail += f"; not ready: {', '.join(unready[:5])}"
    ok = len(ready) >= check.min_ready and (not check.all_ready or not unready)
    return ok, detail


def _service_endpoints(check: ServiceEndpointsCheck, kube: Kube) -> tuple[bool, str]:
    slices = _items(
        kube, ["get", "endpointslices", "-n", check.namespace, "-l", f"kubernetes.io/service-name={check.service}"]
    )
    if slices is None:
        return False, f"cannot list EndpointSlices in {check.namespace}"
    ready: set[str] = set()
    for endpoint_slice in slices:
        endpoints = endpoint_slice.get("endpoints")
        for endpoint in endpoints if isinstance(endpoints, list) else []:
            addresses = _get(endpoint, "addresses")
            if _get(endpoint, "conditions", "ready") is True and isinstance(addresses, list):
                ready.update(a for a in addresses if isinstance(a, str))
    count = len(ready)
    ok = count >= check.min_ready and (check.max_ready is None or count <= check.max_ready)
    shown = ", ".join(sorted(ready)[:6]) or "none"
    return ok, f"service {check.namespace}/{check.service}: {count} ready endpoint(s) [{shown}]"


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _deployment_ready(check: DeploymentReadyCheck, kube: Kube) -> tuple[bool, str]:
    deploy = kube.get_json(["get", "deployment", check.name, "-n", check.namespace])
    if deploy is None:
        return False, f"deployment {check.namespace}/{check.name} not found"
    desired = _int(_get(deploy, "spec", "replicas"))
    status = {key: _int(_get(deploy, "status", key)) for key in ("replicas", "updatedReplicas", "readyReplicas", "availableReplicas")}
    generation_ok = _int(_get(deploy, "status", "observedGeneration")) >= _int(_get(deploy, "metadata", "generation"))
    detail = (
        f"deployment {check.name}: desired={desired} ready={status['readyReplicas']} "
        f"updated={status['updatedReplicas']} available={status['availableReplicas']} total={status['replicas']}"
    )
    if check.replicas is not None and desired != check.replicas:
        return False, detail + f" (expected spec.replicas={check.replicas})"
    ok = generation_ok and all(value == desired for value in status.values()) and desired > 0
    return ok, detail


def _pick_pod(check: ExecCheck, kube: Kube) -> tuple[str | None, str]:
    if check.pod is not None:
        return check.pod, ""
    pods = _items(kube, ["get", "pods", "-n", check.namespace, "-l", check.selector or ""])
    candidates = sorted(
        str(_get(p, "metadata", "name"))
        for p in pods or []
        if _get(p, "status", "phase") == "Running" and _get(p, "metadata", "deletionTimestamp") is None
    )
    if not candidates:
        return None, f"no running pod matches {check.selector!r} in {check.namespace}"
    return candidates[0], ""


def _exec(check: ExecCheck, kube: Kube) -> tuple[bool, str]:
    pod, problem = _pick_pod(check, kube)
    if pod is None:
        return False, problem
    container = ["-c", check.container] if check.container else []
    # Wrap in sh so a failing command is distinguishable from a failing kubectl exec.
    wrapped = ["sh", "-c", f'"$@"; echo "{RC_MARKER}$?"', "sh", *check.command]
    result = kube.kubectl(
        ["exec", "-n", check.namespace, pod, *container, "--", *wrapped], timeout=check.exec_timeout + 10
    )
    match = re.search(rf"{RC_MARKER}(\d+)", result.stdout)
    if match is None:
        return False, f"could not exec in {check.namespace}/{pod}: {result.output()[-300:]}"
    rc = int(match.group(1))
    output = result.stdout[: match.start()].strip()
    command = " ".join(check.command)
    succeeded = rc == 0
    if check.output_matches is not None and succeeded:
        succeeded = re.search(check.output_matches, output) is not None
    ok = succeeded if check.expect == "success" else not succeeded
    tail = output[-200:] if output else result.stderr.strip()[-200:]
    return ok, f"`{command}` in {pod}: exit {rc} (expected {check.expect}){': ' + tail if tail else ''}"


def _can_i(check: CanICheck, kube: Kube) -> tuple[bool, str]:
    groups = list(check.groups)
    parts = check.user.split(":")
    if check.user.startswith("system:serviceaccount:") and len(parts) == 4:
        groups += ["system:serviceaccounts", f"system:serviceaccounts:{parts[2]}", "system:authenticated"]
    review = {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SubjectAccessReview",
        "spec": {
            "user": check.user,
            "groups": groups,
            "resourceAttributes": {
                "namespace": check.namespace,
                "verb": check.verb,
                "group": check.api_group,
                "resource": check.resource,
                "subresource": check.subresource,
                "name": check.name,
            },
        },
    }
    result = kube.kubectl(["create", "-f", "-", "-o", "json"], stdin=json.dumps(review))
    if not result.ok:
        return False, f"SubjectAccessReview failed: {result.output()}"
    loaded: object = json.loads(result.stdout)
    allowed = _get(loaded, "status", "allowed") is True
    target = f"{check.resource}{'/' + check.subresource if check.subresource else ''}"
    scope = f" in {check.namespace}" if check.namespace else " (cluster-wide)"
    return allowed == check.allowed, (
        f"{check.user} {'can' if allowed else 'cannot'} {check.verb} {target}{scope} "
        f"(expected {'allowed' if check.allowed else 'denied'})"
    )


def _node_ready(check: NodeReadyCheck, ctx: GradeContext) -> tuple[bool, str]:
    node = ctx.cluster.resolve_node(check.node)
    data = ctx.grader.get_json(["get", "node", node])
    if data is None:
        return False, f"node {node} not found"
    status = _condition(data, "Ready")
    ready = status == "True"
    return ready == check.ready, f"node {node} Ready={status}"


def _node_exec(check: NodeExecCheck, cluster: Cluster) -> tuple[bool, str]:
    node = cluster.resolve_node(check.node)
    result = cluster.node_exec(node, check.run, timeout=60)
    succeeded = result.ok
    if check.output_matches is not None and succeeded:
        succeeded = re.search(check.output_matches, result.stdout) is not None
    ok = succeeded if check.expect == "success" else not succeeded
    tail = result.output()[-200:]
    return ok, f"on {node}: exit {result.returncode} (expected {check.expect}){': ' + tail if tail else ''}"


def _script(check: ScriptCheck, kube: Kube) -> tuple[bool, str]:
    result = proc.run(["bash", "-c", check.script], env=kube.env(), timeout=120)
    return result.ok, result.output()[-300:] or f"exit {result.returncode}"
