"""
Integration helpers for self-healing and validation.

Provides wrapper functions for Snowflake Cortex-based self-healing
and code validation, adapted for the MigrationContext dataclass.
"""

from __future__ import annotations

import os
import re
import json
import logging
import tempfile
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

from graph.state import MigrationContext

logger = logging.getLogger(__name__)

try:
    from langchain_community.chat_models import ChatSnowflakeCortex
except Exception:
    ChatSnowflakeCortex = None


# ============================================================================
# Text extraction helpers
# ============================================================================

def _extract_model_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                parts.append(text if isinstance(text, str) else str(item))
            else:
                text = getattr(item, "text", None)
                parts.append(text if isinstance(text, str) else str(item))
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _strip_markdown_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return stripped


def _count_lines(text: str) -> int:
    return len(text.splitlines()) if text else 0


def _count_lines_from_files(paths: List[str]) -> Optional[int]:
    total = 0
    found = False
    for path in paths:
        try:
            if not path or not os.path.isfile(path):
                continue
            with open(path, "r", encoding="utf-8-sig") as handle:
                total += _count_lines(handle.read())
                found = True
        except Exception:
            continue
    return total if found else None


# ============================================================================
# Result Data Classes
# ============================================================================

@dataclass
class SelfHealResult:
    """Result of a self-healing operation."""
    success: bool
    fixed_code: str
    fixes_applied: List[str]
    issues_fixed: int
    error_message: Optional[str] = None
    iteration: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationResult:
    """Result of a validation operation."""
    passed: bool
    issues: List[Dict[str, Any]]
    results: Dict[str, Any]
    error_message: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# Snowflake session helper
# ============================================================================

def get_snowflake_session(state: MigrationContext):
    """Create a Snowflake session from MigrationContext."""
    try:
        from core.snowflake_auth import (
            SnowflakeAuthConfig,
            resolve_password_from_sources,
            create_snowpark_session,
        )

        sf_account = (
            state.sf_account or os.getenv("SF_ACCOUNT", "")
        ).strip()
        sf_user = (
            state.sf_user or os.getenv("SF_USER", "") or os.getenv("SNOWFLAKE_USER", "")
        ).strip()
        sf_role = (
            state.sf_role or os.getenv("SF_ROLE", "")
        ).strip()
        sf_warehouse = (
            state.sf_warehouse or os.getenv("SF_WAREHOUSE", "")
        ).strip()
        sf_database = (
            state.sf_database or os.getenv("SF_DATABASE", "")
        ).strip()
        sf_schema = (
            state.sf_schema or os.getenv("SF_SCHEMA", "")
        ).strip()
        sf_authenticator = (
            state.sf_authenticator or os.getenv("SF_AUTHENTICATOR", "externalbrowser")
        ).strip() or "externalbrowser"

        config = SnowflakeAuthConfig(
            account=sf_account,
            user=sf_user,
            role=sf_role,
            warehouse=sf_warehouse,
            database=sf_database,
            schema=sf_schema,
            authenticator=sf_authenticator,
        )

        password = resolve_password_from_sources(
            authenticator=config.authenticator,
            explicit_password=None,
        )

        session = create_snowpark_session(config, password=password)
        logger.info("Snowflake session created successfully")
        return session

    except Exception as e:
        logger.error("Failed to create Snowflake session: %s", e)
        return None


# ============================================================================
# EWI helper
# ============================================================================

def remove_enclosed_strings(text: str) -> str:
    """Remove enclosed strings marked with !!!RESOLVE EWI!!! markers."""
    pattern = r'!!!RESOLVE EWI!!!.*?\*\*\*/!!!'
    return re.sub(pattern, '', text, flags=re.DOTALL)


# ============================================================================
# Self-Healing
# ============================================================================

def apply_self_healing(
    code: str,
    issues: List[Dict[str, Any]],
    state: MigrationContext,
    iteration: int = 1,
    statement_type: str = "mixed",
    logger_callback: Optional[Callable[[str], None]] = None,
) -> SelfHealResult:
    """Apply self-healing to code using Snowflake Cortex through LangChain."""
    if logger_callback is None:
        logger_callback = logger.info

    logger_callback(f"Starting self-healing iteration {iteration}")

    if ChatSnowflakeCortex is None:
        error_msg = "Snowflake Cortex dependency missing. Install langchain-community."
        logger.error(error_msg)
        return SelfHealResult(
            success=False, fixed_code=code, fixes_applied=[], issues_fixed=0,
            error_message=error_msg, iteration=iteration,
        )

    session = get_snowflake_session(state)
    if session is None:
        error_msg = "Snowflake session creation failed for self-heal."
        logger.error(error_msg)
        return SelfHealResult(
            success=False, fixed_code=code, fixes_applied=[], issues_fixed=0,
            error_message=error_msg, iteration=iteration,
        )

    model_name = (
        os.getenv("SNOWFLAKE_CORTEX_MODEL") or os.getenv("CORTEX_MODEL") or "claude-4-sonnet"
    ).strip() or "claude-4-sonnet"
    cortex_function = (os.getenv("SNOWFLAKE_CORTEX_FUNCTION") or "complete").strip() or "complete"

    cleaned_code = remove_enclosed_strings(code)
    prompt_code = cleaned_code.replace("$$", "$ $")

    issue_text = "\n".join(
        f"- [{issue.get('severity', 'error')}] {issue.get('message', issue)}"
        for issue in issues
    ) or "- No explicit issues provided"

    fix_strategy = {
        "ddl": "Prioritize object-creation order, dependencies, and Snowflake DDL compatibility.",
        "dml": "Prioritize column mapping, joins, update semantics, and data type compatibility.",
        "procedure": "Prioritize procedure syntax, variable handling, and CALL semantics.",
        "function": "Prioritize return type compatibility and SQL function semantics.",
        "mixed": "Prioritize broad Snowflake compatibility while preserving intent.",
    }.get(statement_type or "mixed", "Prioritize broad Snowflake compatibility.")

    report_context = state.report_context if isinstance(state.report_context, dict) else {}
    actionable_issues = report_context.get("actionable_issues", [])
    ignored_codes = report_context.get("ignored_codes", [])
    failed_statements = report_context.get("failed_statements", [])
    execution_errors = report_context.get("latest_execution_errors", [])
    report_scan_summary = report_context.get("report_scan_summary", {})

    prompt = (
        "You are a Snowflake SQL migration repair assistant.\n"
        "Use only the provided context and do not hallucinate missing requirements.\n"
        "Do not invent missing objects unless explicitly referenced in runtime errors or actionable report issues.\n"
        "Return only corrected SQL code with no commentary, no markdown, and no code fences.\n"
        f"Statement type: {statement_type or 'mixed'}\n"
        f"Repair strategy: {fix_strategy}\n"
        f"Iteration: {iteration}\n\n"
        f"Validation/Runtime Issues:\n{issue_text}\n\n"
        f"Report Scan Summary: {json.dumps(report_scan_summary, ensure_ascii=False)}\n"
        f"Ignored Report Codes (non-actionable unless runtime errors): {json.dumps(ignored_codes, ensure_ascii=False)}\n"
        f"Actionable Report Issues: {json.dumps(actionable_issues, ensure_ascii=False)}\n"
        f"Latest Execution Errors: {json.dumps(execution_errors, ensure_ascii=False)}\n"
        f"Failed Statements: {json.dumps(failed_statements, ensure_ascii=False)}\n\n"
        f"Code to Fix:\n{prompt_code}"
    )

    try:
        chat_model = ChatSnowflakeCortex(
            model=model_name,
            cortex_function=cortex_function,
            session=session,
            temperature=0,
        )
        response = chat_model.invoke(prompt)
        fixed_code = _strip_markdown_fences(_extract_model_text(getattr(response, "content", response)))
    except Exception as e:
        raw_error = str(e)
        error_msg = raw_error
        marker = 'SnowparkSQLException("'
        if marker in raw_error:
            start = raw_error.find(marker) + len(marker)
            end = raw_error.find('",', start)
            if end != -1:
                error_msg = raw_error[start:end]
        error_msg = (
            error_msg.replace("\\n", "\n")
            .replace('\\"', '"')
            .replace("\\'", "'")
        )
        if "select snowflake.cortex.complete" in error_msg:
            error_msg = error_msg.split("select snowflake.cortex.complete", 1)[0].strip()
        error_msg = f"Snowflake Cortex self-heal failed for model '{model_name}': {error_msg}"
        logger.error(error_msg)
        return SelfHealResult(
            success=False, fixed_code=code, fixes_applied=[], issues_fixed=0,
            error_message=error_msg, iteration=iteration,
        )
    finally:
        try:
            session.close()
        except Exception:
            pass

    if not fixed_code:
        fixed_code = cleaned_code

    logger_callback(f"LLM response (iteration {iteration}, model {model_name}):\n{fixed_code}")

    return SelfHealResult(
        success=True,
        fixed_code=fixed_code,
        fixes_applied=[f"Applied LLM-guided repair via Snowflake Cortex ({model_name})"],
        issues_fixed=len(issues),
        iteration=iteration,
    )


def apply_simple_code_fixes(
    code: str,
    issues: List[Dict[str, Any]],
    logger_callback: Optional[Callable[[str], None]] = None,
) -> SelfHealResult:
    """Apply simple regex-based code fixes without Snowflake connection."""
    if logger_callback is None:
        logger_callback = logger.info

    logger_callback("Applying simple code fixes (no Snowflake connection)")

    fixed_code = code
    fixes_applied = []
    issues_fixed = 0

    try:
        fixed_code = remove_enclosed_strings(fixed_code)
        fixes_applied.append("Removed enclosed strings marked with !!!RESOLVE EWI!!!")

        teradata_to_snowflake = {
            r'\bTRIM\(BOTH\s+FROM\s+': 'TRIM(',
            r'\bTRIM\(LEADING\s+FROM\s+': 'LTRIM(',
            r'\bTRIM\(TRAILING\s+FROM\s+': 'RTRIM(',
            r'\bQUALIFY\s+': 'QUALIFY ',
        }

        for pattern, replacement in teradata_to_snowflake.items():
            if re.search(pattern, fixed_code):
                fixed_code = re.sub(pattern, replacement, fixed_code)
                fixes_applied.append(f"Replaced pattern: {pattern}")

        issues_fixed = len([i for i in issues if "syntax" in i.get("type", "").lower()])

        logger_callback(f"Simple fixes applied: {len(fixes_applied)}, issues potentially fixed: {issues_fixed}")

        return SelfHealResult(
            success=True, fixed_code=fixed_code, fixes_applied=fixes_applied,
            issues_fixed=issues_fixed,
        )

    except Exception as e:
        error_msg = f"Exception during simple code fixes: {e}"
        logger.error(error_msg)
        return SelfHealResult(
            success=False, fixed_code=code, fixes_applied=[], issues_fixed=0,
            error_message=error_msg,
        )


# ============================================================================
# Validation
# ============================================================================

def normalize_sql(sql: str, logger_callback: Optional[Callable[[str], None]] = None) -> str:
    """Normalize SQL by removing comments and converting to uppercase."""
    if logger_callback is None:
        logger_callback = logger.info
    sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)
    sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
    return sql.upper()


def extract_statements(sql: str, logger_callback: Optional[Callable[[str], None]] = None) -> Dict[str, int]:
    """Extract and count SQL statement types."""
    from collections import Counter
    keywords = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'CREATE', 'DROP', 'CALL', 'EXEC', 'TRUNCATE']
    counts = Counter()
    for kw in keywords:
        counts[kw] = len(re.findall(rf'\b{kw}\b', sql))
    return dict(counts)


def extract_tables(sql: str, logger_callback: Optional[Callable[[str], None]] = None) -> set:
    """Extract table references from SQL."""
    table_pattern = r'\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|DELETE\s+FROM)\s+([A-Z0-9_.]+)'
    return set(re.findall(table_pattern, sql))


def extract_columns(sql: str, logger_callback: Optional[Callable[[str], None]] = None) -> set:
    """Extract column references from SQL."""
    col_patterns = [
        r'SELECT\s+(.*?)\s+FROM',
        r'INSERT\s+INTO\s+[A-Z0-9_.]+\s*\((.*?)\)',
        r'UPDATE\s+[A-Z0-9_.]+\s+SET\s+(.*?)\s+(?:WHERE|;)',
        r'ON\s+(.*?)\s+(?:AND|OR|WHERE|;)',
        r'WHERE\s+(.*?)\s+(?:GROUP|ORDER|HAVING|UNION|;)',
    ]
    skip = {'AND', 'OR', 'NOT', 'NULL', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
            'IN', 'EXISTS', 'BETWEEN', 'LIKE', 'IS', 'DISTINCT', 'COUNT', 'SUM',
            'MIN', 'MAX', 'AVG'}
    columns = set()
    for pat in col_patterns:
        for match in re.findall(pat, sql, flags=re.DOTALL):
            for col in re.split(r',|\s|\(|\)|=|<|>!', match):
                col = col.strip()
                if col and col not in skip:
                    if '.' in col:
                        col = col.split('.')[-1]
                    col = re.sub(r'\(.*\)', '', col)
                    if col and re.match(r'^[A-Z0-9_]+$', col):
                        columns.add(col)
    return columns


def extract_procedure_calls(sql: str, logger_callback: Optional[Callable[[str], None]] = None) -> set:
    """Extract procedure/function calls from SQL."""
    proc_pattern = r'\b(?:CALL|EXEC(?:UTE)?)\s+([A-Z0-9_.]+)'
    return set(re.findall(proc_pattern, sql))


def analyze_code(code: str, logger_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """Analyze SQL code and extract metadata."""
    sql = normalize_sql(code, logger_callback)
    return {
        'statements': extract_statements(sql, logger_callback),
        'tables': extract_tables(sql, logger_callback),
        'columns': extract_columns(sql, logger_callback),
        'procedures': extract_procedure_calls(sql, logger_callback),
    }


def validate_code(
    code: str,
    original_code: Optional[str] = None,
    state: Optional[MigrationContext] = None,
    logger_callback: Optional[Callable[[str], None]] = None,
) -> ValidationResult:
    """Validate converted code using line-count regression."""
    if logger_callback is None:
        logger_callback = logger.info

    logger_callback("Starting line-count validation...")
    issues: List[Dict[str, Any]] = []
    results: Dict[str, Any] = {}

    try:
        input_line_count: Optional[int] = None
        output_line_count: Optional[int] = None

        if state:
            input_line_count = _count_lines_from_files(state.source_files)
            output_line_count = _count_lines_from_files(state.converted_files)

        if input_line_count is None:
            baseline = original_code if original_code is not None else (state.original_code if state else "")
            input_line_count = _count_lines(baseline)

        if output_line_count is None:
            output_line_count = _count_lines(code)

        passed = output_line_count >= input_line_count
        results["line_count_validation"] = {
            "passed": passed,
            "input_line_count": input_line_count,
            "output_line_count": output_line_count,
        }

        if not passed:
            issues.append({
                "type": "line_count_regression",
                "severity": "error",
                "message": (
                    f"Output line count ({output_line_count}) is less than "
                    f"input line count ({input_line_count})."
                ),
                "input_line_count": input_line_count,
                "output_line_count": output_line_count,
            })

        logger_callback(
            f"Line-count validation: input={input_line_count}, output={output_line_count}, passed={passed}"
        )
        return ValidationResult(passed=passed, issues=issues, results=results)

    except Exception as e:
        error_msg = f"Exception during validation: {e}"
        logger.error(error_msg)
        return ValidationResult(
            passed=False,
            issues=[{"type": "validation_error", "severity": "error", "message": error_msg}],
            results=results,
            error_message=error_msg,
        )


def validate_syntax(code: str, logger_callback: Optional[Callable[[str], None]] = None) -> List[Dict[str, Any]]:
    """Basic syntax validation on SQL code."""
    issues = []

    open_parens = code.count('(')
    close_parens = code.count(')')
    if open_parens != close_parens:
        issues.append({
            "type": "syntax_error", "severity": "error",
            "message": f"Unbalanced parentheses: {open_parens} opening, {close_parens} closing",
        })

    single_quotes = code.count("'")
    if single_quotes % 2 != 0:
        issues.append({"type": "syntax_error", "severity": "error", "message": "Unbalanced single quotes"})

    teradata_patterns = [
        (r'\bQUALIFY\s+', "QUALIFY clause may need review for Snowflake"),
        (r'\bWITH\s+DATA\b', "WITH DATA clause not supported in Snowflake"),
        (r'\bCREATE\s+MULTISET\s+TABLE\b', "MULTISET TABLE not supported in Snowflake"),
        (r'\bCREATE\s+VOLATILE\s+TABLE\b', "VOLATILE TABLE not supported in Snowflake"),
    ]
    for pattern, message in teradata_patterns:
        if re.search(pattern, code, re.IGNORECASE):
            issues.append({"type": "syntax_warning", "severity": "warning", "message": message})

    return issues


# ============================================================================
# Report formatters
# ============================================================================

def format_validation_report(validation_result: ValidationResult) -> str:
    """Format a validation result as a readable report."""
    lines = [
        "=" * 60, "VALIDATION REPORT", "=" * 60,
        f"Timestamp: {validation_result.timestamp}",
        f"Passed: {validation_result.passed}",
        f"Issues Found: {len(validation_result.issues)}", "",
    ]
    if validation_result.issues:
        lines.append("ISSUES:")
        lines.append("-" * 60)
        for i, issue in enumerate(validation_result.issues, 1):
            lines.append(f"{i}. [{issue.get('severity', 'info').upper()}] {issue.get('type', 'unknown')}")
            lines.append(f"   {issue.get('message', 'No message')}")
        lines.append("")

    if validation_result.results:
        lines.append("RESULTS:")
        lines.append("-" * 60)
        for key, value in validation_result.results.items():
            if isinstance(value, dict) and "passed" in value:
                status = "PASSED" if value["passed"] else "FAILED"
                lines.append(f"{key}: {status}")
            else:
                lines.append(f"{key}: {value}")

    lines.append("=" * 60)
    return "\n".join(lines)


def format_self_heal_report(self_heal_result: SelfHealResult) -> str:
    """Format a self-heal result as a readable report."""
    lines = [
        "=" * 60, "SELF-HEALING REPORT", "=" * 60,
        f"Timestamp: {self_heal_result.timestamp}",
        f"Iteration: {self_heal_result.iteration}",
        f"Success: {self_heal_result.success}",
        f"Issues Fixed: {self_heal_result.issues_fixed}", "",
    ]
    if self_heal_result.fixes_applied:
        lines.append("FIXES APPLIED:")
        lines.append("-" * 60)
        for fix in self_heal_result.fixes_applied:
            lines.append(f"  - {fix}")
        lines.append("")
    if self_heal_result.error_message:
        lines.append("ERROR:")
        lines.append("-" * 60)
        lines.append(f"  {self_heal_result.error_message}")
        lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
