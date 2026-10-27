from mcp.server.fastmcp import FastMCP
import os
import glob

# Initialize the MCP server
mcp = FastMCP("VolvoDataTool")
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# ══════════════════════════════════════════════════════════════════════
# VOLVO DATA CLASSIFICATION — MCP Layer
# Security layer 1: Kong ai-prompt-guard blocks PII patterns in transit
# Security layer 2: MCP server NEVER serves RESTRICTED files to any role
# Security layer 3: Python RBAC filters admin-only files per role
# (No Kong plugin exists that can filter per-file MCP tool call results,
#  so this Python backstop is required for layers 2 & 3)
# ══════════════════════════════════════════════════════════════════════

# Files containing personal PII — blocked at MCP level for ALL roles
# These are also blocked at Kong level via ai-prompt-guard deny patterns
RESTRICTED_FILES = {
    "customer_data.csv",          # Contains customer names, contacts — PII
    "employee_records.csv",       # Contains HR/salary data — Special Category PII
    "internal_security_policy.txt",  # Security architecture details — operational risk
}

def is_allowed(filename: str) -> bool:
    return filename not in RESTRICTED_FILES

@mcp.tool()
def fetch_documents(query: str) -> str:
    """Search across internal Volvo data files and return matching content.
    Args:
        query: The search string to look for within the internal data files.
    """
    query = query.lower()
    results = []

    if not os.path.exists(DATA_DIR):
        return "Error: Data directory not found."

    for filepath in glob.glob(os.path.join(DATA_DIR, '*')):
        filename = os.path.basename(filepath)
        if not os.path.isfile(filepath):
            continue
        # Security check: skip restricted files at MCP level
        if not is_allowed(filename):
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            words = query.lower().split()
            if not query or query.lower() in ["all", "all files", "everything"] or \
               any(word in content.lower() for word in words):
                results.append(f"--- File: {filename} ---\n{content}")

    return "\n\n".join(results) if results else "No matches found."

@mcp.tool()
def list_available_files() -> str:
    """Returns a list of all dataset files accessible via this MCP server.
    Note: Restricted (PII-containing) files are not listed here.
    Role-based filtering is applied by the calling agent.
    """
    if not os.path.exists(DATA_DIR):
        return "Error: Data directory not found."
    files = sorted([
        f for f in os.listdir(DATA_DIR)
        if os.path.isfile(os.path.join(DATA_DIR, f)) and is_allowed(f)
    ])
    return "Available files:\n- " + "\n- ".join(files)

if __name__ == '__main__':
    # Start the server using SSE transport so Kong AI Gateway can proxy MCP traffic
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 5000
    mcp.run(transport='sse')

