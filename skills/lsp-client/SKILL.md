---
name: lsp-client
description: Semantic code analysis via LSP for C#, Python, TypeScript/JavaScript, Go, Rust, Java, and Deno projects. Navigate definitions, references, and implementations; inspect hover information and symbols; search workspaces; and perform language-aware refactoring. Use when exploring unfamiliar codebases or safely renaming code.
---

# LSP Client

Semantic code analysis using Language Server Protocol (LSP) clients. Provides language-aware code navigation, symbol search, and safe refactoring capabilities.

## Installation

The Skill requires the `lsp-client` CLI on `PATH`. Install the published package with:

```bash
uv tool install lsp-client
```

For a local checkout or fork, use an editable tool installation so source changes become available immediately:

```bash
uv tool install --editable /path/to/lsp-client
```

Confirm the installation:

```bash
lsp-client --version
```

Language servers are separate runtime dependencies. See `references/language_servers.md` for the server required by each language.

## Quick Start

Three ways to use the library and CLI:

### 1. Use Pre-built Language Clients

```python
import anyio
from pathlib import Path
from lsp_client import Position
from lsp_client.clients.pyright import PyrightClient

async def main():
    workspace = Path.cwd()
    
    async with PyrightClient(workspace=workspace) as client:
        definitions = await client.request_definition_locations(
            file_path="src/main.py",
            position=Position(line=10, character=5)
        )
        
        for def_loc in definitions:
            file = client.from_uri(def_loc.uri)
            print(f"Definition at {file}:{def_loc.range.start.line}")

anyio.run(main)
```

### 2. Create Custom Client with Selected Capabilities

See `scripts/custom_client_template.py` for a complete template.

Key pattern - inherit from capability mixins:

```python
from attrs import define
from lsp_client.clients.base import PythonClientBase
from lsp_client.capability.request import (
    WithRequestHover,
    WithRequestDefinition,
    WithRequestReferences,
)

@define
class MyClient(
    PythonClientBase,
    WithRequestHover,
    WithRequestDefinition,
    WithRequestReferences,
):
    ...
```

### 3. Use the CLI

Run semantic operations without writing Python code:

```bash
# Analyze symbol at a zero-based position
lsp-client analyze src/main.py 10 5

# Find all symbols in one file
lsp-client symbols document src/main.py

# Search workspace symbols; pass a source path in mixed-language repositories
lsp-client symbols workspace MyClass src/Program.cs

# Preview a rename without changing files
lsp-client rename src/main.py 10 5 new_name

# Apply the displayed rename edits
lsp-client rename src/main.py 10 5 new_name --apply
```

## Common Workflows

### Exploring Unfamiliar Codebase

**Task**: Understand how a function is used across the project

**Approach**:
1. Find definition: `client.request_definition_locations()`
2. Find all references: `client.request_references()`
3. Get type info: `client.request_hover()`

**Command**: `lsp-client analyze <file> <line> <character>`

### Safe Refactoring

**Task**: Rename a symbol across the entire workspace

**Approach**:
1. Preview changes: `client.request_rename_edits()` 
2. Review affected files
3. Apply: `client.apply_workspace_edit()`

**Command**: `lsp-client rename <file> <line> <character> <new_name>`

### Symbol Search

**Task**: Find all classes/functions matching a pattern

**Approach**:
1. Workspace-wide: `client.request_workspace_symbol_list(query="MyClass")`
2. File-specific: `client.request_document_symbol_list(file_path=...)`

**Commands**:
- `lsp-client symbols workspace <query> [source_or_project_path]`
- `lsp-client symbols document <file>`

## Available Clients

See `references/language_servers.md` for full list.

Quick reference:
- **Python**: `PyrightClient`, `PyreflyClient`, `BasedpyrightClient`, `TyClient`
- **Rust**: `RustAnalyzerClient`
- **TypeScript/JS**: `TypescriptClient`, `DenoClient`
- **Go**: `GoplsClient`
- **C#**: `CsharpLsClient`
- **Java**: `JdtlsClient`

All clients support both local (subprocess) and container (Docker) modes. The CLI automatically selects a client from the source suffix, project markers, and required capabilities, including `.sln`, `.slnx`, and `.csproj` for C#. For workspace symbol searches in mixed-language repositories, pass a source file or project path from the intended language workspace.

## Capability System

The library uses capability mixins to compose exactly the features needed.

### Selecting Capabilities

See `references/capabilities.md` for complete list.

Common combinations:

**Basic navigation**:
- `WithRequestDefinition`
- `WithRequestReferences`
- `WithRequestHover`

**IDE-like features**:
- Add `WithRequestCompletion`
- Add `WithRequestSignatureHelp`
- Add `WithRequestCodeAction`

**Symbol search**:
- `WithRequestDocumentSymbol` (file-level)
- `WithRequestWorkspaceSymbol` (project-wide)

**Refactoring**:
- `WithRequestRename`
- `WithRequestCodeAction`
- `WithRequestWorkspaceEdit`

### Why Capability Mixins?

1. **Type safety**: Only methods for registered capabilities exist
2. **Automatic negotiation**: Client tells server what it supports
3. **Zero boilerplate**: No manual capability checking
4. **Composability**: Mix exactly what you need

## Local vs Container Servers

Every client supports dual server backends:

### Local Server (Subprocess)
```python
from lsp_client.clients.pyright import PyrightClient

async with PyrightClient() as client:
    # Uses local pyright-langserver if available
    ...
```

**Pros**: Fast startup, direct file access  
**Cons**: Requires server installed locally

### Container Server (Docker)
```python
from lsp_client.clients.pyright import PyrightClient, PyrightContainerServer

async with PyrightClient(server=PyrightContainerServer()) as client:
    # Uses ghcr.io/lsp-client/pyright:latest
    ...
```

**Pros**: Zero installation, consistent environment  
**Cons**: Docker overhead, path translation

### Automatic Fallback

If no server specified, library tries:
1. Explicit `server=` argument (if provided)
2. Local installation
3. Container fallback
4. Auto-install hook (if defined)

## Key Concepts

### Position

LSP uses 0-indexed line and character positions:

```python
from lsp_client import Position

# Line 10, character 5 (0-indexed)
pos = Position(line=10, character=5)
```

### URI vs File Path

LSP servers work with URIs. The client handles conversion:

```python
# Server returns URI
location = await client.request_definition_locations(...)

# Convert back to file path
file_path = client.from_uri(location.uri)
```

### Async Context Manager

Always use `async with` to ensure proper cleanup:

```python
async with Client(...) as client:
    # Client initialized, server running
    result = await client.request_hover(...)
# Server automatically shut down
```

## Advanced Features

### Configuration Management

Clients come with sensible defaults. Override as needed:

```python
@define
class MyClient(PyrightClient):
    def create_default_config(self):
        return {
            "python": {
                "analysis": {
                    "typeCheckingMode": "strict",
                }
            }
        }
```

### Server Lifecycle Hooks

Customize server behavior with hooks:

```python
from lsp_client.server.local import LocalServer

@define
class CustomServer(LocalServer):
    async def setup(self, workspace):
        # Before server starts
        ...
    
    async def on_started(self, workspace, sender):
        # After server ready
        ...
    
    async def on_shutdown(self):
        # Before cleanup
        ...
```

See library's `examples/custom_hooks.py` for details.

## Troubleshooting

### Server Not Found

**Symptom**: "Could not find language server"

**Solution**: Either install locally or use container:
```python
from lsp_client.clients.pyright import PyrightContainerServer

client = PyrightClient(server=PyrightContainerServer())
```

Install the CLI with `uv tool install lsp-client`. For C#, also install .NET SDK 10 or later and run:

```bash
dotnet tool install --global csharp-ls
```

### Path Translation Issues

When using containers, always work with workspace-relative paths:

```python
# Good
await client.request_hover(file_path="src/main.py", ...)

# Bad (absolute paths won't translate correctly)
await client.request_hover(file_path="/Users/me/project/src/main.py", ...)
```

## Resources

### CLI
- `lsp-client analyze` - Hover, definition, and references for a symbol
- `lsp-client symbols document` - Document symbol listing
- `lsp-client symbols workspace` - Workspace symbol search
- `lsp-client rename` - Preview rename refactoring; apply only with `--apply`

### Scripts
- `custom_client_template.py` - Template for creating custom clients

### References
- `capabilities.md` - Complete list of available LSP capabilities
- `language_servers.md` - Supported language servers and selection guide
