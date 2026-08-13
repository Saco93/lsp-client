"""Command-line interface for common LSP code-analysis operations."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Sequence
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import anyio

from lsp_client.capability.request import (
    WithRequestDefinition,
    WithRequestDocumentSymbol,
    WithRequestHover,
    WithRequestReferences,
    WithRequestRename,
    WithRequestWorkspaceSymbol,
)
from lsp_client.client.abc import Client
from lsp_client.clients import clients
from lsp_client.clients.lang import find_client
from lsp_client.exception import LSPError
from lsp_client.protocol import CapabilityProtocol
from lsp_client.utils.types import Position, lsp_type
from lsp_client.utils.uri import from_local_uri


class ClientSelectionError(RuntimeError):
    """Raised when no registered client matches the requested operation."""


class OperationValidationError(RuntimeError):
    """Raised when an operation would affect a path outside the workspace."""


def _supports_capabilities(
    client_cls: type[Client],
    required_capabilities: Sequence[type[CapabilityProtocol]],
) -> bool:
    return all(
        issubclass(client_cls, capability) for capability in required_capabilities
    )


def create_client(
    path: Path,
    required_capabilities: Sequence[type[CapabilityProtocol]] = (),
) -> Client:
    """Create a matching client that supports all required capabilities."""
    target_path = path.expanduser().resolve()
    if not target_path.exists():
        raise FileNotFoundError(f"Path does not exist: {target_path}")

    target = find_client(target_path)
    if target is None:
        raise ClientSelectionError(
            f"No supported language project found for {target_path}. "
            "Use a source file or directory inside a project with a recognized marker."
        )
    if _supports_capabilities(target.client_cls, required_capabilities):
        return target.client_cls(workspace=target.project_path)

    language_kind = target.client_cls.get_language_config().kind
    for alternative_cls in clients.values():
        config = alternative_cls.get_language_config()
        if config.kind is not language_kind or not _supports_capabilities(
            alternative_cls, required_capabilities
        ):
            continue
        if project_path := config.find_project_root(target_path):
            return alternative_cls(workspace=project_path)

    capability_names = ", ".join(
        capability.__name__ for capability in required_capabilities
    )
    raise ClientSelectionError(
        f"No {language_kind.value} client supports the required capabilities: "
        f"{capability_names}."
    )


def _require_capability(client: Client, capability_name: str) -> ClientSelectionError:
    return ClientSelectionError(
        f"{type(client).__name__} does not support the {capability_name} capability."
    )


async def analyze_symbol(file_path: Path, line: int, character: int) -> None:
    """Print hover, definition, and reference information for a symbol."""
    source = file_path.expanduser().resolve()

    async with create_client(
        source,
        (WithRequestHover, WithRequestDefinition, WithRequestReferences),
    ) as client:
        position = Position(line, character)

        if not isinstance(client, WithRequestHover):
            raise _require_capability(client, "hover")
        hover = await client.request_hover(file_path=source, position=position)
        print("\n📝 Hover Information:")
        if hover:
            print(f"Kind: {hover.kind.value}")
            print(f"Value: {hover.value}")

        if not isinstance(client, WithRequestDefinition):
            raise _require_capability(client, "definition")
        definitions = await client.request_definition(source, position)
        print("\n🎯 Definition:")
        if definitions:
            locations = (
                (definitions,)
                if isinstance(definitions, lsp_type.Location)
                else definitions
            )
            for definition in locations:
                if isinstance(definition, lsp_type.Location):
                    uri = definition.uri
                    range_ = definition.range
                else:
                    uri = definition.target_uri
                    range_ = definition.target_selection_range
                target_file = client.from_uri(uri)
                print(f"  {target_file}:{range_.start.line}:{range_.start.character}")

        if not isinstance(client, WithRequestReferences):
            raise _require_capability(client, "references")
        references = await client.request_references(
            file_path=source,
            position=position,
            include_declaration=False,
        )
        print("\n🔗 References:")
        if references:
            for reference in references:
                target_file = client.from_uri(reference.uri)
                print(
                    f"  {target_file}:{reference.range.start.line}:"
                    f"{reference.range.start.character}"
                )


async def find_document_symbols(file_path: Path) -> None:
    """Print symbols declared in one source file."""
    source = file_path.expanduser().resolve()

    async with create_client(source, (WithRequestDocumentSymbol,)) as client:
        if not isinstance(client, WithRequestDocumentSymbol):
            raise _require_capability(client, "document symbol")
        symbols = await client.request_document_symbol(file_path=source)

        if not symbols:
            print("No symbols found")
            return

        print(f"\n📚 Document Symbols in {source}:")
        for symbol in symbols:
            if isinstance(symbol, lsp_type.DocumentSymbol):
                location = f"{symbol.range.start.line}:{symbol.range.start.character}"
            else:
                location = (
                    f"{client.from_uri(symbol.location.uri)}:"
                    f"{symbol.location.range.start.line}:"
                    f"{symbol.location.range.start.character}"
                )
            print(f"  {symbol.kind.name:15} {symbol.name:30} @ {location}")


async def find_workspace_symbols(query: str, project_path: Path) -> None:
    """Search for symbols in the workspace selected by a source or project path."""
    workspace = project_path.expanduser().resolve()

    async with create_client(workspace, (WithRequestWorkspaceSymbol,)) as client:
        if not isinstance(client, WithRequestWorkspaceSymbol):
            raise _require_capability(client, "workspace symbol")
        symbols = await client.request_workspace_symbol_list(query=query)

        if not symbols:
            print(f"No symbols found matching '{query}'")
            return

        print(f"\n🔍 Workspace Symbols matching '{query}':")
        for symbol in symbols:
            location = symbol.location
            target_file = client.from_uri(location.uri)
            if isinstance(location, lsp_type.Location):
                range_info = (
                    f"{location.range.start.line}:{location.range.start.character}"
                )
                print(
                    f"  {symbol.kind.name:15} {symbol.name:30} "
                    f"@ {target_file}:{range_info}"
                )
            else:
                print(f"  {symbol.kind.name:15} {symbol.name:30} @ {target_file}")


def _print_text_edits(
    client: Client,
    uri: str,
    text_edits: Sequence[
        lsp_type.TextEdit | lsp_type.AnnotatedTextEdit | lsp_type.SnippetTextEdit
    ],
) -> None:
    target_file = client.from_uri(uri)
    print(f"\n  📄 {target_file}: {len(text_edits)} changes")
    for edit in text_edits:
        start = edit.range.start
        end = edit.range.end
        new_text = (
            edit.snippet.value
            if isinstance(edit, lsp_type.SnippetTextEdit)
            else edit.new_text
        )
        print(
            f"    Line {start.line}:{start.character}-"
            f"{end.line}:{end.character} → '{new_text}'"
        )


def _print_workspace_edit(client: Client, edit: lsp_type.WorkspaceEdit) -> None:
    if edit.document_changes:
        for change in edit.document_changes:
            match change:
                case lsp_type.TextDocumentEdit():
                    _print_text_edits(
                        client,
                        change.text_document.uri,
                        change.edits,
                    )
                case lsp_type.CreateFile():
                    print(f"\n  Create file: {client.from_uri(change.uri)}")
                case lsp_type.RenameFile():
                    print(
                        f"\n  Rename file: {client.from_uri(change.old_uri)} → "
                        f"{client.from_uri(change.new_uri)}"
                    )
                case lsp_type.DeleteFile():
                    print(f"\n  Delete file: {client.from_uri(change.uri)}")
    elif edit.changes:
        for uri, text_edits in edit.changes.items():
            _print_text_edits(client, uri, text_edits)


def _iter_workspace_edit_uris(edit: lsp_type.WorkspaceEdit) -> Iterator[str]:
    if edit.document_changes:
        for change in edit.document_changes:
            match change:
                case lsp_type.TextDocumentEdit():
                    yield change.text_document.uri
                case lsp_type.CreateFile() | lsp_type.DeleteFile():
                    yield change.uri
                case lsp_type.RenameFile():
                    yield change.old_uri
                    yield change.new_uri
    elif edit.changes:
        yield from edit.changes


def _validate_workspace_edit_paths(
    client: Client, edit: lsp_type.WorkspaceEdit
) -> None:
    workspace_roots = [
        folder.path.resolve() for folder in client.get_workspace().values()
    ]
    for uri in _iter_workspace_edit_uris(edit):
        path = from_local_uri(uri).resolve()
        if not any(path.is_relative_to(root) for root in workspace_roots):
            raise OperationValidationError(
                f"Refusing to modify {path} because it is outside the workspace."
            )


async def rename_symbol(
    file_path: Path,
    line: int,
    character: int,
    new_name: str,
    apply_changes: bool,
) -> None:
    """Preview a symbol rename and optionally apply the returned workspace edit."""
    source = file_path.expanduser().resolve()

    async with create_client(source, (WithRequestRename,)) as client:
        if not isinstance(client, WithRequestRename):
            raise _require_capability(client, "rename")

        edits = await client.request_rename_edits(
            file_path=source,
            position=Position(line, character),
            new_name=new_name,
        )
        if edits is None:
            print("❌ Rename not possible at this position")
            return

        print(f"\n📝 Renaming to '{new_name}' will affect:")
        _print_workspace_edit(client, edits)

        if not apply_changes:
            print(
                "\nPreview only; no files were changed. Pass --apply to apply these edits."
            )
            return

        _validate_workspace_edit_paths(client, edits)
        print("\n✅ Applying rename...")
        await client.apply_workspace_edit(edits)
        print("✅ Rename completed successfully")


def _package_version() -> str:
    try:
        return version("lsp-client")
    except PackageNotFoundError:
        return "unknown"


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="lsp-client",
        description="Run common semantic code operations through LSP.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_package_version()}",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    analyze_parser = commands.add_parser(
        "analyze",
        help="show hover, definition, and references for a symbol",
    )
    analyze_parser.add_argument("file", type=Path)
    analyze_parser.add_argument(
        "line", type=_non_negative_int, help="zero-based line number"
    )
    analyze_parser.add_argument(
        "character", type=_non_negative_int, help="zero-based character offset"
    )

    symbols_parser = commands.add_parser("symbols", help="find code symbols")
    symbol_commands = symbols_parser.add_subparsers(
        dest="symbols_command", required=True
    )
    document_parser = symbol_commands.add_parser(
        "document", help="list symbols in one file"
    )
    document_parser.add_argument("file", type=Path)
    workspace_parser = symbol_commands.add_parser(
        "workspace", help="search symbols in a workspace"
    )
    workspace_parser.add_argument("query")
    workspace_parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=Path.cwd(),
        help="source or project path used to select the workspace (default: current directory)",
    )

    rename_parser = commands.add_parser(
        "rename", help="preview a symbol rename and optionally apply it"
    )
    rename_parser.add_argument("file", type=Path)
    rename_parser.add_argument(
        "line", type=_non_negative_int, help="zero-based line number"
    )
    rename_parser.add_argument(
        "character", type=_non_negative_int, help="zero-based character offset"
    )
    rename_parser.add_argument("new_name")
    rename_parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed edits; the default is preview only",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its process exit code."""
    args = build_parser().parse_args(argv)

    try:
        match args.command:
            case "analyze":
                anyio.run(analyze_symbol, args.file, args.line, args.character)
            case "symbols":
                match args.symbols_command:
                    case "document":
                        anyio.run(find_document_symbols, args.file)
                    case "workspace":
                        anyio.run(find_workspace_symbols, args.query, args.path)
            case "rename":
                anyio.run(
                    rename_symbol,
                    args.file,
                    args.line,
                    args.character,
                    args.new_name,
                    args.apply,
                )
    except (
        AssertionError,
        ClientSelectionError,
        ExceptionGroup,
        LSPError,
        OperationValidationError,
        OSError,
        TimeoutError,
        ValueError,
    ) as error:
        print(f"lsp-client: error: {error}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
