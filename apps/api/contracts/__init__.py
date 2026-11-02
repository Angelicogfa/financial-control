"""Request/response schemas shared by the HTTP API, the MCP server and the use cases.

Pure Pydantic models and their entity-to-schema serializers (Phase 48.R1). They import only
`core`, `domain` and `contracts`; never FastAPI, `controllers`, `infra` or `worker`.
"""
