from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from lsp_client import CsharpLsClient, Position
from lsp_client.clients.csharp_ls import _find_csharp_ls

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.requires_server,
    pytest.mark.skipif(
        _find_csharp_ls() is None,
        reason="csharp-ls is not installed",
    ),
]


@pytest.fixture
def csharp_workspace(tmp_path: Path) -> tuple[Path, Path]:
    if shutil.which("dotnet") is None:
        pytest.skip("The .NET SDK is not installed")

    project = tmp_path / "SmokeApp.csproj"
    project.write_text(
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
""",
        encoding="utf-8",
    )
    solution = tmp_path / "Smoke.slnx"
    solution.write_text(
        '<Solution>\n  <Project Path="SmokeApp.csproj" />\n</Solution>\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["dotnet", "restore", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )

    source = tmp_path / "Program.cs"
    source.write_text(
        """namespace SmokeApp;

public static class Greeter
{
    public static string Greeting(string name) => $"Hello, {name}";
}

public static class Program
{
    public static void Main()
    {
        Console.WriteLine(Greeter.Greeting("World"));
    }
}
""",
        encoding="utf-8",
    )

    return tmp_path, source


@pytest.mark.asyncio
async def test_csharp_ls_semantic_workflow(
    csharp_workspace: tuple[Path, Path],
) -> None:
    workspace, source = csharp_workspace

    async with CsharpLsClient(
        workspace=workspace,
        server="local",
        request_timeout=60,
    ) as client:
        usage = Position(line=11, character=42)
        declaration = Position(line=4, character=31)

        hover = await client.request_hover(source, usage)
        definitions = await client.request_definition(source, usage)
        references = await client.request_references(source, declaration)
        diagnostics = await client.request_diagnostics(source)
        workspace_diagnostics = await client.request_workspace_diagnostic()
        rename = await client.request_rename_edits(
            source,
            declaration,
            "CreateGreeting",
        )
        symbols = await client.request_workspace_symbol_list("Greeting")

    assert hover is not None
    assert "Greeting" in hover.value
    assert definitions
    assert references is not None and len(references) == 2
    assert not diagnostics
    assert workspace_diagnostics is not None
    assert rename is not None
    assert symbols
