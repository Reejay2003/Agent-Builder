# agentbuilder-nat

The runner that executes an Agent Builder agent on NVIDIA NeMo Agent Toolkit (NAT) through NeMo Fabric, recording an
ATIF trajectory with NeMo Relay. It also ships our Fabric adapter for NAT (`src/agentbuilder_nat/adapter/README.md`),
because Fabric has no official NAT adapter.

    pip install agentbuilder agentbuilder-nat

    from agentbuilder.runtime import load_runner, credential_env
    result = load_runner("local").run(compiled, "What is 17.5 plus 25?", environ=credential_env(spec, compiled))
    print(result.text, result.trajectory.tools_used, result.total_tokens)

A run needs the model key in the environment variable named by the spec (`credential_ref`), nothing else. Errors never
contain the key. Runs are serialised inside one process (the key travels in the process environment).
