from __future__ import annotations

import os
import shutil
from functools import partial
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any, override

import anyio
from attrs import define
from loguru import logger

from lsp_client.capability.diagnostic import (
    WithDocumentDiagnostic,
    WithWorkspaceDiagnostic,
)
from lsp_client.capability.notification import WithNotifyDidChangeConfiguration
from lsp_client.capability.request import (
    WithRequestCallHierarchy,
    WithRequestCodeAction,
    WithRequestCompletion,
    WithRequestDefinition,
    WithRequestDocumentSymbol,
    WithRequestHover,
    WithRequestImplementation,
    WithRequestInlayHint,
    WithRequestReferences,
    WithRequestRename,
    WithRequestSignatureHelp,
    WithRequestTypeDefinition,
    WithRequestTypeHierarchy,
    WithRequestWorkspaceSymbol,
)
from lsp_client.capability.server_notification import (
    WithReceiveLogMessage,
    WithReceiveLogTrace,
    WithReceivePublishDiagnostics,
    WithReceiveShowMessage,
)
from lsp_client.capability.server_request import (
    WithRespondConfigurationRequest,
    WithRespondInlayHintRefresh,
    WithRespondShowDocumentRequest,
    WithRespondShowMessageRequest,
    WithRespondWorkspaceFoldersRequest,
)
from lsp_client.clients.base import CSharpClientBase
from lsp_client.server import DefaultServers, ServerInstallationError
from lsp_client.server.container import ContainerServer
from lsp_client.server.local import LocalServer
from lsp_client.utils.types import lsp_type

CsharpLsContainerServer = partial(
    ContainerServer, image="ghcr.io/lsp-client/csharp-ls:latest"
)

_DOTNET_GLOBAL_TOOLS = Path.home() / ".dotnet" / "tools"
_CSHARP_LS_EXECUTABLE = _DOTNET_GLOBAL_TOOLS / (
    "csharp-ls.exe" if os.name == "nt" else "csharp-ls"
)


def _find_csharp_ls() -> str | None:
    if executable := shutil.which("csharp-ls"):
        return executable
    if _CSHARP_LS_EXECUTABLE.is_file():
        return str(_CSHARP_LS_EXECUTABLE)
    return None


def _local_server_environment() -> dict[str, str]:
    env = dict(os.environ)
    current_path = env.get("PATH")
    env["PATH"] = (
        f"{_DOTNET_GLOBAL_TOOLS}{os.pathsep}{current_path}"
        if current_path
        else str(_DOTNET_GLOBAL_TOOLS)
    )
    return env


async def ensure_csharp_ls_installed() -> None:
    if _find_csharp_ls():
        return

    if not shutil.which("dotnet"):
        raise ServerInstallationError(
            "Could not install csharp-ls because the .NET SDK is not available. "
            "Install .NET 10 or later, then run "
            "'dotnet tool install --global csharp-ls'."
        )

    logger.warning("csharp-ls not found, attempting to install it as a .NET tool...")

    try:
        await anyio.run_process(["dotnet", "tool", "install", "--global", "csharp-ls"])
    except CalledProcessError as e:
        raise ServerInstallationError(
            "Could not install csharp-ls. Install it manually with "
            "'dotnet tool install --global csharp-ls'. See "
            "https://github.com/razzmatazz/csharp-language-server for details."
        ) from e

    if not _find_csharp_ls():
        raise ServerInstallationError(
            "The csharp-ls installation completed, but its executable was not found "
            f"in PATH or {_DOTNET_GLOBAL_TOOLS}."
        )

    logger.info("Successfully installed csharp-ls as a global .NET tool")


CsharpLsLocalServer = partial(
    LocalServer,
    program=_find_csharp_ls() or "csharp-ls",
    args=[],
    env=_local_server_environment(),
    ensure_installed=ensure_csharp_ls_installed,
)


@define
class CsharpLsClient(
    CSharpClientBase,
    WithNotifyDidChangeConfiguration,
    WithDocumentDiagnostic,
    WithWorkspaceDiagnostic,
    WithRequestCallHierarchy,
    WithRequestCodeAction,
    WithRequestCompletion,
    WithRequestDefinition,
    WithRequestDocumentSymbol,
    WithRequestHover,
    WithRequestImplementation,
    WithRequestInlayHint,
    WithRequestReferences,
    WithRequestRename,
    WithRequestSignatureHelp,
    WithRequestTypeDefinition,
    WithRequestTypeHierarchy,
    WithRequestWorkspaceSymbol,
    WithReceiveLogMessage,
    WithReceiveLogTrace,
    WithReceivePublishDiagnostics,
    WithReceiveShowMessage,
    WithRespondConfigurationRequest,
    WithRespondInlayHintRefresh,
    WithRespondShowDocumentRequest,
    WithRespondShowMessageRequest,
    WithRespondWorkspaceFoldersRequest,
):
    """
    - Language: C#
    - Homepage: https://github.com/razzmatazz/csharp-language-server
    - Github: https://github.com/razzmatazz/csharp-language-server
    - Installation: ``dotnet tool install --global csharp-ls``
    """

    @classmethod
    @override
    def create_default_servers(cls) -> DefaultServers:
        return DefaultServers(
            local=CsharpLsLocalServer(),
            container=CsharpLsContainerServer(),
        )

    @override
    def check_server_compatibility(self, info: lsp_type.ServerInfo | None) -> None:
        return

    @override
    def create_default_config(self) -> dict[str, Any] | None:
        return {
            "csharp": {
                "logLevel": "info",
                "applyFormattingOptions": False,
                "analyzersEnabled": False,
                "useMetadataUris": False,
                "razorSupport": False,
            }
        }
