"""The `ab` command: validate, compile, run, doctor and ui."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import signal
import sys
import webbrowser
from collections.abc import Sequence
from importlib.metadata import entry_points
from importlib.util import find_spec
from pathlib import Path

from agentbuilder import __version__
from agentbuilder.approvals import terminal_approver
from agentbuilder.compile import (
    CompiledAgent,
    CompileError,
    approval_needed,
    compile_agent,
    to_fabric_config,
    to_guardrails_yaml,
    to_nat_yaml,
    to_opa_bundle,
    to_openshell_policy,
    to_openshell_provider_profile,
    to_openshell_yaml,
    unapproved_live_tools,
)
from agentbuilder.evals import CaseResult
from agentbuilder.gateway import LocalGateway, default_audit_log
from agentbuilder.models import probe_tool_calling, resolve_model
from agentbuilder.models.credentials import CredentialError
from agentbuilder.runtime import RUNNER_GROUP, RunnerNotInstalled, credential_env, load_runner
from agentbuilder.spec import AgentSpec, SpecError
from agentbuilder.tools import ToolCatalog
from agentbuilder.ui import MIN_NODE, UiSession, find_web_dir, node_version

FORMATS = ("nat", "fabric", "policy", "provider", "opa", "guardrails")
GOOGLE_HELP = """To sign in once (free; about 5 minutes):
  1. console.cloud.google.com -> new project -> APIs & Services -> enable: Gmail API, Google Calendar API, Sheets API
  2. OAuth consent screen -> External -> add yourself as a Test user
  3. Credentials -> Create credentials -> OAuth client ID -> Application type: Desktop app -> download the JSON
  4. ab auth google --client-secret ~/Downloads/client_secret_....json
While the app is in "Testing" status, Google expires the sign-in after 7 days: just run step 4 again."""


def load_catalog(ref: str | None) -> ToolCatalog:
    """`--tools module:attribute` (a ToolCatalog or a function returning one); default: the repository's demo tools."""
    if ref:
        module_name, _, attr = ref.partition(":")
        if not attr:
            raise SystemExit("--tools must look like module:attribute, for example my_tools:catalog")
        target = getattr(importlib.import_module(module_name), attr)
        catalog = target() if callable(target) else target
        if not isinstance(catalog, ToolCatalog):
            raise SystemExit(f"{ref} is not a ToolCatalog (or a function returning one)")
        return catalog
    return _with_library(_demo_catalog())


def _with_library(catalog: ToolCatalog) -> ToolCatalog:
    from agentbuilder.library import personal_catalog

    return personal_catalog(catalog)


def _demo_catalog() -> ToolCatalog:
    tools_dir = next(
        (
            p / "packages" / "mcp-tools"
            for p in [Path.cwd(), *Path.cwd().parents]
            if (p / "packages" / "mcp-tools").is_dir()
        ),
        None,
    )
    if tools_dir is None:
        return ToolCatalog()
    sys.path.insert(0, str(tools_dir))
    from demo_tools import TOOLS  # type: ignore[import-not-found]  # the repository's demo tools

    return ToolCatalog().add_tools("demo", TOOLS, command=sys.executable, args=[str(tools_dir / "demo_server.py")])


def _load(spec_path: str, tools: str | None) -> tuple[AgentSpec, CompiledAgent]:
    spec = AgentSpec.load(spec_path)
    return spec, compile_agent(spec, load_catalog(tools))


def cmd_validate(args: argparse.Namespace) -> int:
    spec, compiled = _load(args.spec, args.tools)
    print(f"ok: {spec.name} runs in {compiled.model.agent_mode} mode with {len(compiled.tools)} tool(s)")
    for warning in compiled.warnings:
        print(f"warning: {warning}")
    return 0


def cmd_compile(args: argparse.Namespace) -> int:
    _, c = _load(args.spec, args.tools)
    if args.format == "nat":
        print(to_nat_yaml(c), end="")
    elif args.format == "fabric":
        print(json.dumps(to_fabric_config(c), indent=2))
    elif args.format == "opa":  # compiler D: one bundle directory's files, each under a "# file:" line
        for name, content in to_opa_bundle(c).items():
            print(f"# file: {name}\n{content}", end="")
    elif args.format == "guardrails":
        print(to_guardrails_yaml(c), end="")
    elif args.format == "policy":
        print(to_openshell_yaml(to_openshell_policy(c), "sandbox policy"), end="")
    else:
        profile = to_openshell_provider_profile(c)
        print(to_openshell_yaml(profile, "provider profile") if profile else "# this model needs no key", end="")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec, compiled = _load(args.spec, args.tools)
    if args.mock:  # tools return canned answers; nothing touches Gmail, Calendar, Sheets or the web
        compiled = compile_agent(
            spec, LocalGateway().apply(load_catalog(args.tools), mock=True, audit_log=default_audit_log())
        )
    # A live call that needs a person is asked here, in the terminal; with no terminal there is no one to ask.
    approve = terminal_approver() if sys.stdin.isatty() else None
    if approve is None and (live := unapproved_live_tools(compiled)):
        print(f"error: {approval_needed(live)} (--mock)", file=sys.stderr)
        return 1
    env = credential_env(spec, compiled)  # a missing key is reported before anything is started
    result = load_runner(args.runner).run(compiled, args.prompt, environ=env, approve=approve)
    if result.trajectory:
        print(
            f"tools used: {', '.join(result.trajectory.tools_used) or 'none'}; tokens: {result.total_tokens}",
            file=sys.stderr,
        )
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if not result.ok:
        print(f"failed: {result.error}", file=sys.stderr)
        return 1
    print(result.text)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    """The eval gate (PLAN 4.4.3). Exit 0: pass, 3: pass with limited mode, 1: block or a setup error."""
    from agentbuilder.evals import load_suite, run_suite

    spec = AgentSpec.load(args.spec)
    name = args.suite or spec.evals.suite
    if not name:
        print("error: name a suite with --suite or evals.suite in the spec", file=sys.stderr)
        return 1
    try:
        suite = load_suite(name)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    # The spec's publish bar wins over the suite's default.
    suite = suite.model_copy(
        update={"thresholds": suite.thresholds.model_copy(update={"success": spec.evals.publish_threshold})}
    )
    catalog = load_catalog(args.tools)
    if not args.live:  # an eval never touches Gmail, Calendar, Sheets or the web unless asked
        catalog = LocalGateway().apply(catalog, mock=True, audit_log=default_audit_log())
    compiled = compile_agent(spec, catalog)
    if live := unapproved_live_tools(compiled):  # an eval has nobody to ask, call after call
        print(f"error: {approval_needed(live)} (drop --live)", file=sys.stderr)
        return 1
    env = credential_env(spec, compiled)
    print(
        f"eval {suite.name}: {len(suite.cases)} cases on {compiled.model.model}; each is one real run", file=sys.stderr
    )

    def show(r: CaseResult) -> None:
        print(f"{'PASS' if r.passed else 'FAIL'} {r.id:<14} {r.seconds:6.1f}s  {r.why}", file=sys.stderr)

    report = run_suite(compiled, suite, runner=load_runner(args.runner), environ=env, on_case=show)
    for key, rate in report.metrics.items():
        print(f"{key:<15} {rate}")
    tokens = f"{report.tokens_per_task:.0f}" if report.tokens_per_task is not None else "unknown"
    print(f"latency p95     {report.latency_p95_s:.1f}s; tokens per task {tokens}")
    print(f"gate: {report.gate.outcome.upper()}: {report.gate.reason}")
    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return {"pass": 0, "pass_limited": 3}.get(report.gate.outcome, 1)


def cmd_probe_model(args: argparse.Namespace) -> int:
    spec = AgentSpec.load(args.spec)
    print(f"checking {spec.model.provider}/{spec.model.model}: this sends one real request", file=sys.stderr)
    result = probe_tool_calling(resolve_model(spec.model))
    print(result.message)
    if result.agent_mode:
        print(f"set model.agent_mode to {result.agent_mode}")
    return 0 if result.ok else 1


def cmd_tools(args: argparse.Namespace) -> int:
    catalog = load_catalog(args.tools)
    tiers = {0: "read-only", 1: "writes", 2: "contacts people", 3: "destructive or financial"}
    for t in catalog.resolve(catalog.tool_ids):
        m = t.manifest
        hosts = ", ".join(h for h in m.egress_hosts if h != "oauth2.googleapis.com") or "none"
        print(f"{t.id:24} tier {m.risk_tier} ({tiers[m.risk_tier]}); network: {hosts}")
        print(f"{'':24} {m.description_plain[:110]}")
    return 0


def _show_and_open(url: str) -> bool:
    print(f"If it does not open, visit:\n{url}\n")
    return webbrowser.open(url)


def cmd_auth(args: argparse.Namespace) -> int:
    from agentbuilder.library import google

    try:
        if args.action == "google":
            if not args.client_secret:
                print(GOOGLE_HELP, file=sys.stderr)
                raise SystemExit("error: pass --client-secret FILE (see the steps above)")
            print("Opening your browser to sign in to Google... (press Ctrl+C to cancel)", flush=True)
            path = google.sign_in(
                args.client_secret,
                open_browser=lambda url: (print(f"If it does not open, visit:\n{url}\n"), webbrowser.open(url)),
            )
            print(f"Signed in. Saved to {path} (private to you).")
        elif args.action == "status":
            info = google.status()
            print("signed in" if info["signed_in"] else "not signed in", f"({info['path']})")
            if info["signed_in"]:
                print(f"scopes: {', '.join(info['scopes'])}; saved {info['saved_days_ago']} day(s) ago")
                if info["saved_days_ago"] >= 6:
                    print("note: in Google's Testing mode the sign-in expires after 7 days; sign in again soon")
            return 0 if info["signed_in"] else 1
        else:
            print("signed out and revoked" if google.sign_out() else "nothing to remove")
    except google.ToolError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"{'ok  ' if passed else 'FAIL'} {label}{': ' + detail if detail else ''}")

    py = sys.version_info
    check("Python 3.11 to 3.13", (3, 11) <= py[:2] <= (3, 13), platform.python_version())
    check("agentbuilder", True, __version__)
    runners = sorted(ep.name for ep in entry_points(group=RUNNER_GROUP))
    check("a runner is installed", bool(runners), ", ".join(runners) or "pip install agentbuilder-nat")
    mcp = find_spec("mcp") is not None
    check("mcp package (runs the tool servers)", mcp, "" if mcp else "pip install 'agentbuilder[mcp]'")
    node = node_version()
    check(
        f"Node {MIN_NODE[0]}.{MIN_NODE[1]} or newer (for `ab ui`)",
        bool(node and node >= MIN_NODE),
        ".".join(map(str, node)) if node else "not found",
    )
    web = find_web_dir()
    check("web app found", web is not None, str(web) if web else "run from the repository checkout")
    if web:
        check(
            "web app dependencies installed",
            (web / "node_modules").is_dir(),
            "" if (web / "node_modules").is_dir() else f"run: cd {web} && npm install",
        )
    return 0 if ok else 1


def _stop_on_sigterm(signum: int, frame: object) -> None:
    raise KeyboardInterrupt


def cmd_ui(args: argparse.Namespace) -> int:
    web = Path(args.web_dir) if args.web_dir else find_web_dir()
    if web is None:
        raise SystemExit("cannot find apps/web; run `ab ui` inside the repository checkout or pass --web-dir")
    node = node_version()
    if not node or node < MIN_NODE:
        raise SystemExit(f"the web app needs Node {MIN_NODE[0]}.{MIN_NODE[1]} or newer (found: {node or 'none'})")
    if not (web / "node_modules").is_dir():
        raise SystemExit(f"install the web app's dependencies first: cd {web} && npm install")
    signal.signal(signal.SIGTERM, _stop_on_sigterm)  # `kill` must shut the web app down too, not orphan it
    session = UiSession(load_catalog(args.tools), web_dir=web, web_port=args.port, open_browser=not args.no_browser)
    try:
        session.start()
        print(f"Agent Builder is running at {session.web_url}  (press Ctrl+C to stop)", flush=True)
        session.wait()
    finally:
        session.stop()
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ab", description="Agent Builder")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)

    def with_spec(name: str, help_text: str) -> argparse.ArgumentParser:
        s = sub.add_parser(name, help=help_text)
        s.add_argument("spec", help="path to an *.agent.yaml file")
        s.add_argument("--tools", help="module:attribute that provides the ToolCatalog (default: the demo tools)")
        return s

    with_spec("validate", "check a spec and report how it will run").set_defaults(fn=cmd_validate)
    c = with_spec("compile", "print a generated config")
    c.add_argument("--format", choices=FORMATS, default="nat")
    c.set_defaults(fn=cmd_compile)
    r = with_spec("run", "run an agent once")
    r.add_argument("prompt")
    r.add_argument("--runner", default="local")
    r.add_argument("--mock", action="store_true", help="tools return canned answers and touch nothing live")
    r.set_defaults(fn=cmd_run)
    e = with_spec("eval", "run the spec's eval suite and apply the gate (mock tools unless --live)")
    e.add_argument("--suite", help="a built-in suite name or a .yaml/.json file (default: evals.suite in the spec)")
    e.add_argument("--runner", default="local")
    e.add_argument("--live", action="store_true", help="real tools instead of mocks")
    e.add_argument("--json", help="also write the full report to this file")
    e.set_defaults(fn=cmd_eval)
    pm = sub.add_parser("probe-model", help="one real request: does the model work and can it use tools?")
    pm.add_argument("spec", help="path to an *.agent.yaml file")
    pm.set_defaults(fn=cmd_probe_model)  # no --tools: the probe sends its own test tool, not the agent's
    sub.add_parser("doctor", help="check this machine").set_defaults(fn=cmd_doctor)
    t = sub.add_parser("tools", help="list the available tools with their risk tier and network access")
    t.add_argument("--tools", help="module:attribute that provides the ToolCatalog (default: demo + personal tools)")
    t.set_defaults(fn=cmd_tools)
    a = sub.add_parser("auth", help="sign in to Google for the Gmail, Calendar and Sheets tools")
    a.add_argument("action", choices=["google", "status", "revoke"])
    a.add_argument("--client-secret", help="the OAuth client JSON downloaded from Google Cloud (Desktop app)")
    a.set_defaults(fn=cmd_auth)
    u = sub.add_parser("ui", help="open the local web app")
    u.add_argument("--port", type=int, default=3000)
    u.add_argument("--web-dir")
    u.add_argument("--tools", help="module:attribute that provides the ToolCatalog (default: the demo tools)")
    u.add_argument("--no-browser", action="store_true")
    u.set_defaults(fn=cmd_ui)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.fn(args))
    except (SpecError, CompileError, CredentialError, RunnerNotInstalled, FileNotFoundError) as exc:
        problems = getattr(exc, "problems", None) or [str(exc)]
        print("error:", *problems, sep="\n  ", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
