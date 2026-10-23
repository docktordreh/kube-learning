"""`cka` command-line interface."""

import json
import os
import platform
import shlex
import shutil
import sys
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.markup import escape
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from cka_labs import paths, proc, tools
from cka_labs.backends import Cluster, get_backend
from cka_labs.backends.kind import KindCluster
from cka_labs.config import DEFAULT_CERT, curricula, curriculum, toolchain
from cka_labs.engine import catalog, selection
from cka_labs.engine.exam import ExamService, ExamState, load_exam
from cka_labs.engine.evaluator import CheckResult
from cka_labs.engine.lifecycle import ActiveLab, LabService, find_cluster, load_session
from cka_labs.engine.progress import HALF_LIFE_DAYS, Progress, readiness
from cka_labs.errors import CkaError
from cka_labs.models import DIFFICULTY_NAMES, Lab

console = Console()
err = Console(stderr=True)

app = typer.Typer(
    help="Kubernetes certification (CKA, CKAD, CKS) practice labs and mock exams on disposable local clusters.",
    no_args_is_help=True,
)
lab_app = typer.Typer(help="Practice labs.", no_args_is_help=True)
cluster_app = typer.Typer(help="Manage the disposable practice clusters.", no_args_is_help=True)
node_app = typer.Typer(help="Node access (like `ssh` in the exam).", no_args_is_help=True)
dev_app = typer.Typer(help="Lab authoring and verification.", no_args_is_help=True)
image_app = typer.Typer(help="Container images you build for labs.", no_args_is_help=True)
exam_app = typer.Typer(help="Timed mock examinations (no hints or solutions).", no_args_is_help=True)
app.add_typer(lab_app, name="lab")
app.add_typer(cluster_app, name="cluster")
app.add_typer(node_app, name="node")
app.add_typer(dev_app, name="dev")
app.add_typer(exam_app, name="exam")
app.add_typer(image_app, name="image")

BackendOpt = Annotated[
    str | None, typer.Option("--backend", "-b", help="kind (default) or kubeadm; env CKA_BACKEND")
]
CertOpt = Annotated[
    str | None, typer.Option("--cert", "-c", help="Certification: cka (default), ckad, cks; env CKA_CERT")
]


def log(message: str) -> None:
    err.print(f"[dim]» {escape(message)}[/dim]")


def backend_name(option: str | None) -> str:
    session = load_session()
    if option:
        return option
    if session:
        return session.backend
    return os.environ.get("CKA_BACKEND", "kind")


def cert_name(option: str | None) -> str:
    name = option or os.environ.get("CKA_CERT") or DEFAULT_CERT
    curriculum(name)  # unknown certification -> CkaError
    return name


def parse_difficulty(value: str | None) -> int | None:
    if value is None:
        return None
    if value.isdigit() and int(value) in DIFFICULTY_NAMES:
        return int(value)
    for level, name in DIFFICULTY_NAMES.items():
        if name.startswith(value.lower()):
            return level
    raise CkaError(f"unknown difficulty {value!r}: 1-4 or {', '.join(DIFFICULTY_NAMES.values())}")


def difficulty_label(level: int) -> str:
    return f"{level} {DIFFICULTY_NAMES[level]}"


def all_labs() -> list[Lab]:
    return [source.meta() for source in catalog.discover().values()]


def show_results(results: list[CheckResult]) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("", width=2)
    table.add_column("check")
    table.add_column("detail", overflow="fold")
    for r in results:
        mark = "[green]✔[/green]" if r.passed else "[red]✘[/red]"
        label = escape(r.description) + (" [dim](guard)[/dim]" if r.role == "guard" else "")
        table.add_row(mark, label, f"[dim]{escape(r.detail)}[/dim]")
    console.print(table)


def fmt_minutes(seconds: float) -> str:
    return f"{int(seconds // 60)}m{int(seconds % 60):02d}s"


def show_task(lab: Lab, task: str, kubeconfig: str) -> None:
    certs = ", ".join(curriculum(cert).exam for cert in lab.certs)
    header = (
        f"[bold]{lab.id}[/bold] — {lab.title}\n"
        f"domain: {curriculum(lab.cert).domain(lab.domain_in(lab.cert) or '').title} · "
        f"difficulty: {difficulty_label(lab.difficulty)} · target: {lab.estimated_minutes} min · counts for {certs}"
    )
    console.print(Panel(header, expand=False))
    console.print(Markdown(task))
    console.print(
        f"\n[dim]Cluster access:[/dim]  export KUBECONFIG={kubeconfig}   [dim](or run `cka shell`)[/dim]\n"
        "[dim]Nodes:[/dim] cka ssh <node>   [dim]Grade:[/dim] cka lab check   [dim]Stuck:[/dim] cka lab hint"
    )


# --- setup / doctor ---------------------------------------------------------------------


@app.command()
def setup(
    images: Annotated[bool, typer.Option(help="Pull node and lab images for offline use")] = True,
) -> None:
    """Install pinned kind, kubectl, kubectl-convert and helm, and cache components and images."""
    for download in tools.downloads():
        tools.install(download, log)
    for component in toolchain().components:
        tools.cache_artifact(component, log)
    if images:
        tools.pull_images(log)
    console.print(f"[green]ready.[/green] Tools in {paths.bin_dir()}. Next: [bold]cka lab start[/bold]")


@app.command()
def doctor() -> None:
    """Report host capabilities, tool versions and backend readiness."""
    table = Table(show_header=False)
    table.add_row("platform", f"{sys.platform} {platform.machine()}")
    table.add_row("python", sys.version.split()[0])
    table.add_row("data dir", str(paths.home()))
    for c in curricula().values():
        table.add_row(f"curriculum {c.id}", f"{c.exam}, Kubernetes v{c.kubernetes_version} (verified {c.verified})")
    for name in ("kind", "kubectl", "kubectl-convert", "helm"):
        table.add_row(name, tools.installed_version(name) or "[red]missing (cka setup)[/red]")
    table.add_row("docker", "ok" if shutil.which("docker") and proc.run(["docker", "info"], timeout=20).ok else "[red]unavailable[/red]")
    table.add_row("/dev/kvm", "present" if os.path.exists("/dev/kvm") else "absent (kubeadm backend falls back to slow emulation)")
    table.add_row("vagrant", shutil.which("vagrant") or "missing (needed only for the kubeadm backend)")
    for name in ("kind", "kubeadm"):
        problems = get_backend(name).problems()
        table.add_row(f"backend {name}", "[green]ready[/green]" if not problems else "[yellow]" + "; ".join(problems) + "[/yellow]")
    console.print(table)


# --- cluster ----------------------------------------------------------------------------


@cluster_app.command("up")
def cluster_up(backend: BackendOpt = None) -> None:
    """Create (or reconnect to) the practice cluster."""
    cluster = get_backend(backend_name(backend)).main()
    log(f"ensuring cluster {cluster.name}")
    cluster.ensure()
    console.print(f"[green]cluster {cluster.name} ready[/green]; export KUBECONFIG={cluster.kubeconfig}")


@cluster_app.command("down")
def cluster_down(
    backend: BackendOpt = None,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation")] = False,
) -> None:
    """Delete the cka-managed practice clusters of a backend (never any other cluster)."""
    b = get_backend(backend_name(backend))
    clusters = [b.main(), *(b.extra(i) for i in range(1, b.max_extra_clusters + 1))]
    existing = [c for c in clusters if c.exists()]
    if not existing:
        console.print("nothing to delete")
        return
    names = ", ".join(c.name for c in existing)
    if not yes and not typer.confirm(f"Delete cka cluster(s) {names}?"):
        raise typer.Abort()
    for cluster in existing:
        log(f"deleting {cluster.name}")
        cluster.delete()
    session = load_session()
    if session and session.backend == b.name:
        paths.state_dir().joinpath("lab.json").unlink(missing_ok=True)


@cluster_app.command("status")
def cluster_status(backend: BackendOpt = None) -> None:
    b = get_backend(backend_name(backend))
    cluster = b.main()
    if not cluster.exists():
        console.print(f"{cluster.name}: not created (cka cluster up)")
        return
    console.print(f"{cluster.name}: exists; kubeconfig {cluster.kubeconfig}")
    result = cluster.admin().kubectl(["get", "nodes", "-o", "wide"])
    console.print(escape(result.output()))


# --- lab --------------------------------------------------------------------------------


@lab_app.command("list")
def lab_list(
    cert: Annotated[str | None, typer.Option("--cert", "-c", help="Only labs counting for cka, ckad, cks, ...")] = None,
    domain: Annotated[str | None, typer.Option(help="Filter by domain id of --cert (default cka)")] = None,
    difficulty: Annotated[str | None, typer.Option(help="1-4 or name")] = None,
    backend: BackendOpt = None,
) -> None:
    """List available labs (all certifications unless --cert is given)."""
    if domain and not cert:
        cert = cert_name(None)
    if cert:
        curriculum(cert)
    level = parse_difficulty(difficulty)
    stats = Progress().lab_stats()
    table = Table(header_style="bold")
    for column in ("id", "title", "domain", "certs", "lvl", "min", "backends", "done"):
        table.add_column(column)
    for lab in all_labs():
        if (cert and cert not in lab.certs) or (domain and lab.domain_in(cert or "") != domain):
            continue
        if (level and lab.difficulty != level) or (backend and backend not in lab.backends):
            continue
        s = stats.get(lab.id)
        done = f"{s.clean_passes}/{s.attempts}" if s else ""
        shown = f"{cert}/{lab.domain_in(cert)}" if cert else lab.domain
        table.add_row(
            lab.id, lab.title, shown, ",".join(lab.certs), str(lab.difficulty), str(lab.estimated_minutes),
            ",".join(lab.backends), done,
        )
    console.print(table)


@lab_app.command("start")
def lab_start(
    lab_id: Annotated[str | None, typer.Argument(help="Lab id; omit for an adaptive recommendation")] = None,
    backend: BackendOpt = None,
    cert: CertOpt = None,
    seed: Annotated[int | None, typer.Option(help="Scenario seed (same seed = same scenario)")] = None,
) -> None:
    """Provision a lab, inject its fault, verify the broken state and show the task."""
    name = backend or os.environ.get("CKA_BACKEND", "kind")
    if lab_id is None:
        progress = Progress()
        target = cert_name(cert)
        choice = selection.recommend(
            selection.filter_labs(all_labs(), backend=name, cert=target),
            progress.objective_stats(),
            progress.lab_stats(),
            cert=target,
        )
        log(f"recommended {choice.lab.id}: {choice.reason}")
        lab_id = choice.lab.id
    _start(lab_id, name, seed)


def _start(lab_id: str, backend: str, seed: int | None) -> None:
    service = LabService(log=log)
    session, lab = service.start(lab_id, backend, seed)
    cluster = find_cluster(session.backend, session.cluster)
    show_task(lab, service.task(session), str(cluster.kubeconfig))


@lab_app.command("status")
def lab_status() -> None:
    """Show the active lab, elapsed time and task."""
    service = LabService(log=log)
    session = service.require_session()
    lab = service.lab(session)
    cluster = find_cluster(session.backend, session.cluster)
    show_task(lab, service.task(session), str(cluster.kubeconfig))
    state = "[green]solved[/green]" if session.solved else "in progress"
    console.print(
        f"\n{state} · elapsed {fmt_minutes(time.time() - session.started_at)} / target {lab.estimated_minutes}m · "
        f"hints {session.hints_used}/{len(lab.hints)} · seed {session.seed}"
    )


@lab_app.command("hint")
def lab_hint() -> None:
    """Reveal the next progressive hint."""
    number, total, text = LabService(log=log).hint()
    console.print(Panel(Markdown(text), title=f"hint {number}/{total}", expand=False))


@lab_app.command("check")
def lab_check() -> None:
    """Grade the live cluster state."""
    service = LabService(log=log)
    before = service.require_session().solved
    session, results = service.check()
    show_results(results)
    if all(r.passed for r in results):
        lab = service.lab(session)
        console.print(f"\n[bold green]PASSED[/bold green] in {fmt_minutes(time.time() - session.started_at)} "
                      f"(target {lab.estimated_minutes}m, hints {session.hints_used}{', solution viewed' if session.solution_viewed else ''})")
        if not before:
            _debrief(service, session, lab)
        raise typer.Exit(0)
    console.print("\n[bold red]NOT YET[/bold red] — fix the failing checks and run `cka lab check` again.")
    raise typer.Exit(1)


def _debrief(service: LabService, session: ActiveLab, lab: Lab) -> None:
    explanation = service.explanation(session)
    if explanation:
        console.print(Panel(Markdown(explanation), title="debrief", expand=False))
    console.print("[bold]Competencies:[/bold] " + "; ".join(lab.competencies))
    console.print("[bold]Docs:[/bold]\n  " + "\n  ".join(lab.docs))
    if lab.source is not None:
        console.print(f"[dim]Adapted from {escape(lab.source.url)} ({escape(lab.source.license)})[/dim]")
    console.print("[dim]Reference solution: cka lab solution · next: cka lab stop && cka lab start[/dim]")


@lab_app.command("solution")
def lab_solution(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip confirmation")] = False,
) -> None:
    """Show the reference solution (counts the attempt as not clean)."""
    service = LabService(log=log)
    session = service.require_session()
    if not session.solved and not yes and not typer.confirm("Not solved yet. Reveal the solution?"):
        raise typer.Abort()
    script, explanation = service.solution()
    console.print(Panel(Syntax(script.strip(), "bash", word_wrap=True), title="reference solution", expand=False))
    if explanation:
        console.print(Panel(Markdown(explanation), title="explanation", expand=False))
    lab = service.lab(session)
    console.print("[bold]Docs:[/bold]\n  " + "\n  ".join(lab.docs))


@lab_app.command("reset")
def lab_reset() -> None:
    """Restore the lab's initial broken state (same scenario seed)."""
    service = LabService(log=log)
    solved = service.require_session().solved
    session = service.reset()
    note = "new attempt started" if solved else "the timer keeps running"
    console.print(f"[green]{session.lab_id} reset[/green]; {note}.")


@lab_app.command("stop")
def lab_stop() -> None:
    """Clean up the active lab (only resources the lab owns)."""
    LabService(log=log).stop()
    console.print("lab stopped and cleaned up")


@lab_app.command("env")
def lab_env() -> None:
    """Print shell exports for the active cluster: eval "$(cka lab env)"."""
    print(f"export KUBECONFIG={_active_kubeconfig()}")
    print(f'export PATH="{paths.bin_dir()}:$PATH"')


# --- exam -------------------------------------------------------------------------------


@exam_app.command("start")
def exam_start(
    backend: BackendOpt = None,
    cert: CertOpt = None,
    duration: Annotated[int, typer.Option("--duration", help="Time limit in minutes")] = 120,
    pass_percent: Annotated[int, typer.Option("--pass-percent", help="Locally computed passing threshold")] = 66,
    seed: Annotated[int | None, typer.Option(help="Reproduce the same task selection")] = None,
) -> None:
    """Provision a balanced timed mock exam. The timer starts after setup completes."""
    service = ExamService(log=log)
    exam = service.start(
        backend_name(backend), cert=cert_name(cert), duration_minutes=duration, pass_percent=pass_percent, seed=seed
    )
    console.print(
        Panel(
            f"[bold]{curriculum(exam.cert).exam} exam {exam.exam_id} started[/bold]\n"
            f"{len(exam.tasks)} tasks · {exam.duration_minutes} minutes · local pass threshold {exam.pass_percent}%\n"
            f"seed {exam.seed} · this is not an official {curriculum(exam.cert).exam} score",
            title="mock exam",
            expand=False,
        )
    )
    _show_exam_task(exam, exam.tasks[0])


@exam_app.command("status")
def exam_status() -> None:
    """Show remaining time and task states without grading or revealing answers."""
    exam = ExamService().require()
    _show_exam_status(exam)


@exam_app.command("task")
def exam_task(
    number: Annotated[int | None, typer.Argument(help="Task number; omit to open the next pending task")] = None,
) -> None:
    """Open an exam task. This is the only task text exposed in strict exam mode."""
    service = ExamService()
    exam, task = service.task(number)
    _show_exam_task(exam, task)


@exam_app.command("skip")
def exam_skip(
    number: Annotated[int | None, typer.Argument(help="Task number; omit to skip the next pending task")] = None,
) -> None:
    """Skip a task; it remains available with `cka exam task N`."""
    exam = ExamService().skip(number)
    console.print(f"task skipped; {sum(task.status == 'pending' for task in exam.tasks)} pending")


@exam_app.command("submit")
def exam_submit() -> None:
    """Evaluate every non-skipped task, record the local score and clean up."""
    service = ExamService(log=log)
    exam, reports = service.submit()
    for task in exam.tasks:
        results = reports.get(task.number, [])
        mark = "[green]PASS[/green]" if task.status == "passed" else "[red]FAIL[/red]" if task.status == "failed" else "[yellow]SKIP[/yellow]"
        console.print(f"{mark} task {task.number}: {task.lab_id} ({task.points} points)")
        if results:
            show_results(results)
    percent = (exam.score or 0) / (exam.max_score or 1) * 100
    outcome = "PASSED" if percent >= exam.pass_percent else "FAILED"
    console.print(
        f"\n[bold]{outcome}[/bold] — {exam.score}/{exam.max_score} points ({percent:.1f}%), "
        f"threshold {exam.pass_percent}%; local practice result only"
    )


@exam_app.command("results")
def exam_results(
    as_json: Annotated[bool, typer.Option("--json", help="Print the stored result as JSON")] = False,
) -> None:
    """Show the most recent submitted mock-exam result."""
    report = Progress().exam_report()
    if report is None:
        raise CkaError("no submitted exam results")
    if as_json:
        print(json.dumps(report, indent=2, default=str))
        return
    percent = report.get("percent", 0)
    passed = bool(report.get("passed"))
    console.print(
        f"[bold {'green' if passed else 'red'}]{'PASSED' if passed else 'FAILED'}[/bold {'green' if passed else 'red'}] "
        f"— {report.get('score')}/{report.get('max_score')} points ({percent}%), "
        f"threshold {report.get('pass_percent')}%\nseed: {report.get('seed')}"
    )
    tasks = report.get("tasks")
    if isinstance(tasks, list):
        for item in tasks:
            if isinstance(item, dict):
                console.print(f"  task {item.get('number')}: {item.get('lab_id')} — {item.get('status')}")


@exam_app.command("abort")
def exam_abort(
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Do not ask for confirmation")] = False,
) -> None:
    """End an exam without a score and clean its managed resources."""
    service = ExamService(log=log)
    exam = service.require()
    if not yes and not typer.confirm("Abort the exam and clean up its tasks?"):
        raise typer.Abort()
    service.cleanup(exam)
    for task in exam.tasks:
        service.progress.finish_attempt(task.attempt_id, "abandoned")
    service.progress.finish_exam(exam.exam_id, 0, exam.max_score or 0, {"aborted": True, "exam_id": exam.exam_id})
    from cka_labs.engine.exam import clear_exam

    clear_exam()
    console.print("exam aborted; managed resources cleaned")


def _show_exam_status(exam: ExamState) -> None:
    table = Table(header_style="bold")
    table.add_column("#")
    table.add_column("lab")
    table.add_column("domain")
    table.add_column("points")
    table.add_column("status")
    for task in exam.tasks:
        colour = {"pending": "yellow", "skipped": "dim", "passed": "green", "failed": "red"}[task.status]
        table.add_row(str(task.number), task.lab_id, task.domain, str(task.points), f"[{colour}]{task.status}[/{colour}]")
    console.print(table)
    remaining_seconds = max(0, int(exam.duration_minutes * 60 - (time.time() - exam.started_at)))
    console.print(f"remaining: {remaining_seconds // 60}m{remaining_seconds % 60:02d}s · task: `cka exam task N`")


def _show_exam_task(exam: ExamState, task: object) -> None:
    from cka_labs.engine.exam import ExamTask

    if not isinstance(task, ExamTask):
        raise CkaError("invalid exam task")
    source = catalog.get(task.lab_id)
    lab = source.load(task.values)
    show_task(lab, source.read("task.md", task.values), str(find_cluster(task.backend, task.cluster).kubeconfig))
    console.print(f"\n[dim]Exam task {task.number}/{len(exam.tasks)} · {task.points} points · no hints in exam mode[/dim]")


def _active_kubeconfig() -> str:
    from cka_labs.engine import exam as exam_engine

    exam = exam_engine.load_exam()
    if exam is not None:
        return str(exam_engine.exam_kubeconfig())
    session = load_session()
    if session:
        return str(find_cluster(session.backend, session.cluster).kubeconfig)
    return str(get_backend(backend_name(None)).main().kubeconfig)


def _lab_cluster() -> Cluster:
    """The cluster labs work on: CKA_CLUSTER (set for lab setup scripts), else the active exam's
    or lab's cluster, else the backend's main cluster."""
    if os.environ.get("CKA_CLUSTER"):
        return find_cluster(backend_name(None), os.environ["CKA_CLUSTER"])
    from cka_labs.engine import exam as exam_engine

    exam = exam_engine.load_exam()
    if exam is not None:
        return get_backend(exam.backend).main()
    session = load_session()
    if session:
        return find_cluster(session.backend, session.cluster)
    return get_backend(backend_name(None)).main()


@image_app.command("load")
def image_load(
    images: Annotated[list[str] | None, typer.Argument(help="Images in the host's Docker, e.g. myapp:2.0")] = None,
    archive: Annotated[
        Path | None, typer.Option(help="Load an image archive instead (docker save, podman save, OCI)")
    ] = None,
) -> None:
    """Copy images you built on this host into every node of the lab cluster (kind backend).

    Never pulls: an image missing from the host's Docker is an error. Pods then use it with
    `imagePullPolicy: Never` or `IfNotPresent`."""
    if bool(images) == (archive is not None):
        raise CkaError("give image names or --archive, not both")
    cluster = _lab_cluster()
    if not isinstance(cluster, KindCluster):
        raise CkaError("`cka image load` supports the kind backend only")
    cluster.admin().verify_marker()
    if archive is not None:
        if not archive.is_file():
            raise CkaError(f"{archive} is not a file")
        cluster.load_archive(archive.resolve())
        console.print(f"loaded {archive} into {cluster.name}")
        return
    names = images or []
    missing = [name for name in names if not proc.run(["docker", "image", "inspect", name], timeout=30).ok]
    if missing:
        raise CkaError(f"not in the host's Docker: {', '.join(missing)} (build or pull it first)")
    cluster.load_images(names)
    console.print(f"loaded {', '.join(names)} into {cluster.name}")


@app.command()
def shell() -> None:
    """Open a sub-shell wired to the practice cluster (KUBECONFIG, kubectl, alias k)."""
    kubeconfig = _active_kubeconfig()
    user_shell = os.environ.get("SHELL", "/bin/bash")
    rc = paths.ensure(paths.state_dir()) / "shellrc"
    rc.write_text(
        "[ -f ~/.bashrc ] && . ~/.bashrc\n"
        "alias k=kubectl\n"
        "source <(kubectl completion bash) 2>/dev/null && complete -o default -F __start_kubectl k\n"
        "PS1='(cka) '\"$PS1\"\n"
    )
    env = {"KUBECONFIG": kubeconfig, "CKA_SHELL": "1"}
    console.print(f"[dim]KUBECONFIG={kubeconfig}; exit the shell to return.[/dim]")
    argv = ["bash", "--rcfile", str(rc), "-i"] if user_shell.endswith("bash") or not shutil.which(user_shell) else [user_shell]
    raise typer.Exit(proc.interactive(argv, env=env))


# --- nodes ------------------------------------------------------------------------------


def _node_cluster(node: str) -> Cluster:
    """The managed cluster owning `node` (node names are unique across cka clusters)."""
    name = backend_name(None)
    owner = get_backend(name).owns_node(node)
    if owner is not None:
        return owner
    session = load_session()
    if session:
        return find_cluster(session.backend, session.cluster)
    return get_backend(name).main()


@app.command()
def ssh(node: Annotated[str, typer.Argument(help="Node name as shown by `kubectl get nodes`")]) -> None:
    """Root shell on a cluster node (the exam's `ssh <node>`)."""
    cluster = _node_cluster(node)
    raise typer.Exit(cluster.node_shell(cluster.resolve_node(node)))


@node_app.command("exec")
def node_exec(
    node: str,
    command: Annotated[list[str] | None, typer.Argument(help="Command; reads a script from stdin if omitted")] = None,
) -> None:
    """Run a command (or a stdin script) as root on a node."""
    cluster = _node_cluster(node)
    script = shlex.join(command) if command else sys.stdin.read()
    result = cluster.node_exec(cluster.resolve_node(node), script, timeout=900)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    raise typer.Exit(result.returncode)


@node_app.command("list")
def node_list(backend: BackendOpt = None) -> None:
    cluster = get_backend(backend_name(backend)).main()
    for logical, actual in cluster.nodes().items():
        console.print(f"{actual}  [dim]({logical})[/dim]")


# --- practice & progress ----------------------------------------------------------------


@app.command()
def practice(
    cert: CertOpt = None,
    domain: Annotated[str | None, typer.Option(help="Domain id of the certification (see `cka progress`)")] = None,
    difficulty: Annotated[str | None, typer.Option(help="1-4 or fundamentals|intermediate|advanced|exam")] = None,
    weakest: Annotated[bool, typer.Option("--weakest", help="Target your weakest attempted objective")] = False,
    backend: BackendOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only show the choice")] = False,
) -> None:
    """Pick the next lab adaptively for one certification and start it."""
    name = backend or os.environ.get("CKA_BACKEND", "kind")
    target = cert_name(cert)
    progress = Progress()
    labs = selection.filter_labs(
        all_labs(), backend=name, cert=target, domain=domain, difficulty=parse_difficulty(difficulty)
    )
    pick = selection.weakest if weakest else selection.recommend
    choice = pick(labs, progress.objective_stats(), progress.lab_stats(), cert=target)
    console.print(f"[bold]{choice.lab.id}[/bold] {escape(choice.lab.title)}\n[dim]why: {escape(choice.reason)}[/dim]")
    if not dry_run:
        _start(choice.lab.id, name, None)


def _pace(pace: float) -> str:
    colour = "red" if pace > 2 else "yellow" if pace > 1 else "green"
    return f"[{colour}]{pace:.1f}×[/{colour}]"


def _check_description(lab_id: str, check_id: str) -> str:
    """Unrendered description from lab.yaml (placeholders such as {{app}} stay visible)."""
    try:
        checks = catalog.get(lab_id).raw.get("checks")
    except CkaError:
        return ""
    for check in checks if isinstance(checks, list) else []:
        if isinstance(check, dict) and check.get("id") == check_id:
            return str(check.get("description", ""))
    return ""


def _lab_history(progress: Progress, lab_id: str, as_json: bool) -> None:
    catalog.get(lab_id)  # unknown lab -> CkaError
    history = progress.lab_history(lab_id)
    if as_json:
        print(json.dumps(history, indent=2, default=str))
        return
    table = Table(header_style="bold", title=f"{lab_id} attempts")
    for column in ("#", "started", "mode", "status", "min", "target", "hints", "solution", "checks", "failed checks"):
        table.add_column(column)
    for a in history:
        table.add_row(
            str(a["id"]),
            time.strftime("%Y-%m-%d %H:%M", time.localtime(a["started_at"])),
            a["mode"],
            a["status"],
            f"{(a['ended_at'] - a['started_at']) / 60:.1f}" if a["ended_at"] is not None else "",
            str(a["estimated_minutes"] or ""),
            f"{a['hints_used']}/{a['hints_total']}" if a["hints_total"] is not None else str(a["hints_used"]),
            "yes" if a["solution_viewed"] else "",
            str(a["checks_run"]),
            escape(", ".join(f"{check}×{n}" for check, n in a["failed_checks"].items())),
        )
    console.print(table if history else f"no attempts of {lab_id} yet")


@app.command("progress")
def progress_cmd(
    lab_id: Annotated[str | None, typer.Argument(help="Show the attempt history of one lab")] = None,
    cert: CertOpt = None,
    as_json: Annotated[bool, typer.Option("--json", help="Export everything as JSON")] = False,
) -> None:
    """Show progress per curriculum objective of one certification, exam readiness and the most failed checks."""
    progress = Progress()
    if lab_id is not None:
        _lab_history(progress, lab_id, as_json)
        return
    if as_json:
        print(json.dumps(progress.export(), indent=2, default=str))
        return
    target = curriculum(cert_name(cert))
    stats = progress.objective_stats()
    covered: dict[str, int] = {}
    for lab in all_labs():
        for objective in lab.objectives:
            covered[objective] = covered.get(objective, 0) + 1
    table = Table(
        header_style="bold",
        title=f"{target.exam} objectives (weakness = 1 − (Σw·credit + 1)/(Σw + 2); hints cost up to 0.5 credit per pass; "
        f"w halves every {HALF_LIFE_DAYS} days; pace = time to pass ÷ target; readiness = mean mastery, "
        "mastery = max(0, 1 − 2·weakness))",
    )
    for column in ("objective", "labs", "attempts", "clean", "credit", "avg min", "pace", "hints", "weakness"):
        table.add_column(column)
    weighted = total_weight = 0.0
    for domain in target.domains:
        ids = [f"{target.id}/{domain.id}/{key}" for key in domain.objectives]
        practisable = [objective for objective in ids if covered.get(objective)]
        ready = readiness(stats, practisable)
        if practisable:
            weighted += domain.weight * ready
            total_weight += domain.weight
        table.add_row(
            f"[bold]{domain.title} ({domain.weight}%)[/bold]", "", "", "", "", "", "", "",
            f"[bold]ready {ready:.0%}[/bold]" if practisable else "",
        )
        for key, title in domain.objectives.items():
            objective = f"{target.id}/{domain.id}/{key}"
            s = stats.get(objective)
            weakness = s.weakness if s else selection.UNTRIED_WEAKNESS
            colour = "red" if weakness > 0.5 else "yellow" if weakness > 0.3 else "green"
            table.add_row(
                f"  {title[:58]}",
                str(covered.get(objective, 0)),
                str(s.attempts if s else 0),
                str(s.clean_passes if s else 0),
                f"{s.credit:.1f}" if s else "0",
                f"{s.avg_minutes:.1f}" if s and s.avg_minutes is not None else "",
                _pace(s.pace) if s and s.pace is not None else "",
                str(s.hints if s else 0),
                f"[{colour}]{weakness:.2f}[/{colour}]",
            )
    console.print(table)
    if total_weight:
        console.print(
            f"[bold]{target.exam} exam readiness: {weighted / total_weight:.0%}[/bold] "
            "[dim](curriculum-weighted; objectives without labs are excluded)[/dim]"
        )
    failed = progress.top_failed_checks(5)
    if failed:
        checks = Table(header_style="bold", title="Most failed checks (first try = knowledge gap; runs include retries)")
        for column in ("lab", "check", "description", "first try", "attempts", "runs"):
            checks.add_column(column)
        for f in failed:
            checks.add_row(
                f.lab_id, f.check_id, escape(_check_description(f.lab_id, f.check_id)),
                str(f.first_try), str(f.attempts), str(f.runs),
            )
        console.print(checks)
    exams = progress.exams()
    if exams:
        last = exams[-1]
        if last.get("score") is not None:
            console.print(f"[bold]Last mock exam:[/bold] {last['score']}/{last['max_score']} (pass ≥ {last['pass_percent']}%)")


# --- dev --------------------------------------------------------------------------------


@dev_app.command("validate")
def dev_validate() -> None:
    """Statically validate every lab (schema, curriculum mapping, files, images)."""
    from cka_labs.engine.validation import validate_all

    problems = validate_all()
    if problems:
        for problem in problems:
            err.print(f"[red]✘[/red] {escape(problem)}")
        raise typer.Exit(1)
    console.print(f"[green]{len(catalog.discover())} labs valid[/green]")


@dev_app.command("verify")
def dev_verify(
    lab_ids: Annotated[list[str] | None, typer.Argument(help="Labs to verify (default: all for the backend)")] = None,
    backend: BackendOpt = None,
    seed: Annotated[int, typer.Option(help="Scenario seed")] = 1,
) -> None:
    """Run the full conformance cycle against a real cluster (see docs/authoring.org)."""
    from cka_labs.engine.conformance import verify_lab

    name = backend or os.environ.get("CKA_BACKEND", "kind")
    ids = lab_ids or [lab.id for lab in all_labs() if name in lab.backends]
    failures = 0
    for lab_id in ids:
        report = verify_lab(lab_id, name, seed, log)
        status = "[green]PASS[/green]" if report.ok else "[red]FAIL[/red]"
        console.print(f"{status} {lab_id} ({report.seconds:.0f}s)")
        for line in report.lines:
            console.print(f"    {escape(line)}")
        failures += 0 if report.ok else 1
    raise typer.Exit(1 if failures else 0)


def main() -> None:
    try:
        app()
    except CkaError as exc:
        err.print(f"[red]error:[/red] {escape(str(exc))}")
        sys.exit(2)


if __name__ == "__main__":
    main()
