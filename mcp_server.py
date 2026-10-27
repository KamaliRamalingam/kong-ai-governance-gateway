from mcp.server.fastmcp import FastMCP
import os
import glob

mcp = FastMCP("VolvoDataTool")
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


@mcp.tool()
def read_file(filename: str) -> str:
    """Read the full contents of a specific data file by its exact filename.

    Args:
        filename: The exact filename to read (e.g. 'vehicle_specs.csv', 'fleet_analytics_report.txt').
    """
    filepath = os.path.join(DATA_DIR, filename)
    # Basic path traversal guard
    if not os.path.abspath(filepath).startswith(os.path.abspath(DATA_DIR)):
        return "Error: Invalid filename."
    if not os.path.isfile(filepath):
        return f"Error: File '{filename}' not found."
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


@mcp.tool()
def search_files(query: str) -> str:
    """Search across all data files for lines or sections matching the query.

    Args:
        query: A keyword or phrase to search for in the data files.
    """
    query_lower = query.lower()
    results = []
    if not os.path.exists(DATA_DIR):
        return "Error: Data directory not found."
    for filepath in sorted(glob.glob(os.path.join(DATA_DIR, '*'))):
        if not os.path.isfile(filepath):
            continue
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        matching_lines = [
            line for line in content.splitlines()
            if query_lower in line.lower()
        ]
        if matching_lines:
            results.append(
                f"--- {os.path.basename(filepath)} ---\n" + "\n".join(matching_lines)
            )
    return "\n\n".join(results) if results else f"No matches found for '{query}'."


@mcp.tool()
def list_files() -> str:
    """Return a list of all available data files that can be queried."""
    if not os.path.exists(DATA_DIR):
        return "Error: Data directory not found."
    files = sorted(
        f for f in os.listdir(DATA_DIR)
        if os.path.isfile(os.path.join(DATA_DIR, f))
    )
    return "Available files:\n- " + "\n- ".join(files)


if __name__ == '__main__':
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = 8765
    mcp.run(transport='sse')
