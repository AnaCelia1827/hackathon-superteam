# Public Python SDK

The public `LoopRail` API is currently packaged with the Python runtime in `apps/runtime` as the `looprail-runtime` distribution. Install it with `python -m pip install -e apps/runtime` from the repository root, then import `LoopRail` from `looprail`.

The public facade lives in `apps/runtime/looprail/sdk.py`; tool execution, policy, and adapters stay in the same distribution so the local hackathon installation has one Python package. See `apps/runtime/README.md` for a runnable example.
