from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from lsp_client import cli
from lsp_client.capability.request import WithRequestRename
from lsp_client.clients.basedpyright import BasedpyrightClient
from lsp_client.clients.csharp_ls import CsharpLsClient
from lsp_client.utils.types import lsp_type


def test_create_client_selects_workspace_from_source(tmp_path: Path) -> None:
    (tmp_path / "App.csproj").touch()
    source = tmp_path / "Program.cs"
    source.touch()

    client = cli.create_client(source)

    assert isinstance(client, CsharpLsClient)
    assert client.get_workspace()["__root__"].path == tmp_path


def test_create_client_selects_alternative_with_required_capability(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").touch()
    source = tmp_path / "main.py"
    source.touch()

    client = cli.create_client(source, (WithRequestRename,))

    assert isinstance(client, BasedpyrightClient)
    assert client.get_workspace()["__root__"].path == tmp_path


def test_create_client_rejects_missing_path(tmp_path: Path) -> None:
    source = tmp_path / "missing.cs"

    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        cli.create_client(source)


def test_create_client_rejects_unknown_project(tmp_path: Path) -> None:
    with pytest.raises(cli.ClientSelectionError, match="No supported language"):
        cli.create_client(tmp_path)


def test_parser_accepts_document_symbols() -> None:
    args = cli.build_parser().parse_args(["symbols", "document", "Program.cs"])

    assert args.command == "symbols"
    assert args.symbols_command == "document"
    assert args.file == Path("Program.cs")


def test_parser_rejects_negative_position() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["analyze", "Program.cs", "-1", "2"])


def test_main_dispatches_workspace_symbols(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    def run(function: Callable[..., Any], *args: Any) -> None:
        calls.append((function, args))

    monkeypatch.setattr(cli.anyio, "run", run)

    result = cli.main(["symbols", "workspace", "Widget", str(tmp_path)])

    assert result == 0
    assert calls == [(cli.find_workspace_symbols, ("Widget", tmp_path))]


def test_main_rename_defaults_to_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    def run(function: Callable[..., Any], *args: Any) -> None:
        calls.append((function, args))

    monkeypatch.setattr(cli.anyio, "run", run)

    result = cli.main(["rename", "Program.cs", "1", "2", "Renamed"])

    assert result == 0
    assert calls == [(cli.rename_symbol, (Path("Program.cs"), 1, 2, "Renamed", False))]


def test_main_rename_supports_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    def run(function: Callable[..., Any], *args: Any) -> None:
        calls.append((function, args))

    monkeypatch.setattr(cli.anyio, "run", run)

    result = cli.main(["rename", "Program.cs", "1", "2", "Renamed", "--apply"])

    assert result == 0
    assert calls == [(cli.rename_symbol, (Path("Program.cs"), 1, 2, "Renamed", True))]


def test_main_reports_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def run(_function: Callable[..., Any], *_args: Any) -> None:
        raise TimeoutError("server timed out")

    monkeypatch.setattr(cli.anyio, "run", run)

    result = cli.main(["analyze", "Program.cs", "1", "2"])

    assert result == 1
    assert capsys.readouterr().err == "lsp-client: error: server timed out\n"


def test_workspace_edit_uri_iteration_includes_resource_operations(
    tmp_path: Path,
) -> None:
    original = tmp_path / "old.cs"
    renamed = tmp_path / "new.cs"
    created = tmp_path / "created.cs"
    deleted = tmp_path / "deleted.cs"
    edit = lsp_type.WorkspaceEdit(
        document_changes=[
            lsp_type.RenameFile(old_uri=original.as_uri(), new_uri=renamed.as_uri()),
            lsp_type.CreateFile(uri=created.as_uri()),
            lsp_type.DeleteFile(uri=deleted.as_uri()),
        ]
    )

    assert list(cli._iter_workspace_edit_uris(edit)) == [
        original.as_uri(),
        renamed.as_uri(),
        created.as_uri(),
        deleted.as_uri(),
    ]


def test_workspace_edit_validation_rejects_path_outside_workspace(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "App.csproj").touch()
    source = workspace / "Program.cs"
    source.touch()
    client = cli.create_client(source)
    edit = lsp_type.WorkspaceEdit(
        document_changes=[lsp_type.DeleteFile(uri=(tmp_path / "outside.cs").as_uri())]
    )

    with pytest.raises(cli.OperationValidationError, match="outside the workspace"):
        cli._validate_workspace_edit_paths(client, edit)
