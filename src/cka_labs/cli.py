"""`cka` command-line interface."""

import json
import os
import platform
import shlex
import shutil
import sys
import time
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
from cka_labs.config import curriculum
from cka_labs.engine import catalog, selection
from cka_labs.engine.evaluator import CheckResult
from cka_labs.engine.lifecycle import ActiveLab, LabService, find_cluster, load_session
from cka_labs.engine.progress import Progress
from cka_labs.errors import CkaError
from cka_labs.models import DIFFICULTY_NAMES, Lab

console = Console()
err = Console(stderr=True)

app = typer.Typer(help="CKA practice labs and mock exams on disposable local clusters.", no_args_is_help=True)
lab_app = typer.Typer(help="Practice labs.", no_args_is_help=True)
cluster_app = typer.Typer(help="Manage the disposable practice clusters.", no_args_is_help=True)
node_app = typer.Typer(help="Node access (like `ssh` in the exam).", no_args_is_help=True)
dev_app = typer.Typer(help="Lab authoring and verification.", no_args_is_help=True)
app.add_typer(lab_app, name="lab")
app.add_typer(cluster_app, name="cluster")
app.add_typer(node_app, name="node")
app.add_typer(dev_app, name="dev")

BackendOpt = Annotated[
    str | None, typer.Option("--backend", "-b", help="kind (default) or kubeadm; env CKA_BACKEND")
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
    header = (
        f"[bold]{lab.id}[/bold] — {lab.title}\n"
        f"domain: {curriculum().domain(lab.domain).title} · difficulty: {difficulty_label(lab.difficulty)} · "
        f"target: {lab.estimated_minutes} min"
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
    """Install pinned kind + kubectl into the cka directory and cache images."""
    for download in tools.downloads():
        tools.install(download, log)
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
    table.add_row("exam target", f"CKA, Kubernetes v{curriculum().kubernetes_version} (verified {curriculum().verified})")
    for name in ("kind", "kubectl"):
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
    domain: Annotated[str | None, typer.Option(help="Filter by domain id")] = None,
    difficulty: Annotated[str | None, typer.Option(help="1-4 or name")] = None,
    backend: BackendOpt = None,
) -> None:
    """List available labs."""
    level = parse_difficulty(difficulty)
    stats = Progress().lab_stats()
    table = Table(header_style="bold")
    for column in ("id", "title", "domain", "lvl", "min", "backends", "done"):
        table.add_column(column)
    for lab in all_labs():
        if (domain and lab.domain != domain) or (level and lab.difficulty != level):
            continue
        if backend and backend not in lab.backends:
            continue
        s = stats.get(lab.id)
        done = f"{s.clean_passes}/{s.attempts}" if s else ""
        table.add_row(lab.id, lab.title, lab.domain, str(lab.difficulty), str(lab.estimated_minutes), ",".join(lab.backends), done)
    console.print(table)


@lab_app.command("start")
def lab_start(
    lab_id: Annotated[str | None, typer.Argument(help="Lab id; omit for an adaptive recommendation")] = None,
    backend: BackendOpt = None,
    seed: Annotated[int | None, typer.Option(help="Scenario seed (same seed = same scenario)")] = None,
) -> None:
    """Provision a lab, inject its fault, verify the broken state and show the task."""
    name = backend or os.environ.get("CKA_BACKEND", "kind")
    if lab_id is None:
        progress = Progress()
        choice = selection.recommend(
            selection.filter_labs(all_labs(), backend=name), progress.objective_stats(), progress.lab_stats()
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
    session = service.reset()
    console.print(f"[green]{session.lab_id} reset[/green]; the timer keeps running.")


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


def _active_kubeconfig() -> str:
    from cka_labs.engine import exam as exam_engine

    exam = exam_engine.load_exam()
    if exam is not None:
        return str(exam_engine.exam_kubeconfig())
    session = load_session()
    if session:
        return str(find_cluster(session.backend, session.cluster).kubeconfig)
    return str(get_backend(backend_name(None)).main().kubeconfig)


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
    domain: Annotated[str | None, typer.Option(help="architecture|workloads|networking|storage|troubleshooting")] = None,
    difficulty: Annotated[str | None, typer.Option(help="1-4 or fundamentals|intermediate|advanced|exam")] = None,
    weakest: Annotated[bool, typer.Option("--weakest", help="Target your weakest attempted objective")] = False,
    backend: BackendOpt = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Only show the choice")] = False,
) -> None:
    """Pick the next lab adaptively and start it."""
    name = backend or os.environ.get("CKA_BACKEND", "kind")
    progress = Progress()
    labs = selection.filter_labs(all_labs(), backend=name, domain=domain, difficulty=parse_difficulty(difficulty))
    pick = selection.weakest if weakest else selection.recommend
    choice = pick(labs, progress.objective_stats(), progress.lab_stats())
    console.print(f"[bold]{choice.lab.id}[/bold] {escape(choice.lab.title)}\n[dim]why: {escape(choice.reason)}[/dim]")
    if not dry_run:
        _start(choice.lab.id, name, None)


@app.command("progress")
def progress_cmd(
    as_json: Annotated[bool, typer.Option("--json", help="Export everything as JSON")] = False,
) -> None:
    """Show progress per curriculum objective and the weakest areas."""
    progress = Progress()
    if as_json:
        print(json.dumps(progress.export(), indent=2, default=str))
        return
    stats = progress.objective_stats()
    covered: dict[str, int] = {}
    for lab in all_labs():
        for objective in lab.objectives:
            covered[objective] = covered.get(objective, 0) + 1
    table = Table(header_style="bold", title="Objectives (weakness = 1 − (clean passes + 1)/(attempts + 2))")
    for column in ("objective", "labs", "attempts", "clean", "avg min", "hints", "weakness"):
        table.add_column(column)
    for domain in curriculum().domains:
        table.add_row(f"[bold]{domain.title} ({domain.weight}%)[/bold]", "", "", "", "", "", "")
        for key, title in domain.objectives.items():
            objective = f"{domain.id}/{key}"
            s = stats.get(objective)
            weakness = s.weakness if s else selection.UNTRIED_WEAKNESS
            colour = "red" if weakness > 0.5 else "yellow" if weakness > 0.3 else "green"
            table.add_row(
                f"  {title[:58]}",
                str(covered.get(objective, 0)),
                str(s.attempts if s else 0),
                str(s.clean_passes if s else 0),
                f"{s.avg_minutes:.1f}" if s and s.avg_minutes is not None else "",
                str(s.hints if s else 0),
                f"[{colour}]{weakness:.2f}[/{colour}]",
            )
    console.print(table)
    failed = progress.top_failed_checks(5)
    if failed:
        console.print("[bold]Most failed checks:[/bold] " + ", ".join(f"{lab}:{check}×{n}" for lab, check, n in failed))
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
