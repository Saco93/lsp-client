from __future__ import annotations

from typing import Final

from .basedpyright import BasedpyrightClient
from .csharp_ls import CsharpLsClient
from .deno import DenoClient
from .gopls import GoplsClient
from .jdtls import JdtlsClient
from .pyrefly import PyreflyClient
from .pyright import PyrightClient
from .rust_analyzer import RustAnalyzerClient
from .ty import TyClient
from .typescript import TypescriptClient

clients: Final = {
    "basedpyright": BasedpyrightClient,
    "csharp_ls": CsharpLsClient,
    "gopls": GoplsClient,
    "pyrefly": PyreflyClient,
    "pyright": PyrightClient,
    "rust_analyzer": RustAnalyzerClient,
    "deno": DenoClient,
    "typescript": TypescriptClient,
    "ty": TyClient,
    "jdtls": JdtlsClient,
}

__all__ = [
    "BasedpyrightClient",
    "CsharpLsClient",
    "DenoClient",
    "GoplsClient",
    "JdtlsClient",
    "PyreflyClient",
    "PyrightClient",
    "RustAnalyzerClient",
    "TyClient",
    "TypescriptClient",
]
