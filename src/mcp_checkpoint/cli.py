import asyncio
import argparse
import json
import sys
import logging
import os
import shutil
import textwrap
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from rich.console import Console
from rich.text import Text


class SuppressStderr:

    def __enter__(self):
        self.original_stderr = sys.stderr
        sys.stderr = open(os.devnull, 'w')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stderr.close()
        sys.stderr = self.original_stderr


SEVERITY_EMOJI = {
    'CRITICAL': '🚫',
    'HIGH': '🔴', 
    'MEDIUM': '🟠',
    'LOW': '🟡',
}

RISK_EMOJI = {**SEVERITY_EMOJI, 'NONE': '✅'}


def get_level_emoji(level, mapping):
    level_upper = level.upper() if isinstance(level, str) else level
    return mapping.get(level_upper, '❓')


def print_separator(char='═', length=50):
    print(char * length)


def truncate_lines(text: str, max_lines: int = 2) -> str:
    if not text:
        return ""
    lines = str(text).splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[:max_lines]) + "…"


def wrap_text_with_indent(text: str, indent: str = "       ", max_lines: int = None) -> str:
    if not text:
        return ""
    
    try:
        terminal_width = shutil.get_terminal_size().columns
    except (OSError, AttributeError):
        terminal_width = 80
    
    indent_len = len(indent)
    available_width = terminal_width - indent_len
    
    if available_width < 20:
        available_width = 20
    
    wrapped_lines = textwrap.wrap(
        text, 
        width=available_width, 
        break_long_words=False, 
        break_on_hyphens=False
    )
    
    if max_lines and len(wrapped_lines) > max_lines:
        wrapped_lines = wrapped_lines[:max_lines]
        if len(wrapped_lines) == max_lines:
            last_line = wrapped_lines[-1]
            if len(last_line) + 3 <= available_width:
                wrapped_lines[-1] = last_line + "…"
            else:
                max_chars = available_width - 3
                wrapped_lines[-1] = last_line[:max_chars] + "…"
    
    return "\n".join([indent + line for line in wrapped_lines])


def print_banner():
    console = Console()

    banner = """
███    ███  ██████ ██████       ██████ ██   ██ ███████  ██████ ██   ██ ██████   ██████  ██ ███    ██ ████████ 
████  ████ ██      ██   ██     ██      ██   ██ ██      ██      ██  ██  ██   ██ ██    ██ ██ ████   ██    ██    
██ ████ ██ ██      ██████      ██      ███████ █████   ██      █████   ██████  ██    ██ ██ ██ ██  ██    ██    
██  ██  ██ ██      ██          ██      ██   ██ ██      ██      ██  ██  ██      ██    ██ ██ ██  ██ ██    ██    
██      ██  ██████ ██           ██████ ██   ██ ███████  ██████ ██   ██ ██       ██████  ██ ██   ████    ██ 
"""

    console.print(banner, style="turquoise2")

    banner_text = Text("                                                                            ｂｙ  Ａｉｒａ  Ｓｅｃｕｒｉｔｙ",
                       style="bold magenta")
    console.print(banner_text)
    console.print()


def print_boxed_section(title, content_func):
    print_separator('═', 60)
    print(f"{title}")
    print_separator('─', 60)
    content_func()
    print()


def _format_entity_display(entity) -> str:
    entity_type_map = {
        "tool": "Tool",
        "resource": "Resource",
        "prompt": "Prompt",
        "resource_template": "Resource Template",
        "server": "Server",
        "configuration": "Configuration"
    }
    entity_label = entity_type_map.get(entity.entity_type, entity.entity_type.title())
    
    changed_fields = entity.changed_fields or []
    changed_str = f" [changed: {', '.join(changed_fields)}]" if changed_fields else ""
    
    disabled = entity.additional_info.get("disabled", False) if entity.additional_info else False
    disabled_str = " [disabled]" if disabled else ""
    
    # Special handling for tool name ambiguity - show both conflicting tools
    if entity.entity_type == "tool" and entity.additional_info and "tools" in entity.additional_info:
        tools_list = entity.additional_info["tools"]
        if isinstance(tools_list, list) and len(tools_list) >= 2:
            tool1 = tools_list[0]
            tool2 = tools_list[1]
            tool1_name = tool1.get("name", "unknown") if isinstance(tool1, dict) else str(tool1)
            tool1_server = tool1.get("server", "unknown") if isinstance(tool1, dict) else "unknown"
            tool2_name = tool2.get("name", "unknown") if isinstance(tool2, dict) else str(tool2)
            tool2_server = tool2.get("server", "unknown") if isinstance(tool2, dict) else "unknown"
            score = entity.additional_info.get("score", "")
            score_str = f" (similarity: {score}%)" if score else ""
            return f"Conflict between '{tool1_name}' (server: {tool1_server}) and '{tool2_name}' (server: {tool2_server}) -{score_str}"
    
    if entity.entity_type == "configuration":
        if entity.config_file:
            return f"Server '{entity.entity_name}' (config: '{entity.config_file}'){disabled_str}{changed_str}"
        else:
            return f"Server '{entity.entity_name}'{disabled_str}{changed_str}"
    
    if entity.entity_type == "resource" and entity.affected_resource_uri:
        return f"{entity_label} '{entity.affected_resource_uri}' (server: '{entity.server_name}'){changed_str}"
    elif entity.entity_type == "resource_template" and entity.affected_resource_template_uri:
        return f"{entity_label} '{entity.affected_resource_template_uri}' (server: '{entity.server_name}'){changed_str}"
    else:
        return f"{entity_label} '{entity.entity_name}' (server: '{entity.server_name}'){changed_str}"


def _entity_to_dict(entity) -> dict:
    result = {
        "entity_type": entity.entity_type,
        "entity_name": entity.entity_name,
        "server_name": entity.server_name,
    }
    
    if entity.config_file:
        result["config_file"] = entity.config_file
    if entity.affected_tool:
        result["affected_tool"] = entity.affected_tool
    if entity.affected_resource:
        result["affected_resource"] = entity.affected_resource
    if entity.affected_resource_uri:
        result["affected_resource_uri"] = entity.affected_resource_uri
    if entity.affected_prompt:
        result["affected_prompt"] = entity.affected_prompt
    if entity.affected_resource_template:
        result["affected_resource_template"] = entity.affected_resource_template
    if entity.affected_resource_template_uri:
        result["affected_resource_template_uri"] = entity.affected_resource_template_uri
    if entity.changed_fields:
        result["changed_fields"] = entity.changed_fields
    if entity.additional_info:
        result["additional_info"] = entity.additional_info
    
    return result


def _grouped_issue_to_dict(grouped) -> dict:

    return {
        "finding_type": grouped.issue_type,
        "severity": grouped.severity.value,
        "description": grouped.description,
        "remediation": grouped.remediation,
        "total_entities": grouped.total_entities,
        "entities_affected": [_entity_to_dict(entity) for entity in grouped.entities_affected]
    }


def _redact_headers(headers: dict) -> dict:
    if not headers:
        return {}
    sensitive_headers = {
        'authorization', 'auth', 'authenticate',
        'api-key', 'api_key', 'apikey', 'apikey', 'apiKey', 'API_KEY', 'API-KEY',
        'token', 'access-token', 'access_token', 'accessToken', 'ACCESS_TOKEN',
        'x-api-key', 'x-api-key', 'X-API-Key', 'X-API-KEY',
        'bearer', 'oauth', 'oauth-token', 'oauth_token',
        'session', 'session-id', 'session_id', 'sessionId',
        'cookie', 'set-cookie',
        'x-auth-token', 'x-auth-token', 'X-Auth-Token',
        'x-access-token', 'x-access-token', 'X-Access-Token'
    }
    return {k: "***" if k.lower() in {h.lower() for h in sensitive_headers} else v for k, v in headers.items()}


def _redact_env(env: dict) -> dict:
    if not env:
        return {}
    sensitive_keywords = {
        'key', 'token', 'secret', 'password', 'passwd', 'pwd',
        'api_key', 'apikey', 'api-key', 'apiKey', 'API_KEY',
        'auth', 'authorization', 'authenticate',
        'credential', 'credentials', 'creds',
        'access', 'access_token', 'access-token', 'accessToken',
        'session', 'session_id', 'session-id', 'sessionId',
        'bearer', 'oauth', 'oauth_token', 'oauth-token',
        'private', 'private_key', 'private-key', 'privateKey',
        'cert', 'certificate', 'cert_key', 'cert-key',
        'ssh', 'ssh_key', 'ssh-key', 'sshKey',
        'aws', 'aws_key', 'aws_key_id', 'aws_secret',
        'gcp', 'gcp_key', 'gcp_credential',
        'azure', 'azure_key', 'azure_secret'
    }
    return {k: "***" if any(keyword in k.lower() for keyword in sensitive_keywords) else v for k, v in env.items()}


def _redact_args(args: List[str]) -> List[str]:
    if not args:
        return []
    
    sensitive_flags = {
        '--api-key', '--apikey', '--api_key', '--apiKey', '--API_KEY', '--API-KEY',
        '--token', '--auth-token', '--access-token', '--access_token', '--accessToken',
        '--bearer', '--oauth', '--oauth-token', '--oauth_token',
        '--password', '--passwd', '--pwd', '--pass',
        '--secret', '--secret-key', '--secretkey', '--secret_key', '--secretKey',
        '--credential', '--credentials', '--creds',
        '--auth', '--authorization', '--authenticate',
        '-k', '--key', '-t', '--token', '-p', '--password', '-s', '--secret',
        '--aws-key', '--aws-secret', '--gcp-key', '--azure-key'
    }
    
    redacted = []
    i = 0
    while i < len(args):
        arg = args[i]
        arg_lower = arg.lower()
        
        if '=' in arg:
            key, value = arg.split('=', 1)
            key_lower = key.lower()
            if any(flag in key_lower for flag in sensitive_flags) or \
               any(sensitive in key_lower for sensitive in ['key', 'token', 'secret', 'password', 'auth', 'credential', 'passwd', 'pwd', 'cred']):
                redacted.append(f"{key}=***")
            else:
                redacted.append(arg)
        elif arg_lower in sensitive_flags:
            redacted.append(arg)
            if i + 1 < len(args) and not args[i + 1].startswith('-'):
                redacted.append("***")
                i += 1
        else:
            redacted.append(arg)
        i += 1
    
    return redacted


def setup_logging(show_logs: bool = False):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "mcp_checkpoint.log"

    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    if show_logs:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    return str(log_file)


def format_scan_results_as_markdown(results, baseline_status: Optional[dict] = None) -> str:
    from .security_utils import ScanResult, AffectedEntity, get_generic_description, get_generic_recommendation
    md = []

    md.append("# MCP Checkpoint Scan Report")
    md.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("")

    md.append("## Summary")
    md.append(f"- **Servers found**: {len(results.servers)}")
    md.append(f"- **Tools found**: {len(results.tools)}")
    md.append(f"- **Resources found**: {len(results.resources)}")
    md.append(f"- **Prompts found**: {len(results.prompts)}")
    md.append(f"- **Resource Templates found**: {len(results.resource_templates)}")
    md.append(f"- **Config files**: {len(results.config_files)}")
    md.append(f"- **Errors**: {len(results.errors)}")
    if results.status:
        md.append(f"- **Status**:")
        for status_msg in results.status:
            md.append(f"  - {status_msg}")
    md.append("")

    if results.servers:
        md.append("## Discovered Servers")
        for server in results.servers:
            status = "DISABLED" if server.disabled else "ENABLED"
            md.append(f"### {server.name} ({server.type.value}) - {status}")
            if server.source_file:
                md.append(f"- **Source**: `{server.source_file}`")
            if server.endpoint:
                md.append(f"- **Endpoint**: `{server.endpoint}`")
            if server.command:
                md.append(f"- **Command**: `{server.command}`")
            if server.args:
                md.append(f"- **Args**: `{' '.join(_redact_args(server.args))}`")
            if server.headers:
                redacted_headers = _redact_headers(server.headers)
                headers_str = ', '.join([f"`{k}={v}`" for k, v in redacted_headers.items()])
                md.append(f"- **Headers**: {headers_str}")
            if server.env:
                redacted_env = _redact_env(server.env)
                env_str = ', '.join([f"`{k}={v}`" for k, v in redacted_env.items()])
                md.append(f"- **Environment Variables**: {env_str}")
            if server.additional_permissions:
                md.append(f"- **Permissions**: {', '.join(server.additional_permissions)}")
            md.append("")

    if results.tools:
        md.append("## Discovered Tools")
        for tool in results.tools:
            md.append(f"### {tool.name}")
            md.append(f"- **Server**: {tool.server_name}")
            md.append(f"- **Description**: {tool.description}")
            if tool.input_schema:
                md.append(f"- **Schema**:")
                md.append("```json")
                md.append(json.dumps(tool.input_schema, indent=2))
                md.append("```")
            md.append("")

    if results.resources:
        md.append("## Discovered Resources")
        for resource in results.resources:
            md.append(f"### {resource.name}")
            md.append(f"- **URI**: `{resource.uri}`")
            md.append(f"- **Server**: {resource.server_name}")
            md.append(f"- **Description**: {resource.description}")
            md.append(f"- **MIME Type**: {resource.mime_type}")
            md.append("")

    if results.prompts:
        md.append("## Discovered Prompts")
        for prompt in results.prompts:
            md.append(f"### {prompt.name}")
            md.append(f"- **Server**: {prompt.server_name}")
            md.append(f"- **Description**: {prompt.description}")
            if prompt.arguments:
                md.append(f"- **Arguments**:")
                md.append("```json")
                md.append(json.dumps(prompt.arguments, indent=2))
                md.append("```")
            md.append("")

    if results.resource_templates:
        md.append("## Discovered Resource Templates")
        for template in results.resource_templates:
            md.append(f"### {template.name}")
            md.append(f"- **URI Template**: `{template.uri_template}`")
            md.append(f"- **Server**: {template.server_name}")
            md.append(f"- **Description**: {template.description}")
            md.append(f"- **MIME Type**: {template.mime_type}")
            md.append("")

    if baseline_status:
        md.append("## Baseline Status")
        md.append(f"- **Baseline File**: `{baseline_status.get('baseline_file', 'N/A')}`")
        md.append(f"- **Baseline Loaded**: {baseline_status.get('baseline_loaded', False)}")
        if 'warning' in baseline_status:
            md.append(f"- **Warning**: {baseline_status['warning']}")
        md.append("")

    if hasattr(results, 'security_report') and results.security_report:
        security_report = results.security_report
        md.append("## Security Report")
        md.append(f"- **Risk Level**: {security_report.risk_level.value}")
        md.append(f"- **Total Findings**: {security_report.total_issues}")
        md.append("")

        md.append("### Findings by Severity")
        for severity, count in security_report.issues_by_severity.items():
            if count > 0:
                md.append(f"- **{severity.value}**: {count}")
        md.append("")

        if security_report.issues_by_type:
            md.append("### Findings by Type")
            for issue_type, count in security_report.issues_by_type.items():
                md.append(f"- **{issue_type}**: {count}")
            md.append("")

        if security_report.grouped_issues:
            md.append("### Security Findings")
            for grouped in security_report.grouped_issues:
                sev_str = grouped.severity.value.upper()
                md.append(f"#### {grouped.issue_type} ({sev_str})")
                md.append(f"**Description**: {grouped.description}")
                md.append("")
                md.append(f"**Entities Affected ({grouped.total_entities})**:")
                for entity in grouped.entities_affected:
                    entity_display = _format_entity_display(entity)
                    md.append(f"- {entity_display}")
                md.append("")
                md.append(f"**Remediation**: {grouped.remediation}")
                md.append("")
                md.append("---")
                md.append("")

    if results.errors:
        md.append("## Errors")
        for error in results.errors:
            md.append(f"- {error}")
        md.append("")

    if results.status:
        md.append("## Status")
        for status_msg in results.status:
            md.append(f"- {status_msg}")
        md.append("")

    return "\n".join(md)


def format_inspect_results_as_markdown(results, baseline_info: Optional[dict] = None) -> str:
    from .security_utils import ScanResult
    md = []

    md.append("# MCP Configuration Inspection Report")
    md.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    md.append("")

    md.append("## Summary")
    md.append(f"- **Servers found**: {len(results.servers)}")
    md.append(f"- **Tools found**: {len(results.tools)}")
    md.append(f"- **Resources found**: {len(results.resources)}")
    md.append(f"- **Prompts found**: {len(results.prompts)}")
    md.append(f"- **Resource Templates found**: {len(results.resource_templates)}")
    md.append(f"- **Config files**: {len(results.config_files)}")
    md.append(f"- **Errors**: {len(results.errors)}")
    if results.status:
        md.append(f"- **Status**:")
        for status_msg in results.status:
            md.append(f"  - {status_msg}")
    md.append("")

    if baseline_info:
        md.append("## Baseline")
        md.append(f"- **Baseline File**: `{baseline_info.get('baseline_file', 'N/A')}`")
        md.append(f"- **Baseline Generated**: {baseline_info.get('baseline_generated', False)}")
        if baseline_info.get('timestamp'):
            md.append(f"- **Generated At**: {baseline_info['timestamp']}")
        md.append("")

    if results.config_files:
        md.append("## Configuration Files")
        for config_file in results.config_files:
            md.append(f"- `{config_file}`")
        md.append("")

    if results.servers:
        md.append("## Discovered Servers")
        for server in results.servers:
            status = "DISABLED" if server.disabled else "ENABLED"
            md.append(f"### {server.name} ({server.type.value}) - {status}")
            if server.source_file:
                md.append(f"- **Source**: `{server.source_file}`")
            if server.endpoint:
                md.append(f"- **Endpoint**: `{server.endpoint}`")
            if server.command:
                md.append(f"- **Command**: `{server.command}`")
            if server.args:
                md.append(f"- **Args**: `{' '.join(_redact_args(server.args))}`")
            if server.headers:
                redacted_headers = _redact_headers(server.headers)
                headers_str = ', '.join([f"`{k}={v}`" for k, v in redacted_headers.items()])
                md.append(f"- **Headers**: {headers_str}")
            if server.env:
                redacted_env = _redact_env(server.env)
                env_str = ', '.join([f"`{k}={v}`" for k, v in redacted_env.items()])
                md.append(f"- **Environment Variables**: {env_str}")
            if server.additional_permissions:
                md.append(f"- **Permissions**: {', '.join(server.additional_permissions)}")
            md.append("")

    if results.tools:
        md.append("## Discovered Tools")
        for tool in results.tools:
            md.append(f"### {tool.name}")
            md.append(f"- **Server**: {tool.server_name}")
            md.append(f"- **Description**: {tool.description}")
            if tool.input_schema:
                md.append(f"- **Schema**:")
                md.append("```json")
                md.append(json.dumps(tool.input_schema, indent=2))
                md.append("```")
            md.append("")
    if results.resources:
        md.append("## Discovered Resources")
        for resource in results.resources:
            md.append(f"### {resource.name}")
            md.append(f"- **URI**: `{resource.uri}`")
            md.append(f"- **Server**: {resource.server_name}")
            md.append(f"- **Description**: {resource.description}")
            md.append(f"- **MIME Type**: {resource.mime_type}")
            md.append("")

    if results.prompts:
        md.append("## Discovered Prompts")
        for prompt in results.prompts:
            md.append(f"### {prompt.name}")
            md.append(f"- **Server**: {prompt.server_name}")
            md.append(f"- **Description**: {prompt.description}")
            if prompt.arguments:
                md.append(f"- **Arguments**:")
                md.append("```json")
                md.append(json.dumps(prompt.arguments, indent=2))
                md.append("```")
            md.append("")

    if results.resource_templates:
        md.append("## Discovered Resource Templates")
        for template in results.resource_templates:
            md.append(f"### {template.name}")
            md.append(f"- **URI Template**: `{template.uri_template}`")
            md.append(f"- **Server**: {template.server_name}")
            md.append(f"- **Description**: {template.description}")
            md.append(f"- **MIME Type**: {template.mime_type}")
            md.append("")

    if results.errors:
        md.append("## Errors")
        for error in results.errors:
            md.append(f"- {error}")
        md.append("")

    if results.status:
        md.append("## Status")
        for status_msg in results.status:
            md.append(f"- {status_msg}")
        md.append("")

    return "\n".join(md)


def determine_output_file(args, command_type: str):
    if args.output:
        return args.output
    else:
        return f"{command_type}_results.{args.report_type}"


def build_baseline_status(baseline_path: Optional[str], baseline_loaded: bool, baseline_warning: Optional[str]) -> dict:
    status = {
        "baseline_file": baseline_path if baseline_path else None,
        "baseline_loaded": baseline_loaded
    }
    if baseline_warning:
        status["warning"] = baseline_warning
    return status


def validate_baseline_path(file_path: str, mode: str) -> Optional[Path]:
    path = Path(file_path)
    
    if path.exists() and path.is_dir():
        raise ValueError(f"Baseline path is a directory: {file_path}. Must be a file path.")
    
    if mode == 'inspect':
        if not path.parent.exists():
            raise ValueError(
                f"Parent directory does not exist: {path.parent}\n"
                f"Please create the directory first or use an existing path."
            )
        return path
    
    if mode == 'scan':
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError(f"Baseline path exists but is not a file: {file_path}")
        return path
    
    return path


def save_report_to_file(content, filepath, report_type, suppress_print=False):
    output_path = Path(filepath)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.exists() and output_path.is_dir():
        raise ValueError(f"Output path is a directory: {filepath}. Must be a file path.")

    with open(output_path, 'w') as f:
        f.write(content)

    if not suppress_print:
        print(f"Report saved to {output_path}")


async def scan_command(args):
    print('\n🏃 Running MCP Checkpoint in scan mode...\n')

    from .scanner import MCPConfigScanner
    from .security_utils import (
        ScanResult,
        AffectedEntity,
        calculate_risk_level,
        sort_issues_by_severity,
        group_issues_by_type_and_severity,
    )
    from .baseline import load_baseline, generate_baseline, save_baseline
    
    scanner = MCPConfigScanner()
    
    baseline = None
    baseline_path_str = None
    baseline_path = None
    baseline_warning = None
    
    if args.baseline:
        baseline_path_str = args.baseline
    else:
        default_baseline = Path("baseline.json")
        if default_baseline.exists():
            baseline_path_str = str(default_baseline)

    custom_paths = []
    if args.config:
        custom_paths.extend(args.config)
    
    if baseline_path_str:
        try:
            validated_path = validate_baseline_path(baseline_path_str, 'scan')
            if validated_path:
                baseline_path = validated_path
                baseline = load_baseline(validated_path)
                if baseline:
                    print(f"  🧭 Using baseline: {baseline_path_str} (✅ loaded)\n")
                else:
                    baseline_warning = f"Baseline checks skipped. Baseline file not found or invalid: {baseline_path_str}."
                    print(f"  ⚠️  Skipping baseline checks as no valid baseline file was provided: {baseline_path_str}.")
                    print(f"     💡 Run `mcp-checkpoint inspect --baseline {baseline_path_str}` first to create one.")
            else:
                baseline_warning = f"Baseline checks skipped. Baseline file not found or invalid: {baseline_path_str}."
                print(f"  ⚠️  Skipping baseline checks as no valid baseline file was provided: {baseline_path_str}.")
                print(f"     💡 Run `mcp-checkpoint inspect --baseline {baseline_path_str}` first to create one.\n")
        except ValueError as e:
            baseline_warning = f"Baseline checks skipped. Invalid baseline file: {baseline_path_str}."
            print(f"  ⚠️  Skipping baseline checks as no valid baseline file was provided: {baseline_path_str}.")
            print(f"     💡 Run `mcp-checkpoint inspect --baseline {baseline_path_str}` first to create one.\n")
    else:
        baseline_warning = "Baseline checks skipped. No baseline file found."
        print(f"  ⚠️  Skipping baseline checks as no baseline file was found.")
        print(f"     💡 Run `mcp-checkpoint inspect` first to create one.\n")
    missing_paths = []
    if not custom_paths:
        print("  📄 No config provided — searching known locations…")
    else:
        for p in custom_paths:
            exists = Path(p).exists()
            status_text = " (✅ found)" if exists else " (❌ not found)"
            print(f"  📄 Using config: {p}{status_text}")
            if not exists:
                missing_paths.append(p)
        if missing_paths:
            custom_paths = [p for p in custom_paths if Path(p).exists()]
            if not custom_paths:
                print(
                    "\n  No valid config files found. Please provide at least one valid config file path with --config.")
                sys.exit(1)

    try:
        with SuppressStderr():
            config_files = await scanner.discover_config_files(custom_paths)
            print("     🧩 Parsing configuration…")
            is_user_provided = bool(custom_paths)

            servers = []
            parse_errors = []
            for cfg in config_files:
                try:
                    parsed = await scanner.parse_single_config(cfg, is_user_provided)
                    servers.extend(parsed)
                except Exception as e:
                    parse_errors.append(f"Failed to parse config: {cfg} ({e})")

            if is_user_provided and len(servers) == 0:
                print("\n  ❌ Failed to parse provided config or no MCP servers found in it.")
                for p in config_files:
                    print(f"     ↳ {p}")
                if parse_errors:
                    for err in parse_errors:
                        print(f"     ❌ {err}")
                print("\n  Ensure the file is valid JSON/YAML and follows expected schema (servers/mcpServers).")
                sys.exit(1)

            server_names = [s.name for s in servers]
            if server_names:
                shown = ", ".join(server_names[:5])
                more = f" (+{len(server_names) - 5} more)" if len(server_names) > 5 else ""
                print(f"\n  🔲 Servers found ({len(server_names)}): {shown}{more}")

            failed = []
            seen_oauth = set()
            connected = set()

            def progress_cb(event, data):
                if event == 'failed':
                    name = data.get('server')
                    err = data.get('error', 'error')
                    failed.append((name, err))
                    clean_err = err.replace(f"Failed to connect to server: {name}", "").strip()
                    if not clean_err or clean_err == err:
                        clean_err = err
                    print(f"     ❌ Connection failed: {name} ({clean_err})")
                elif event == 'oauth_wait':
                    name = data.get('server')
                    if name and name not in seen_oauth:
                        seen_oauth.add(name)
                        print(f"        ⏳ Waiting for OAuth: {name}")
                elif event == 'oauth_approved':
                    name = data.get('server')
                    if name and getattr(args, 'verbose', False):
                        print(f"        🆗 Access approved: {name}")
                elif event == 'connected':
                    name = data.get('server')
                    if name:
                        connected.add(name)
                        tools_n = data.get('tools', 0)
                        res_n = data.get('resources', 0)
                        prompts_n = data.get('prompts', 0)
                        templates_n = data.get('resource_templates', 0)
                        print(f"        🔗 Connected: {name} (tools {tools_n}, resources {res_n}, prompts {prompts_n}, resource templates {templates_n})")

            from .run_checks import SecurityCheckRunner, SecurityReport
            security_scanner = SecurityCheckRunner(baseline=baseline)
            config_only_result = ScanResult(servers=servers, tools=[], resources=[], prompts=[], resource_templates=[], config_files=config_files)
            config_task = asyncio.create_task(security_scanner.run_configuration_checks(config_only_result))
            print("     🔌 Connecting to servers…")
            discovery_task = asyncio.create_task(scanner.discover_all(servers, progress=progress_cb))

            config_issues, (tools, resources, prompts, templates) = await asyncio.gather(config_task, discovery_task)

            errors = []
            status = []

            if missing_paths:
                for p in missing_paths:
                    errors.append(f"Config not found: {p}")
                if is_user_provided:
                    total_provided = len(args.config) if args.config else 0
                    missing_count = len(missing_paths)
                    status.append(
                        f"Some provided configs ({missing_count}/{total_provided}) not found. Results exclude those files.")

            if parse_errors:
                errors.extend(parse_errors)
                if is_user_provided:
                    total_cfgs = len(config_files)
                    failed_cfgs = len(parse_errors)
                    status.append(
                        f"Some provided configs ({failed_cfgs}/{total_cfgs}) failed to parse. Results exclude those files.")

            for server_name, error_msg in failed:
                clean_error = error_msg.replace(f"Failed to connect to server: {server_name}", "").strip()
                if not clean_error or clean_error == error_msg:
                    clean_error = error_msg
                errors.append(f"Connection failed to server '{server_name}': {clean_error}")

            enabled_servers = [s for s in servers if not s.disabled]
            total_servers = len(enabled_servers)
            connected_count = len(connected)
            failed_count = len(failed)

            if connected_count == 0 and failed_count > 0:
                status.append("No servers connected. Only configuration checks were run.")
            elif failed_count > 0:
                status.append(
                    f"Some servers ({failed_count}/{total_servers}) failed to connect. Security scan is incomplete for failed servers.")
            elif total_servers == 0:
                status.append("No MCP servers found in configuration. Only configuration checks were run.")
            else:
                if baseline:
                    status.append("All servers connected. Full security scan completed.")
                else:
                    status.append("All servers connected. Scan completed without baseline checks.")

            if len(connected) == 0:
                print("\n  ⚠️  No servers connected. Running configuration checks only.")
                print("     ‼️  Check your server configurations and network connectivity.")

            print("\n  ✅ Configuration scan complete\n")

            if len(connected) == 0:
                results = ScanResult(servers=servers, tools=[], resources=[], prompts=[], resource_templates=[], config_files=config_files, errors=errors,
                                     status=status)
                security_report = SecurityReport()
                security_report.all_issues = sort_issues_by_severity(config_issues)
                security_report.total_issues = len(config_issues)
                for issue in config_issues:
                    security_report.issues_by_severity[issue.severity] += 1
                    issue_type = issue.issue_type.split(':')[0]
                    if issue_type not in security_report.issues_by_type:
                        security_report.issues_by_type[issue_type] = 0
                    security_report.issues_by_type[issue_type] += 1
                security_report.grouped_issues = group_issues_by_type_and_severity(config_issues)
                security_report.risk_level = calculate_risk_level(config_issues)
                results.security_report = security_report
            else:
                print("  🛡️  Running security checks…")
                security_report = await security_scanner.perform_security_scan(
                    ScanResult(servers=servers, tools=tools, resources=resources, prompts=prompts, resource_templates=templates, config_files=config_files,
                               errors=errors, status=status)
                )
                results = ScanResult(servers=servers, tools=tools, resources=resources, prompts=prompts, resource_templates=templates, config_files=config_files,
                                     errors=errors, status=status)
                results.security_report = security_report

            output_file = determine_output_file(args, "scan")
            output_data = None
            markdown_content = None
            if args.report_type == "json":
                output_data = {
                    "servers": [
                        {
                            "name": server.name,
                            "type": server.type.value,
                            "endpoint": server.endpoint,
                            "command": server.command,
                            "args": _redact_args(server.args),
                            "headers": _redact_headers(server.headers),
                            "env": _redact_env(server.env),
                            "disabled": server.disabled,
                            "additional_permissions": server.additional_permissions,
                            "tools": [tool.name for tool in results.tools if tool.server_name == server.name],
                            "resources": [resource.name for resource in results.resources if
                                          resource.server_name == server.name],
                            "prompts": [prompt.name for prompt in results.prompts if prompt.server_name == server.name],
                            "resource_templates": [template.name for template in results.resource_templates if template.server_name == server.name],
                            "source_file": server.source_file
                        }
                        for server in results.servers
                    ],
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "input_schema": tool.input_schema,
                            "server_name": tool.server_name,
                            "server_endpoint": tool.server_endpoint
                        }
                        for tool in results.tools
                    ],
                    "resources": [
                        {
                            "uri": resource.uri,
                            "name": resource.name,
                            "description": resource.description,
                            "mime_type": resource.mime_type,
                            "server_name": resource.server_name,
                            "server_endpoint": resource.server_endpoint
                        }
                        for resource in results.resources
                    ],
                    "prompts": [
                        {
                            "name": prompt.name,
                            "description": prompt.description,
                            "arguments": prompt.arguments,
                            "server_name": prompt.server_name,
                            "server_endpoint": prompt.server_endpoint
                        }
                        for prompt in results.prompts
                    ],
                    "resource_templates": [
                        {
                            "name": template.name,
                            "uri_template": template.uri_template,
                            "description": template.description,
                            "mime_type": template.mime_type,
                            "server_name": template.server_name,
                            "server_endpoint": template.server_endpoint
                        }
                        for template in results.resource_templates
                    ],
                    "config_files": results.config_files,
                    "errors": results.errors,
                    "status": results.status,
                    "baseline_status": build_baseline_status(baseline_path_str, baseline is not None, baseline_warning),
                    "security_report": {
                        "risk_level": results.security_report.risk_level.value if results.security_report else "NONE",
                        "total_findings": results.security_report.total_issues if results.security_report else 0,
                        "findings_by_severity": {k.value: v for k, v in (
                            results.security_report.issues_by_severity.items() if results.security_report else [])},
                        "findings_by_type": results.security_report.issues_by_type if results.security_report else {},
                        "grouped_findings": [
                            _grouped_issue_to_dict(grouped)
                            for grouped in (results.security_report.grouped_issues if results.security_report else [])
                        ]
                    }
                }
            else:
                baseline_status_dict = build_baseline_status(baseline_path_str, baseline is not None, baseline_warning)
                markdown_content = format_scan_results_as_markdown(results, baseline_status_dict)
            print()
            summary = scanner.get_scan_summary(results)
            print_separator('═', 60)
            print("📊 SUMMARY")
            print_separator('═', 60)
            print(f"🔲 Servers found:        {summary['total_servers']}")
            try:
                connected_count = len(connected)
                print(f"🔗 Connected servers:    {connected_count}/{summary['total_servers']}")
            except Exception:
                pass
            print(f"🔧 Tools found:          {summary['total_tools']}")
            print(f"📁 Resources found:      {summary['total_resources']}")
            print(f"💬 Prompts found:        {summary['total_prompts']}")
            print(f"🗂️  Resource Templates:   {summary['total_resource_templates']}")
            print(f"📄 Config files:         {summary['config_files']}")
            if baseline_path_str and baseline:
                print(f"🧭 Baseline Loaded:      Yes")
            else:
                print(f"🧭 Baseline Loaded:      No")
            if summary['errors'] > 0:
                print(f"❌ Errors:               {summary['errors']}")
            if results.status:
                print(f"💎 Status:")
                for msg in results.status:
                    print(f"   {msg}")
            print()
            print_separator('═', 60)
            risk = results.security_report.risk_level.value if results.security_report else "NONE"
            total_issues = results.security_report.total_issues if results.security_report else 0
            
            if total_issues == 0:
                icon = '✅'
            else:
                icon = get_level_emoji(risk, RISK_EMOJI)
            
            print(f"{icon} SECURITY REPORT")
            print_separator('═', 60)
            print(f"🔺 Total Findings:       {total_issues}")

            if results.security_report and total_issues > 0:
                print(f"\n📊 Findings by Severity:")
                severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
                for sev_name in severity_order:
                    for sev, count in results.security_report.issues_by_severity.items():
                        sev_str = sev.value if hasattr(sev, 'value') else str(sev)
                        if sev_str.upper() == sev_name and count > 0:
                            emoji = get_level_emoji(sev_str, SEVERITY_EMOJI)
                            print(f"   {emoji} {sev_str.upper()}: {count}")

                grouped_issues = results.security_report.grouped_issues
                if grouped_issues:
                    print(f"\n🪲  Findings by Type:\n")
                    
                    for grouped in grouped_issues:
                        sev_str = grouped.severity.value.upper()
                        emoji = get_level_emoji(sev_str, SEVERITY_EMOJI)
                        
                        print(f"   {emoji} {grouped.issue_type} ({sev_str})")
                        print(wrap_text_with_indent(grouped.description, indent="       ", max_lines=None))
                        
                        print(f"       🐞 Entities affected ({grouped.total_entities}):")
                        for entity in grouped.entities_affected:
                            entity_display = _format_entity_display(entity)
                            print(f"           ⮕  {entity_display}")
                        
                        print(f"       💡 Remediation:")
                        print(wrap_text_with_indent(grouped.remediation, indent="           ", max_lines=None))
                        print()

            try:
                if args.report_type == "json":
                    save_report_to_file(json.dumps(output_data, indent=2), output_file, "json", suppress_print=True)
                else:
                    save_report_to_file(markdown_content, output_file, "markdown", suppress_print=True)
                print(f"💾 Report saved to {output_file}")
            except Exception as e:
                print(f"\n⚠️  Warning: Failed to save report to {output_file}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Scan failed: {e}", file=sys.stderr)
        sys.exit(1)


async def inspect_command(args):
    print('\n🏃 Running MCP Checkpoint in inspect mode...\n')

    from .scanner import MCPConfigScanner
    from .security_utils import ScanResult
    from .baseline import generate_baseline, save_baseline
    
    scanner = MCPConfigScanner()
    
    baseline_path_str = args.baseline if args.baseline else "baseline.json"
    baseline_path = None
    
    try:
        validated_path = validate_baseline_path(baseline_path_str, 'inspect')
        baseline_path = validated_path
    except ValueError as e:
        print(f"\n  ❌ Error: {e}")
        sys.exit(1)
    
    custom_paths = []
    if args.config:
        custom_paths.extend(args.config)
    
    missing_paths = []
    if not custom_paths:
        print("  📄 No config provided — searching known locations…")
    else:
        for p in custom_paths:
            exists = Path(p).exists()
            status_text = " (✅ found)" if exists else " (❌ not found)"
            print(f"  📄 Using config: {p}{status_text}")
            if not exists:
                missing_paths.append(p)
        if missing_paths:
            custom_paths = [p for p in custom_paths if Path(p).exists()]
            if not custom_paths:
                print(
                    "\n  No valid config files found. Please provide at least one valid config file path with --config.")
                sys.exit(1)

    try:
        with SuppressStderr():
            config_files = await scanner.discover_config_files(custom_paths)
            print("     🧩 Parsing configuration…")
            is_user_provided = bool(custom_paths)

            servers = []
            parse_errors = []
            for cfg in config_files:
                try:
                    parsed = await scanner.parse_single_config(cfg, is_user_provided)
                    servers.extend(parsed)
                except Exception as e:
                    parse_errors.append(f"Failed to parse config: {cfg} ({e})")

            if is_user_provided and len(servers) == 0:
                print("\n  ❌ Failed to parse provided config or no MCP servers found in it.")
                for p in config_files:
                    print(f"     ↳ {p}")
                if parse_errors:
                    for err in parse_errors:
                        print(f"     ❌ {err}")
                print("\n  Ensure the file is valid JSON/YAML and follows expected schema (servers/mcpServers).")
                sys.exit(1)

            server_names = [s.name for s in servers]
            if server_names:
                shown = ", ".join(server_names[:5])
                more = f" (+{len(server_names) - 5} more)" if len(server_names) > 5 else ""
                print(f"\n  🔲 Servers found ({len(server_names)}): {shown}{more}")

            connected = set()
            failed = []
            seen_connecting = set()
            seen_oauth = set()

            def progress_cb(event, data):
                if event == 'failed':
                    name = data.get('server')
                    err = data.get('error', 'error')
                    failed.append((name, err))
                    clean_err = err.replace(f"Failed to connect to server: {name}", "").strip()
                    if not clean_err or clean_err == err:
                        clean_err = err
                    print(f"     ❌ Connection failed: {name} ({clean_err})")
                elif event == 'oauth_wait':
                    name = data.get('server')
                    if name and name not in seen_oauth:
                        seen_oauth.add(name)
                        print(f"        ⏳ Waiting for OAuth: {name}")
                elif event == 'oauth_approved':
                    name = data.get('server')
                    if name and getattr(args, 'verbose', False):
                        print(f"        🆗 Access approved: {name}")
                elif event == 'connected':
                    name = data.get('server')
                    if name:
                        connected.add(name)
                        tools_n = data.get('tools', 0)
                        res_n = data.get('resources', 0)
                        prompts_n = data.get('prompts', 0)
                        templates_n = data.get('resource_templates', 0)
                        print(f"        🔗 Connected: {name} (tools {tools_n}, resources {res_n}, prompts {prompts_n}, resource templates {templates_n})")

            print("     🔌 Connecting to servers…")

            tools, resources, prompts, templates = await scanner.discover_all(servers, progress=progress_cb)

            errors = []
            status = []

            if missing_paths:
                for p in missing_paths:
                    errors.append(f"Config not found: {p}")
                if is_user_provided:
                    total_provided = len(args.config) if args.config else 0
                    missing_count = len(missing_paths)
                    status.append(
                        f"Some provided configs ({missing_count}/{total_provided}) not found. Results exclude those files.")

            if parse_errors:
                errors.extend(parse_errors)
                if is_user_provided:
                    total_cfgs = len(config_files)
                    failed_cfgs = len(parse_errors)
                    status.append(
                        f"Some provided configs ({failed_cfgs}/{total_cfgs}) failed to parse. Results exclude those files.")

            for server_name, error_msg in failed:
                clean_error = error_msg.replace(f"Failed to connect to server: {server_name}", "").strip()
                if not clean_error or clean_error == error_msg:
                    clean_error = error_msg
                errors.append(f"Connection failed to server '{server_name}': {clean_error}")

            enabled_servers = [s for s in servers if not s.disabled]
            total_servers = len(enabled_servers)
            connected_count = len(connected)
            failed_count = len(failed)

            if connected_count == 0 and (failed_count > 0 or total_servers > 0):
                status.append("No servers connected. Cannot proceed with inspection.")
                print("\n  ⚠️  No servers could be connected. Cannot proceed with inspection.")
                print("      ‼️  Check your server configurations and network connectivity.\n")
                results = ScanResult(servers=servers, tools=[], resources=[], prompts=[], resource_templates=[], config_files=config_files, errors=errors,
                                     status=status)
            elif total_servers == 0:
                status.append("No servers connected. Cannot proceed with inspection.")
                print("\n  ⚠️  No servers could be connected. Cannot proceed with inspection.")
                print("      ‼️  Check your server configurations and network connectivity.\n")
                results = ScanResult(servers=servers, tools=[], resources=[], prompts=[], resource_templates=[], config_files=config_files, errors=errors,
                                     status=status)
            elif failed_count > 0:
                status.append(
                    f"Some servers ({failed_count}/{total_servers}) failed to connect. Inspection results are incomplete for failed servers.")
                print("\n  🔍 Discovering tools/resources/prompts…\n")
                results = ScanResult(servers=servers, tools=tools, resources=resources, prompts=prompts, resource_templates=templates, config_files=config_files,
                                     errors=errors, status=status)
            else:
                status.append("All servers connected. Inspection complete.")
                print("\n  🔍 Discovering tools/resources/resource templates/prompts…\n")
                results = ScanResult(servers=servers, tools=tools, resources=resources, prompts=prompts, resource_templates=templates, config_files=config_files,
                                     errors=errors, status=status)

        baseline_data = generate_baseline(results)
        save_baseline(baseline_data, baseline_path)
        print(f"  🧭 Baseline saved to: {baseline_path_str}\n")

        output_file = determine_output_file(args, "inspect")
        output_data = None
        markdown_content = None

        if args.report_type == "json":
            output_data = {
                "servers": [
                    {
                        "name": server.name,
                        "type": server.type.value,
                        "endpoint": server.endpoint,
                        "command": server.command,
                        "args": server.args,
                        "headers": _redact_headers(server.headers),
                        "env": _redact_env(server.env),
                        "disabled": server.disabled,
                        "additional_permissions": server.additional_permissions,
                        "tools": [tool.name for tool in results.tools if tool.server_name == server.name],
                        "resources": [resource.name for resource in results.resources if
                                      resource.server_name == server.name],
                        "prompts": [prompt.name for prompt in results.prompts if prompt.server_name == server.name],
                        "resource_templates": [template.name for template in results.resource_templates if template.server_name == server.name],
                        "source_file": server.source_file
                    }
                    for server in results.servers
                ],
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "server_name": tool.server_name,
                        "server_endpoint": tool.server_endpoint
                    }
                    for tool in results.tools
                ],
                "resources": [
                    {
                        "uri": resource.uri,
                        "name": resource.name,
                        "description": resource.description,
                        "mime_type": resource.mime_type,
                        "server_name": resource.server_name,
                        "server_endpoint": resource.server_endpoint
                    }
                    for resource in results.resources
                ],
                "prompts": [
                    {
                        "name": prompt.name,
                        "description": prompt.description,
                        "arguments": prompt.arguments,
                        "server_name": prompt.server_name,
                        "server_endpoint": prompt.server_endpoint
                    }
                    for prompt in results.prompts
                ],
                "resource_templates": [
                    {
                        "name": template.name,
                        "uri_template": template.uri_template,
                        "description": template.description,
                        "mime_type": template.mime_type,
                        "server_name": template.server_name,
                        "server_endpoint": template.server_endpoint
                    }
                    for template in results.resource_templates
                ],
                "config_files": results.config_files,
                "errors": results.errors,
                "status": results.status,
                "baseline": {
                    "baseline_file": baseline_path_str,
                    "baseline_generated": True,
                    "timestamp": baseline_data.timestamp
                }
            }

        else:
            baseline_info = {
                "baseline_file": baseline_path_str,
                "baseline_generated": True,
                "timestamp": baseline_data.timestamp
            }
            markdown_content = format_inspect_results_as_markdown(results, baseline_info)

        summary = scanner.get_scan_summary(results)
        print_separator('═', 60)
        print("📊 SUMMARY")
        print_separator('═', 60)
        print(f"🔲 Servers found:        {summary['total_servers']}")
        try:
            connected_count = len(connected)
            print(f"🔗 Connected servers:    {connected_count}/{summary['total_servers']}")
        except Exception:
            pass
        print(f"🔧 Tools found:          {summary['total_tools']}")
        print(f"📁 Resources found:      {summary['total_resources']}")
        print(f"💬 Prompts found:        {summary['total_prompts']}")
        print(f"🗂️  Resource Templates:   {summary['total_resource_templates']}")
        print(f"📄 Config files:         {summary['config_files']}")
        print(f"🧭 Baseline:             {baseline_path_str} (generated)")
        if summary['errors'] > 0:
            print(f"❌ Errors:               {summary['errors']}")
        if results.status:
            print(f"💎 Status:")
            for msg in results.status:
                print(f"   {msg}")
            print()
        print_separator('═', 60)
        print(f"📒 INSPECTION REPORT")
        print_separator('═', 60)
        print(f"📄 Configuration Files ({len(results.config_files)}):")
        for config_file in results.config_files:
            print(f"   • {config_file}")
        
        if results.servers:
            print(f"\n🔲  Servers ({len(results.servers)}):")
            for server in results.servers:
                status = "DISABLED" if server.disabled else "ENABLED"
                status_icon = "⛔" if server.disabled else "✅"
                print(f"   {status_icon} {server.name} ({server.type.value}) - {status}")
                if server.source_file:
                    print(f"      📍 Source: {server.source_file}")
                if server.endpoint:
                    print(f"      🔗 Endpoint: {server.endpoint}")
                if server.command:
                    print(f"      ⚙️ Command: {server.command}")
                if server.args:
                    print(f"      🔣 Args: {' '.join(_redact_args(server.args))}")
                if server.headers:
                    redacted_headers = _redact_headers(server.headers)
                    headers_str = ', '.join([f"{k}={v}" for k, v in redacted_headers.items()])
                    print(f"      📑 Headers: {headers_str}")
                if server.env:
                    redacted_env = _redact_env(server.env)
                    env_str = ', '.join([f"{k}={v}" for k, v in redacted_env.items()])
                    print(f"      🔐 Env: {env_str}")
                if server.additional_permissions:
                    print(f"      ⚠️  Permissions: {', '.join(server.additional_permissions)}")
                print()
        
        if results.tools:
            print(f"🔧 Tools ({len(results.tools)}):")
            for tool in results.tools:
                print(f"   • {tool.name}")
                print(f"     🔲 Server: {tool.server_name}")
                preview = truncate_lines(tool.description or "", 2).strip()
                if preview:
                    print(f"     📝 Description: {preview}\n")

        if results.resources:
            print(f"📁 Resources ({len(results.resources)}):")
            for resource in results.resources:
                print(f"   • {resource.name}")
                print(f"     🔲 Server: {resource.server_name}")
                print(f"     🔗 URI: {resource.uri}")
                if resource.description:
                    rprev = truncate_lines(resource.description, 2).strip()
                    print(f"     📝 Description: {rprev}")
                print(f"     📄 MIME Type: {resource.mime_type}\n")

        if results.prompts:
            print(f"💬 Prompts ({len(results.prompts)}):")
            for prompt in results.prompts:
                print(f"   • {prompt.name}")
                print(f"     🔲 Server: {prompt.server_name}")
                if prompt.description:
                    pprev = truncate_lines(prompt.description, 2).strip()
                    print(f"     📝 Description: {pprev}")
                if prompt.arguments:
                    arg_names = ', '.join(prompt.arguments.keys())
                    print(f"     🔣  Arguments: {arg_names} ({len(prompt.arguments)} defined)\n")

        if results.resource_templates:
            print(f"🗂️  Resource Templates ({len(results.resource_templates)}):")
            for template in results.resource_templates:
                print(f"   • {template.name}")
                print(f"     🔲 Server: {template.server_name}")
                print(f"     🔗 URI Template: {template.uri_template}")
                if template.description:
                    tprev = truncate_lines(template.description, 2).strip()
                    print(f"     📝 Description: {tprev}")
                print(f"     📄 MIME Type: {template.mime_type}\n")

        try:
            if args.report_type == "json":
                save_report_to_file(json.dumps(output_data, indent=2), output_file, "json", suppress_print=True)
            else:
                save_report_to_file(markdown_content, output_file, "markdown", suppress_print=True)
            print(f"💾 Report saved to {output_file}")
        except Exception as e:
            print(f"\n⚠️  Warning: Failed to save report to {output_file}: {e}", file=sys.stderr)

        if any("No servers connected" in status_msg for status_msg in results.status):
            sys.exit(1)
        
    except Exception as e:
        print(f"Inspection failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    print_banner()
    parser = argparse.ArgumentParser(

        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    ## Inspect Mode (Inventory and Generate Baseline)
        mcp-checkpoint inspect                                 # Inspect all known configs and generate baseline.json (no security analysis)
        mcp-checkpoint inspect --config ./config.json          # Inspect specific config and generate baseline.json (no security analysis)
        mcp-checkpoint inspect --config ./config1.json \\
                            --config ./config2.json            # Inspect multiple configs and generate baseline.json (no security analysis)
        mcp-checkpoint inspect --baseline ./my-baseline.json   # Generate custom baseline file (defaults to baseline.json if not specified)
        mcp-checkpoint inspect --config ./config.json \\
                            --baseline ./my-baseline.json      # Inspect specific config and generate custom baseline file
        mcp-checkpoint inspect --output results.json           # Save results to file
        mcp-checkpoint inspect --verbose                       # Detailed output
    
    ## Scan Mode (Security Analysis)
        mcp-checkpoint scan                                    # Scan all known configs using default baseline.json (if present) for security risks
        mcp-checkpoint scan --config ./config.json             # Scan specific config using default baseline.json (if present)for security risks
        mcp-checkpoint scan --config ./config1.json \\
                        --config ./config2.json                # Scan multiple configs using default baseline.json (if present) in one run
        mcp-checkpoint scan --baseline ./my-baseline.json      # Scan all known configs with custom baseline for drift detection
        mcp-checkpoint scan --config ./config.json \\
                        --baseline ./my-baseline.json          # Scan specific config with custom baseline for drift detection
        mcp-checkpoint scan --output results.json              # Save results to file
        mcp-checkpoint scan --verbose                          # Detailed output
        mcp-checkpoint scan --show-logs                        # Display debug logs in terminal
    
Note: 
    First-time scan will download the ML model for prompt injection check (~290MB) from Hugging Face.
    Subsequent scans use the cached model for faster completion.
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    scan_parser = subparsers.add_parser(
        'scan', 
        help='Scan MCP configurations',
        description="""
        Scan MCP server configurations for detecting any security risks.
        
        Note: 
          On first run, the prompt injection detection model will be 
        automatically downloaded from Hugging Face (~290MB). 
          This is an one-time download and subsequent scans will use the cached model.
        """
    )
    scan_parser.add_argument('--config', action='append', help='Custom config file path')
    scan_parser.add_argument('--baseline', help='Baseline file path for comparison (default: baseline.json in current directory)')
    scan_parser.add_argument('--report-type', choices=['json', 'md'], default='json',
                             help='Output format: json or markdown (default: json)')
    scan_parser.add_argument('--output', '-o', help='Output file path (optional)')
    scan_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    scan_parser.add_argument('--show-logs', action='store_true',
                             help='Display debug logs in terminal (logs always saved to file)')
    scan_parser.set_defaults(func=scan_command)
    
    inspect_parser = subparsers.add_parser(
        'inspect', 
        help='Inspect MCP configurations',
        description="""
        Inspect MCP server configurations and generate a baseline for future comparisons.
        """
    )
    inspect_parser.add_argument('--config', action='append', help='Custom config file path')
    inspect_parser.add_argument('--baseline', help='Baseline file path to save (default: baseline.json in current directory)')
    inspect_parser.add_argument('--report-type', choices=['json', 'md'], default='json',
                                help='Output format: json or markdown (default: json)')
    inspect_parser.add_argument('--output', '-o', help='Output file path (optional)')
    inspect_parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    inspect_parser.add_argument('--show-logs', action='store_true',
                                help='Display debug logs in terminal (logs always saved to file)')
    inspect_parser.set_defaults(func=inspect_command)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if hasattr(args, 'show_logs') and args.show_logs:
        setup_logging(show_logs=True)
    else:
        setup_logging(show_logs=False)

    asyncio.run(args.func(args))


if __name__ == '__main__':
    main()