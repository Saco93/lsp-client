"""
Language-specific configuration for LSP clients.

Provides LanguageConfig for defining language properties including file suffixes,
project markers, and project root detection logic.
"""

from __future__ import annotations

from pathlib import Path

from attrs import Factory, frozen

from lsp_client.utils.workspace import lsp_type


@frozen
class LanguageConfig:
    """Configuration for a programming language in the LSP client."""

    kind: lsp_type.LanguageKind
    """The kind of programming language."""

    suffixes: list[str]
    """File suffixes associated with the language."""

    project_files: list[str]
    """Files that indicate the root of a project for this language."""

    prioritized_project_file_groups: list[list[str]] = Factory(list)
    """Marker groups checked by priority; distance wins within each group."""

    exclude_files: list[str] = Factory(list)
    """Files that indicate a directory should not be considered a project root for this language."""

    prioritize_project_files: bool = False
    """Whether marker order takes priority over distance from the input path."""

    def is_project_root(self, path: Path) -> bool:
        """Check if the given path is a project root for this language.

        A directory is considered a project root if it:
        1. Contains at least one of the patterns in :attr:`project_files`.
        2. Does NOT contain any of the patterns in :attr:`exclude_files`.
        """
        if not path.is_dir():
            return False

        if any(
            next(path.glob(pattern), None) is not None for pattern in self.exclude_files
        ):
            return False

        return any(
            next(path.glob(pattern), None) is not None for pattern in self.project_files
        )

    def find_project_root(self, path: Path) -> Path | None:
        """Determine the project root for the given path.

        By default, the project root is the nearest ancestor directory
        (including the directory of ``path``) that is a project root according
        to :meth:`is_project_root`. If :attr:`prioritize_project_files` is true,
        marker patterns are checked in their configured order before distance
        is considered. If :attr:`prioritized_project_file_groups` is configured,
        group order takes priority while the nearest marker wins within a group.

        Parameters
        ----------
        path:
            A file or directory path for which to locate the project root.
            If a file is given, it must have a suffix listed in
            :attr:`suffixes` or ``None`` is returned.

        Returns
        -------
        Path | None
            The path to the detected project root directory, or ``None`` if
            no suitable project root can be found.
        """
        if path.is_file():
            if not any(path.name.endswith(suffix) for suffix in self.suffixes):
                return None
            path = path.parent

        candidates = [path, *path.parents]
        if self.prioritized_project_file_groups:
            for project_file_group in self.prioritized_project_file_groups:
                for candidate in candidates:
                    if any(
                        next(candidate.glob(pattern), None) is not None
                        for pattern in self.exclude_files
                    ):
                        continue
                    if any(
                        next(candidate.glob(project_file), None) is not None
                        for project_file in project_file_group
                    ):
                        return candidate
            return None

        if self.prioritize_project_files:
            for project_file in self.project_files:
                for candidate in candidates:
                    if any(
                        next(candidate.glob(pattern), None) is not None
                        for pattern in self.exclude_files
                    ):
                        continue
                    if next(candidate.glob(project_file), None) is not None:
                        return candidate
            return None

        for candidate in candidates:
            if self.is_project_root(candidate):
                return candidate

        return None
