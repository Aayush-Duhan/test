"""Tool definitions registry for the AI agent orchestrator.

Each tool wraps a CLI command that the agent can invoke. Tools are defined
with JSON-schema parameters so the LLM can generate valid invocations,
and an allowlist flag that controls whether auto-fix retries are permitted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolParameter:
    """Single parameter accepted by a tool."""

    name: str
    description: str
    type: str = "string"  # JSON-schema type
    required: bool = True
    default: str | None = None
    enum: list[str] | None = None


@dataclass(frozen=True)
class ToolDefinition:
    """Definition of an executable CLI tool."""

    name: str
    description: str
    command_template: str  # e.g. "snowconvert --assess --input {input_path}"
    parameters: list[ToolParameter] = field(default_factory=list)
    allowlisted: bool = True  # can the agent auto-retry on failure?
    timeout_seconds: int = 300
    working_directory: str | None = None  # if None, uses cwd

    def build_command(self, args: dict[str, Any]) -> str:
        """Render the command template with supplied arguments."""
        return self.command_template.format(**args)

    def to_llm_schema(self) -> dict[str, Any]:
        """Return a JSON-schema-like dict the LLM can use to decide invocations."""
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }

            if param.enum:
                prop["enum"] = param.enum

            if param.default is not None:
                prop["default"] = param.default

            properties[param.name] = prop

            if param.required:
                required.append(param.name)

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, ToolDefinition] = {
    "run_command": ToolDefinition(
        name="run_command",
        description=(
            "Execute an arbitrary shell command on the local system. "
            "Use this for general-purpose tasks like checking versions, "
            "listing files, or running scripts."
        ),
        command_template="{command}",
        parameters=[
            ToolParameter(
                name="command",
                description="The full shell command to execute",
                required=True,
            ),
        ],
        allowlisted=True,
        timeout_seconds=120,
    ),
    "scai_init_project": ToolDefinition(
        name="scai_init_project",
        description=(
            "Initialize a new SnowConvert AI migration project. "
            "Creates the project folder structure (.scai/, source/, converted/) "
            "and configures it for the specified source database language. "
            "Optionally copies source code files into the project during init. "
            "This must be run before any other scai commands (code add, code convert, etc.)."
        ),
        command_template="scai init {project_path} -l {source_language}{name_flag}{input_flag}{connection_flag}",
        parameters=[
            ToolParameter(
                name="project_path",
                description="Directory path where the project will be created",
                required=True,
            ),
            ToolParameter(
                name="source_language",
                description="Source database language to migrate from",
                required=True,
                enum=[
                    "SqlServer", "Redshift", "Oracle", "Teradata",
                    "BigQuery", "Databricks", "Greenplum", "Sybase",
                    "Postgresql", "Netezza", "Spark", "Vertica",
                    "Hive", "Db2",
                ],
            ),
            ToolParameter(
                name="name_flag",
                description=(
                    'Project name flag, e.g. " -n my-project" (include leading space). '
                    "Leave empty string to default to the folder name."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="input_flag",
                description=(
                    'Input code path flag, e.g. " -i /path/to/sql/files" (include leading space). '
                    "Leave empty string to skip."
                ),
                required=False,
                default="",
            ),
            ToolParameter(
                name="connection_flag",
                description=(
                    'Snowflake connection name flag, e.g. " -c my-conn" (include leading space). '
                    "Leave empty string to skip."
                ),
                required=False,
                default="",
            ),
        ],
        allowlisted=True,
        timeout_seconds=60,
    ),
}


def get_tool(name: str) -> ToolDefinition | None:
    """Look up a tool by name."""
    return TOOL_REGISTRY.get(name)


def get_all_tools() -> list[ToolDefinition]:
    """Return all registered tools."""
    return list(TOOL_REGISTRY.values())


def get_tools_for_llm() -> list[dict[str, Any]]:
    """Return all tool schemas formatted for LLM consumption."""
    return [tool.to_llm_schema() for tool in TOOL_REGISTRY.values()]
