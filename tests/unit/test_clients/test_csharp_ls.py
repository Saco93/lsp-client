from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from lsp_client import CsharpLsClient
from lsp_client.clients import clients
from lsp_client.clients.csharp_ls import (
    _DOTNET_GLOBAL_TOOLS,
    _find_csharp_ls,
    ensure_csharp_ls_installed,
)
from lsp_client.clients.lang import find_client
from lsp_client.server import ServerInstallationError
from lsp_client.utils.types import lsp_type


def test_csharp_language_configuration() -> None:
    config = CsharpLsClient.get_language_config()

    assert config.kind is lsp_type.LanguageKind.CSharp
    assert config.suffixes == [".cs"]
    assert config.project_files == ["*.sln", "*.slnx", "*.csproj"]
    assert config.prioritized_project_file_groups == [
        ["*.sln", "*.slnx"],
        ["*.csproj"],
    ]


def test_csharp_solution_root_takes_priority_over_nearer_project(
    tmp_path: Path,
) -> None:
    (tmp_path / "Workspace.sln").touch()
    project = tmp_path / "src" / "App"
    project.mkdir(parents=True)
    (project / "App.csproj").touch()
    source = project / "Program.cs"
    source.touch()

    assert CsharpLsClient.get_language_config().find_project_root(source) == tmp_path


def test_csharp_slnx_takes_priority_over_nearer_project(tmp_path: Path) -> None:
    (tmp_path / "Workspace.slnx").touch()
    project = tmp_path / "src" / "App"
    project.mkdir(parents=True)
    (project / "App.csproj").touch()
    source = project / "Program.cs"
    source.touch()

    assert CsharpLsClient.get_language_config().find_project_root(source) == tmp_path


def test_csharp_uses_nearest_project_when_no_solution_exists(tmp_path: Path) -> None:
    project = tmp_path / "src" / "App"
    project.mkdir(parents=True)
    (project / "App.csproj").touch()
    source = project / "Program.cs"
    source.touch()

    assert CsharpLsClient.get_language_config().find_project_root(source) == project


def test_find_client_discovers_csharp(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").touch()
    source = tmp_path / "Program.cs"
    source.touch()

    target = find_client(source)

    assert target is not None
    assert target.client_cls is CsharpLsClient
    assert target.project_path == tmp_path


def test_csharp_client_is_exported_and_registered() -> None:
    from lsp_client.clients import CsharpLsClient as ExportedCsharpLsClient

    assert ExportedCsharpLsClient is CsharpLsClient
    assert clients["csharp_ls"] is CsharpLsClient


def test_csharp_default_servers() -> None:
    servers = CsharpLsClient.create_default_servers()

    assert Path(servers.local.program).name == "csharp-ls"
    assert list(servers.local.args) == []
    assert servers.local.env is not None
    assert servers.local.env["PATH"].split(os.pathsep, maxsplit=1)[0] == str(
        _DOTNET_GLOBAL_TOOLS
    )
    assert servers.local.ensure_installed is ensure_csharp_ls_installed
    assert servers.container.image == "ghcr.io/lsp-client/csharp-ls:latest"


def test_csharp_default_configuration() -> None:
    config = CsharpLsClient().create_default_config()

    assert config == {
        "csharp": {
            "logLevel": "info",
            "applyFormattingOptions": False,
            "analyzersEnabled": False,
            "useMetadataUris": False,
            "razorSupport": False,
        }
    }


def test_find_csharp_ls_uses_dotnet_global_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "csharp-ls"
    executable.touch()

    monkeypatch.setattr(
        "lsp_client.clients.csharp_ls._CSHARP_LS_EXECUTABLE", executable
    )
    monkeypatch.setattr("lsp_client.clients.csharp_ls.shutil.which", lambda _name: None)

    assert _find_csharp_ls() == str(executable)


@pytest.mark.asyncio
async def test_install_returns_when_csharp_ls_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    async def run_process(_command: list[str]) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "lsp_client.clients.csharp_ls._find_csharp_ls",
        lambda: "/usr/bin/csharp-ls",
    )
    monkeypatch.setattr("lsp_client.clients.csharp_ls.anyio.run_process", run_process)

    await ensure_csharp_ls_installed()

    assert called is False


@pytest.mark.asyncio
async def test_install_requires_dotnet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("lsp_client.clients.csharp_ls._find_csharp_ls", lambda: None)
    monkeypatch.setattr(
        "lsp_client.clients.csharp_ls.shutil.which", lambda _program: None
    )

    with pytest.raises(ServerInstallationError, match=r"\.NET SDK"):
        await ensure_csharp_ls_installed()


@pytest.mark.asyncio
async def test_install_invokes_dotnet_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    lookups = 0
    commands: list[list[str]] = []

    def find_csharp_ls() -> str | None:
        nonlocal lookups
        lookups += 1
        return None if lookups == 1 else "/home/user/.dotnet/tools/csharp-ls"

    def which(program: str) -> str | None:
        return "/usr/bin/dotnet" if program == "dotnet" else None

    async def run_process(command: list[str]) -> None:
        commands.append(command)

    monkeypatch.setattr("lsp_client.clients.csharp_ls._find_csharp_ls", find_csharp_ls)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.shutil.which", which)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.anyio.run_process", run_process)

    await ensure_csharp_ls_installed()

    assert commands == [["dotnet", "tool", "install", "--global", "csharp-ls"]]


@pytest.mark.asyncio
async def test_install_wraps_dotnet_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def which(program: str) -> str | None:
        return "/usr/bin/dotnet" if program == "dotnet" else None

    async def run_process(command: list[str]) -> None:
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr("lsp_client.clients.csharp_ls._find_csharp_ls", lambda: None)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.shutil.which", which)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.anyio.run_process", run_process)

    with pytest.raises(ServerInstallationError, match="Could not install csharp-ls"):
        await ensure_csharp_ls_installed()


@pytest.mark.asyncio
async def test_install_reports_missing_tool_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def which(program: str) -> str | None:
        return "/usr/bin/dotnet" if program == "dotnet" else None

    async def run_process(_command: list[str]) -> None:
        return

    monkeypatch.setattr("lsp_client.clients.csharp_ls._find_csharp_ls", lambda: None)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.shutil.which", which)
    monkeypatch.setattr("lsp_client.clients.csharp_ls.anyio.run_process", run_process)

    with pytest.raises(ServerInstallationError, match=r"\.dotnet/tools"):
        await ensure_csharp_ls_installed()
