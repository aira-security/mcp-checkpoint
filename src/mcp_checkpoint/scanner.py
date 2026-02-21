import os
import json
import yaml
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from pathlib import Path
from .config_validator import load_and_validate_config
from .connector import MCPConnector
from .security_utils import (
    TransportType,
    MCPServerInfo,
    ToolInfo,
    ResourceInfo,
    PromptInfo,
    ResourceTemplateInfo,
    ScanResult
)

logger = logging.getLogger(__name__)


def _safe_progress_callback(progress, event: str, data: Dict[str, Any]):
    if progress:
        try:
            progress(event, data)
        except Exception:
            pass


class MCPConfigScanner:
    
    def __init__(self):
        self.known_locations = {
            # Cursor
            "~/.cursor/mcp.json": "cursor",
            # Windsurf
            "~/.codeium/windsurf/mcp_config.json": "windsurf",
            # VS Code
            "~/.vscode/mcp.json": "vscode",
            "~/AppData/Roaming/Code/User/settings.json": "vscode",
            "~/AppData/Roaming/Code/User/mcp.json": "vscode",
            "~/Library/Application Support/Code/User/settings.json": "vscode",
            "~/Library/Application Support/Code/User/mcp.json": "vscode",
            "~/.config/Code/User/settings.json": "vscode",
            "~/.config/Code/User/mcp.json": "vscode",
            # Claude Desktop (macOS)
            "~/Library/Application Support/Claude/claude_desktop_config.json": "claude_desktop",
            # Claude Code
            "~/.claude/settings.json": "claude_desktop",
            "~/AppData/Roaming/Claude/claude_desktop_config.json": "claude_desktop",
            # Gemini CLI
            "~/.gemini/settings.json": "gemini_cli",
            ".gemini/settings.json": "gemini_cli",
            # Neovim
            "~/.config/nvim/mcp.json": "neovim",
            # Helix
            "~/.config/helix/mcp.json": "helix",
            # Zed
            "~/.config/zed/mcp.json": "zed",
            # Fallback locations
            "./mcp_servers.json": "custom",
            "./mcp.json": "custom",
            "~/.config/mcp/servers.json": "custom"
        }
    
    async def discover_config_files(self, custom_paths: List[str] = None) -> List[str]:
        config_files = []
        
        if custom_paths:
            config_files.extend(custom_paths)
            logger.info(f"Using custom config files: {custom_paths}")
        else:
            for location in self.known_locations:
                expanded_path = os.path.expanduser(location)
                if os.path.exists(expanded_path):
                    config_files.append(expanded_path)
                    logger.info(f"Found config file: {expanded_path}")
        
        if not custom_paths:
            current_dir = Path(".")
            for pattern in ["mcp*.json", "*.mcp.json", "mcp*.yaml", "*.mcp.yaml"]:
                for file_path in current_dir.glob(pattern):
                    if file_path.is_file():
                        config_files.append(str(file_path))
                        logger.info(f"Found config file: {file_path}")
        
        self.discovered_configs = config_files
        return config_files
    
    async def parse_config_files(self, config_files: List[str], is_user_provided: bool = False) -> List[MCPServerInfo]:
        servers = []
        
        for config_file in config_files:
            try:
                all_servers = await self.parse_single_config(config_file, is_user_provided)
                servers.extend(all_servers)
                logger.info(f"Parsed {len(all_servers)} servers from {config_file}")
            except Exception as e:
                logger.error(f"Failed to parse {config_file}: {e}")
        
        return servers
    
    async def parse_single_config(self, config_file: str, is_user_provided: bool = False) -> List[MCPServerInfo]:
        
        
        config, validation_errors = load_and_validate_config(config_file)
        
        if config is None:
            if validation_errors:
                error_msg = "; ".join(validation_errors)
                raise ValueError(f"Configuration validation failed for '{config_file}': {error_msg}")
            raise ValueError(f"Failed to load configuration file: {config_file}")
        
        if validation_errors and is_user_provided:
            for error in validation_errors:
                logger.warning(f"Configuration validation warning: {error}")
        
        servers = []
        
        if 'mcpServers' in config:
            mcp_servers = config['mcpServers']
        elif 'servers' in config:
            mcp_servers = config['servers']
        else:
            mcp_servers = config
        
        for server_name, server_config in mcp_servers.items():
            try:
                server_info = self.create_server_info(server_name, server_config, config_file, is_user_provided)
                servers.append(server_info)
            except Exception as e:
                logger.error(f"Failed to parse server {server_name}: {e}", exc_info=False)
        
        return servers
    
    def create_server_info(self, name: str, config: Dict[str, Any], source_file: str,
                           is_user_provided: bool = False) -> MCPServerInfo:
        server_type = config.get('transport') or config.get('type')

        if not server_type:
            if config.get('url') or config.get('endpoint'):
                server_type = 'http'
            elif '--transport' in config.get('args', []) and 'http-only' in config.get('args', []):
                server_type = 'http'
            else:
                server_type = 'stdio'
                logger.warning(f"Server '{name}' missing 'type' field, so defaulting to 'stdio' "
                             f"Consider explicitly setting the 'type' field in the configuration.")

        try:
            transport_type = TransportType(server_type.lower())
        except ValueError:
            raise ValueError(
                f"Server '{name}' has invalid transport type '{server_type}'. Valid types: {[t.value for t in TransportType]}")

        endpoint = config.get('url') or config.get('endpoint')
        command = config.get('command')
        args = config.get('args', [])
        headers = config.get('headers', {})
        env = config.get('env', {})
        disabled = config.get('disabled', False)

        additional_permissions = None
        if not is_user_provided:
            client_type = self._detect_client_type(source_file)
            if client_type != 'custom':
                additional_permissions = self._extract_client_permissions_from_config(config, source_file)

        server_info = MCPServerInfo(
            name=name,
            type=transport_type,
            endpoint=endpoint,
            command=command,
            args=args,
            headers=headers,
            env=env,
            disabled=disabled,
            tools=[],
            resources=[],
            source_file=source_file
        )
    
        if additional_permissions is not None:
            server_info.additional_permissions = additional_permissions

        return server_info

    def _extract_client_permissions_from_config(self, config: Dict[str, Any], source_file: str) -> List[str]:
        client_type = self._detect_client_type(source_file)

        client_permissions = []

        if client_type == 'windsurf':
            windsurf_permissions = ['codebase_search', 'find', 'grep_search', 'list_directory',
                                    'read_file', 'edit_file', 'write_to_file', 'run_terminal_command']
            for permission in windsurf_permissions:
                if permission in config:
                    client_permissions.append(permission)

        elif client_type == 'cursor':
            cursor_permissions = ['Read File', 'List Directory', 'Codebase', 'Grep',
                                  'Search Files', 'Web', 'Fetch Rules', 'Edit & Reapply',
                                  'Delete File', 'Terminal']
            for permission in cursor_permissions:
                if permission in config:
                    client_permissions.append(permission)

        elif client_type == 'vscode':
            vscode_permissions = ['extensions', 'fetch', 'findTestFiles', 'githubRepo',
                                  'new', 'openSimpleBrowser', 'problems', 'runCommands',
                                  'runNotebooks', 'runTasks', 'search', 'searchResults',
                                  'terminalLastCommand', 'terminalSelection', 'testFailure',
                                  'usages', 'vscodeAPI', 'changes', 'codebase', 'editFiles']
            for permission in vscode_permissions:
                if permission in config:
                    client_permissions.append(permission)

        elif client_type == 'custom':
            standard_keys = {'type', 'command', 'args', 'headers', 'env', 'disabled', 'name'}
            for key, value in config.items():
                if key not in standard_keys and isinstance(value, bool) and value:
                    client_permissions.append(key)

        return client_permissions

    def _detect_client_type(self, source_file: str) -> str:
        import os

        expanded_path = os.path.expanduser(source_file)

        for known_path, client_type in self.known_locations.items():
            expanded_known_path = os.path.expanduser(known_path)
            if expanded_path == expanded_known_path:
                return client_type

        return 'custom'

    async def discover_all(self, servers: List[MCPServerInfo], progress: Optional[Callable[[str, Dict[str, Any]], None]] = None) -> Tuple[
        List[ToolInfo], List[ResourceInfo], List[PromptInfo], List[ResourceTemplateInfo]]:
        connector = MCPConnector()
        all_tools: List[ToolInfo] = []
        all_resources: List[ResourceInfo] = []
        all_prompts: List[PromptInfo] = []
        all_resource_templates: List[ResourceTemplateInfo] = []
        
        async def discover_for_server(server: MCPServerInfo) -> Tuple[
            List[ToolInfo], List[ResourceInfo], List[PromptInfo], List[ResourceTemplateInfo], str, Optional[str]]:
            if server.disabled:
                logger.info(f"Skipping disabled server: {server.name}")
                return [], [], [], [], server.name, None
            try:
                _safe_progress_callback(progress, 'connecting', {"server": server.name})
                server_tools, server_resources, server_prompts, server_resource_templates = await connector.discover_all(server, progress=progress)
                logger.info(
                    f"Discovered {len(server_tools)} tools, {len(server_resources)} resources, {len(server_prompts)} prompts, {len(server_resource_templates)} resource templates from {server.name}")
                _safe_progress_callback(progress, 'connected', {
                    "server": server.name,
                    "tools": len(server_tools),
                    "resources": len(server_resources),
                    "prompts": len(server_prompts),
                    "resource_templates": len(server_resource_templates)
                })
                return server_tools, server_resources, server_prompts, server_resource_templates, server.name, None
            except Exception as e:
                logger.error(f"Failed to discover from {server.name}: {e}", exc_info=False)
                _safe_progress_callback(progress, 'failed', {"server": server.name, "error": str(e)})
                return [], [], [], [], server.name, str(e)

        tasks = [asyncio.create_task(discover_for_server(s)) for s in servers]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        for tools, resources, prompts, templates, _srv, _err in results:
            all_tools.extend(tools)
            all_resources.extend(resources)
            all_prompts.extend(prompts)
            all_resource_templates.extend(templates)

        return all_tools, all_resources, all_prompts, all_resource_templates
    
    def get_scan_summary(self, scan_result: ScanResult) -> Dict[str, Any]:
        if not scan_result:
            return {"error": "No scan results available"}
        
        return {
            "total_servers": len(scan_result.servers),
            "total_tools": len(scan_result.tools),
            "total_resources": len(scan_result.resources),
            "total_prompts": len(scan_result.prompts),
            "total_resource_templates": len(scan_result.resource_templates),
            "config_files": len(scan_result.config_files),
            "errors": len(scan_result.errors),
            "status": len(scan_result.status),
            "servers_by_type": {
                transport.value: len([s for s in scan_result.servers if s.type == transport])
                for transport in TransportType
            }
        }