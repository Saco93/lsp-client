# Example: C# analysis with csharp-ls
#
# Install the server before running this example:
#   dotnet tool install --global csharp-ls
#
# Run from a directory containing a .sln, .slnx, or .csproj file:
#   uv run examples/csharp_ls.py Program.cs 10 20

from __future__ import annotations

import sys
from pathlib import Path

import anyio

from lsp_client import CsharpLsClient, Position
from lsp_client.utils.types import lsp_type


async def main(file_path: Path, line: int, character: int) -> None:
    file_path = file_path.resolve()
    workspace = CsharpLsClient.get_language_config().find_project_root(file_path)
    if workspace is None:
        raise ValueError(f"No .sln, .slnx, or .csproj found for {file_path}")

    async with CsharpLsClient(workspace=workspace) as client:
        position = Position(line=line, character=character)
        hover = await client.request_hover(file_path, position)
        definitions = await client.request_definition(file_path, position)
        references = await client.request_references(file_path, position)
        diagnostics = await client.request_diagnostics(file_path)

    definition_count = (
        0
        if definitions is None
        else 1
        if isinstance(definitions, lsp_type.Location)
        else len(definitions)
    )
    print(f"Hover: {hover.value if hover else 'none'}")
    print(f"Definitions: {definition_count}")
    print(f"References: {len(references or [])}")
    print(f"Diagnostics: {len(diagnostics or [])}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: csharp_ls.py <file> <zero-based-line> <character>")

    anyio.run(main, Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]))
