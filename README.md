<p align="center" style="margin-bottom: 0; line-height: 0;">
<img src="https://github.com/aira-security/mcp-checkpoint/blob/main/mcp-checkpoint.png" width="350"> 
</p>
<h3 align="center" margin-top: -20px; margin-bottom: 70px;>
   MCP Checkpoint
</h3>

<br>

## :rocket: Overview

MCP Checkpoint is a comprehensive security scanner for Model Context Protocol (MCP). Automatically discovers, analyzes, and secures MCP servers integrated with all major Agentic IDEs, Agents and Clients.

<br>

![MCP Checkpoint](https://github.com/aira-security/mcp-checkpoint/blob/main/mcp-checkpoint.gif)


## :bulb: Features

- **🔍 Auto-Discovery**: Finds known MCP configurations for popular Agentic IDEs like Cursor, Windsurf, VS Code, Claude Desktop, and more
- **🔧 Tool, Resource & Prompt Inventory**: Connects to MCP servers and catalogs available tools, resources, and prompt templates
- **🛡️ Security Analysis**: Specialized security checks including Prompt Injection, Rug Pull Attack, Cross-server Tool Shadowing, Tool Poisoning, Tool Name Ambiguity, [and more..](#beginner-security-checks)
- **🧭 Baseline Drift Detection**: Captures approved MCP components and detects rug pulls attacks
- **📊 Comprehensive Reporting**: Generates JSON and Markdown reports with actionable findings
- **📜 Audit Trail**: Timestamped baselines and reports for full traceability of changes and findings


## :toolbox: Installation

```bash
pip install mcp-checkpoint
```

## :running: Quick Start

```bash
# Scan all configurations with security analysis (auto-detects baseline.json if present)
mcp-checkpoint scan

# Inspect configurations and generate baseline (defaults to baseline.json)
mcp-checkpoint inspect

# Use custom configuration file
mcp-checkpoint scan --config /path/to/config.json

# Scan multiple configuration files
 mcp-checkpoint scan \
   --config /path/to/cursor.mcp.json \
   --config /path/to/vscode.mcp.json

# Use custom baseline file path
mcp-checkpoint inspect --baseline /path/to/my-baseline.json
mcp-checkpoint scan --baseline /path/to/my-baseline.json

# Generate markdown report
mcp-checkpoint scan --report-type md

# Save to custom file
mcp-checkpoint scan --output my-report.json
mcp-checkpoint scan --report-type md --output my-report.md
```

#### :gear: Command Options

| Option                    | Description                                                         |
|---------------------------|---------------------------------------------------------------------|
| `--config`                | Custom configuration file path (can be used multiple times)         |
| `--baseline`              | Baseline file for drift detection (scan) or creation (inspect)      |
| `--report-type {json,md}` | Output format (default: json)                                       |
| `--output`                | Custom output file path                                             |
| `--verbose`               | Detailed terminal output                                            |
| `--show-logs`             | Display debug logs in terminal                                      |


## :beginner: Security Checks

### 🛡️ Standard Checks

- **Prompt Injection**  
- **Indirect Prompt Injection**
- **Cross-Server Tool Shadowing**
- **Tool Poisoning**
  - **Prompt Injection in Tool Description, Name and Args**
  - **Command Injection in Tool Description, Name and Args**
- **Tool Name Ambiguity**
- **Command Injection**
- **Excessive Tool Permissions**
- **Hardcoded Secrets**

### 🧭 Baseline Checks

Detects deviations from approved MCP components (requires a baseline generated via `inspect` mode):

- **Rug Pull Attack**
  - **Tool Modified**
  - **Resource Modified**
  - **Resource Template Modified**
  - **Prompt Modified**

### :page_with_curl: Logging

Logs are automatically saved to `logs/mcp_checkpoint.log`:

```bash
# Default: logs saved to file only
mcp-checkpoint scan

# Show logs in terminal too
mcp-checkpoint scan --show-logs
```


### :test_tube: Demo

Test MCP Checkpoint using our intentionally vulnerable MCP servers. For details, see the [demo guide](demo-mcp-server/README.md).

### :office: Enterprise Edition

Get enterprise-grade protection with **Active Insight Mode**, offering ***runtime agent behavior analysis***, enhanced features, and additional scan capabilities — [book a demo](https://calendly.com/mohan-/aira-security) today.

### :star2: Community

 [Join our Slack](https://join.slack.com/t/airasecurityc-jwt3316/shared_invite/zt-3iar5tm3k-R5js~WfnDIHRNtSgd7D0Bg) - a space for developers and security engineers building together to secure AI agents.

### :question: FAQs

**Q: Is my source code ever shared, or does everything run locally?**

MCP Checkpoint runs entirely locally. Inspect and scan modes analyze your MCP configurations, detect MCP servers integrated with your agents, and evaluate them directly on your machine. Prompt injection checks use our open-source model `Aira-security/FT-Llama-Prompt-Guard-2`, downloaded from Hugging Face to your local environment, ensuring your data and code is never shared externally.


### :balance_scale: License

Distributed under the Apache 2.0 License. See [LICENSE](https://github.com/aira-security/mcp-checkpoint/blob/main/LICENSE) for more information.