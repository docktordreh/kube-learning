"""Lab definition schema (lab.yaml after parameter rendering).

Student-facing text lives in task.md; everything in lab.yaml is hidden from the student
except hints, which are revealed one at a time.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Backend = Literal["kind", "kubeadm"]
Difficulty = Annotated[int, Field(ge=1, le=4)]

DIFFICULTY_NAMES: dict[int, str] = {1: "fundamentals", 2: "intermediate", 3: "advanced", 4: "exam"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --- Checks -------------------------------------------------------------------------------
# A check inspects live cluster state and never mutates graded objects.
# role=goal: must fail right after setup and pass once solved.
# role=guard: must pass right after setup and stay passing (detects collateral damage).


class _CheckBase(_Strict):
    id: str = "wait"
    description: str = ""
    role: Literal["goal", "guard"] = "goal"
    # Seconds to keep re-evaluating a failing check while grading (lets rollouts converge).
    timeout: int = Field(default=0, ge=0, le=600)


class JsonPathCheck(_CheckBase):
    """Compare `kubectl get <resource> -o jsonpath=<jsonpath>` output."""

    type: Literal["jsonpath"]
    resource: str
    namespace: str | None = None
    jsonpath: str
    op: Literal["equals", "not_equals", "matches", "not_matches", "contains", "nonempty", "empty", "gte", "lte"] = (
        "equals"
    )
    value: str | None = None

    @model_validator(mode="after")
    def _value_required(self) -> "JsonPathCheck":
        if self.op not in ("nonempty", "empty") and self.value is None:
            raise ValueError(f"op {self.op!r} needs a value")
        return self


class ExistsCheck(_CheckBase):
    type: Literal["exists"]
    resource: str
    namespace: str | None = None
    present: bool = True


class PodsReadyCheck(_CheckBase):
    """Pods matching selector: at least min_ready Ready, and (if all_ready) none unready."""

    type: Literal["pods_ready"]
    namespace: str
    selector: str
    min_ready: int = Field(default=1, ge=0)
    all_ready: bool = True


class ServiceEndpointsCheck(_CheckBase):
    """Count ready endpoint addresses in the Service's EndpointSlices."""

    type: Literal["service_endpoints"]
    namespace: str
    service: str
    min_ready: int = Field(default=1, ge=0)
    max_ready: int | None = None


class DeploymentReadyCheck(_CheckBase):
    type: Literal["deployment_ready"]
    namespace: str
    name: str
    replicas: int | None = None


class ExecCheck(_CheckBase):
    """Run a command in an existing Pod (selected by name or label selector)."""

    type: Literal["exec"]
    namespace: str
    pod: str | None = None
    selector: str | None = None
    container: str | None = None
    command: list[str]
    expect: Literal["success", "failure"] = "success"
    output_matches: str | None = None
    exec_timeout: int = Field(default=15, ge=1, le=120)

    @model_validator(mode="after")
    def _target(self) -> "ExecCheck":
        if (self.pod is None) == (self.selector is None):
            raise ValueError("exec check needs exactly one of pod or selector")
        return self


class CanICheck(_CheckBase):
    """SubjectAccessReview for a user or ServiceAccount; never persisted by the API server."""

    type: Literal["can_i"]
    user: str
    groups: list[str] = []
    verb: str
    resource: str
    api_group: str = ""
    subresource: str = ""
    namespace: str = ""
    name: str = ""
    allowed: bool = True


class NodeReadyCheck(_CheckBase):
    type: Literal["node_ready"]
    node: str
    ready: bool = True


class NodeExecCheck(_CheckBase):
    """Run a read-only shell snippet on a node."""

    type: Literal["node_exec"]
    node: str
    run: str
    expect: Literal["success", "failure"] = "success"
    output_matches: str | None = None


class ScriptCheck(_CheckBase):
    """Escape hatch: bash on the host with the read-only grader kubeconfig. Exit 0 = pass."""

    type: Literal["script"]
    script: str


Check = Annotated[
    JsonPathCheck
    | ExistsCheck
    | PodsReadyCheck
    | ServiceEndpointsCheck
    | DeploymentReadyCheck
    | ExecCheck
    | CanICheck
    | NodeReadyCheck
    | NodeExecCheck
    | ScriptCheck,
    Field(discriminator="type"),
]


# --- Setup and cleanup steps --------------------------------------------------------------


class ApplyStep(_Strict):
    """kubectl apply a rendered manifest file relative to the lab directory."""

    apply: str


class KubectlStep(_Strict):
    kubectl: list[str]
    ignore_errors: bool = False


class WaitStep(_Strict):
    """Poll a check until it passes (used to reach a stable broken state)."""

    wait: Check
    timeout: int = Field(default=180, ge=1, le=900)


class NodeStep(_Strict):
    node: str
    run: str
    ignore_errors: bool = False


class ScriptStep(_Strict):
    """bash on the host with the admin kubeconfig of the lab cluster."""

    script: str
    ignore_errors: bool = False


class CaptureStep(_Strict):
    """Record a jsonpath value after setup; checks reference it as {{captured.<name>}}."""

    capture: str
    resource: str
    namespace: str | None = None
    jsonpath: str


Step = ApplyStep | KubectlStep | WaitStep | NodeStep | ScriptStep | CaptureStep


# --- Lab ----------------------------------------------------------------------------------


class Param(_Strict):
    choices: list[str] = Field(min_length=1)


class Source(_Strict):
    """Upstream of an licensed lab: attribution and the license gate in `cka dev validate`."""

    url: str
    path: str = ""
    commit: str = ""
    license: str


class Lab(_Strict):
    id: Annotated[str, Field(pattern=r"^[a-z]+(-[a-z]+)*-[0-9]{3}$")]
    title: str
    # <cert>/<domain>/<key>, e.g. cka/networking/services. The first objective is primary:
    # it decides the lab's directory labs/<cert>/<domain>/ and its home domain.
    objectives: list[Annotated[str, Field(pattern=r"^[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+$")]] = Field(min_length=1)
    difficulty: Difficulty
    estimated_minutes: int = Field(ge=1, le=60)
    backends: list[Backend] = Field(min_length=1)
    # namespace: shares a cluster with other labs; cluster: may disrupt cluster-wide
    # behaviour (nodes, control plane, DNS) and gets its own cluster in exams.
    isolation: Literal["namespace", "cluster"] = "namespace"
    namespaces: list[str] = []
    owned: list[str] = []
    # Pinned tools (helm) and shared cluster components (traefik) the lab needs.
    requires: list[str] = []
    params: dict[str, Param] = {}
    setup: list[Step] = []
    checks: list[Check] = Field(min_length=1)
    hints: list[str] = Field(min_length=1)
    competencies: list[str] = Field(min_length=1)
    docs: list[str] = Field(min_length=1)
    cleanup: list[Step] = []
    source: Source | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "Lab":
        ids = [c.id for c in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError("check ids must be unique")
        if not any(c.role == "goal" for c in self.checks):
            raise ValueError("a lab needs at least one goal check")
        for check in self.checks:
            if check.id == "wait" or not check.description:
                raise ValueError("every check needs an id and a description")
        for item in self.owned:
            kind, sep, name = item.partition("/")
            if not sep or not kind or not name or "*" in item:
                raise ValueError(f"owned entries must be explicit kind/name, got {item!r}")
        return self

    @property
    def goal_checks(self) -> list[Check]:
        return [c for c in self.checks if c.role == "goal"]

    @property
    def cert(self) -> str:
        """Certification of the primary objective."""
        return self.objectives[0].split("/")[0]

    @property
    def domain(self) -> str:
        """Primary domain, qualified by its certification (e.g. cka/networking)."""
        return self.objectives[0].rpartition("/")[0]

    @property
    def certs(self) -> list[str]:
        return list(dict.fromkeys(o.split("/")[0] for o in self.objectives))

    def domain_in(self, cert: str) -> str | None:
        """The lab's domain id within `cert` (first matching objective), or None if it has none."""
        return next((o.split("/")[1] for o in self.objectives if o.startswith(f"{cert}/")), None)
