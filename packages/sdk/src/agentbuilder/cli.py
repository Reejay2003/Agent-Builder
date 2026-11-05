"""The `ab` command: validate, compile, run, doctor and ui."""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import signal
import sys
from collections.abc import Sequence
from importlib.metadata import entry_points
from pathlib import Path

from agentbuilder import __version__
from agentbuilder.compile import (
    CompiledAgent,
    CompileError,
    compile_agent,
    to_fabric_config,
    to_nat_yaml,
    to_openshell_policy,
    to_openshell_provider_profile,
    to_openshell_yaml,
)
from agentbuilder.models.credentials import CredentialError
from agentbuilder.runtime import RUNNER_GROUP, RunnerNotInstalled, credential_env, load_runner
from agentbuilder.spec import AgentSpec, SpecError
from agentbuilder.tools import ToolCatalog
from agentbuilder.ui import MIN_NODE, UiSession, find_web_dir, node_version

FORMATS = ("nat", "fabric", "policy", "provider")


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
    elif args.format == "policy":
        print(to_openshell_yaml(to_openshell_policy(c), "sandbox policy"), end="")
    else:
        profile = to_openshell_provider_profile(c)
        print(to_openshell_yaml(profile, "provider profile") if profile else "# this model needs no key", end="")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec, compiled = _load(args.spec, args.tools)
    env = credential_env(spec, compiled)  # a missing key is reported before anything is started
    result = load_runner(args.runner).run(compiled, args.prompt, environ=env)
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
    r.set_defaults(fn=cmd_run)
    sub.add_parser("doctor", help="check this machine").set_defaults(fn=cmd_doctor)
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
