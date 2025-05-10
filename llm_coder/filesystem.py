#!/usr/bin/env python3

import asyncio
import os
import json
import sys
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
import fnmatch
import difflib

# Third-party imports (you may need to install these)
try:
    from pydantic import BaseModel
except ImportError:
    print("Error: pydantic package required. Install with 'pip install pydantic'")
    sys.exit(1)


# Schema definitions
class ReadFileArgs(BaseModel):
    path: str


class ReadMultipleFilesArgs(BaseModel):
    paths: List[str]


class WriteFileArgs(BaseModel):
    path: str
    content: str


class EditOperation(BaseModel):
    oldText: str
    newText: str


class EditFileArgs(BaseModel):
    path: str
    edits: List[EditOperation]
    dryRun: bool = False


class CreateDirectoryArgs(BaseModel):
    path: str


class ListDirectoryArgs(BaseModel):
    path: str


class DirectoryTreeArgs(BaseModel):
    path: str


class MoveFileArgs(BaseModel):
    source: str
    destination: str


class SearchFilesArgs(BaseModel):
    path: str
    pattern: str
    excludePatterns: List[str] = []


class GetFileInfoArgs(BaseModel):
    path: str


class FileInfo(BaseModel):
    size: int
    created: datetime
    modified: datetime
    accessed: datetime
    isDirectory: bool
    isFile: bool
    permissions: str


class TreeEntry(BaseModel):
    name: str
    type: Literal["file", "directory"]
    children: Optional[List["TreeEntry"]] = None


# Path utilities
def normalize_path(p: str) -> str:
    """Normalize a path for consistent handling."""
    return os.path.normpath(p)


def expand_home(filepath: str) -> str:
    """Expand '~' to the user's home directory."""
    if filepath.startswith("~/") or filepath == "~":
        return os.path.join(
            os.path.expanduser("~"), filepath[1:] if filepath.startswith("~") else ""
        )
    return filepath


# Global variables
allowed_directories = []


def initialize_filesystem_settings(directories: List[str]) -> None:
    """ファイルシステム操作が許可されるディレクトリを設定します。"""
    global allowed_directories

    if not directories:
        print(
            "警告: 許可されたディレクトリが指定されていません。ファイルシステム操作は制限されます。",
            file=sys.stderr,
        )
        allowed_directories = []
        return

    valid_directories = []
    for dir_path in directories:
        expanded_dir = expand_home(dir_path)
        abs_dir = os.path.abspath(expanded_dir)
        norm_dir = normalize_path(abs_dir)

        if not os.path.exists(norm_dir):
            print(
                f"警告: ディレクトリ '{dir_path}' (解決後: {norm_dir}) が存在しません。",
                file=sys.stderr,
            )
            continue

        if not os.path.isdir(norm_dir):
            print(
                f"警告: パス '{dir_path}' (解決後: {norm_dir}) はディレクトリではありません。",
                file=sys.stderr,
            )
            continue

        valid_directories.append(norm_dir)

    allowed_directories = valid_directories
    print(
        f"ファイルシステム設定完了。許可ディレクトリ: {allowed_directories}",
        file=sys.stderr,
    )


# Security utilities
async def validate_path(requested_path: str) -> str:
    """
    Validate that a path is within allowed directories and resolve symlinks safely.
    Returns the real path if valid, raises an exception otherwise.
    """
    expanded_path = expand_home(requested_path)
    absolute = os.path.abspath(expanded_path)
    normalized_requested = normalize_path(absolute)

    # Check if path is within allowed directories
    is_allowed = any(
        normalized_requested.startswith(dir) for dir in allowed_directories
    )
    if not is_allowed:
        raise ValueError(
            f"Access denied - path outside allowed directories: {absolute} not in {', '.join(allowed_directories)}"
        )

    # Handle symlinks by checking their real path
    try:
        real_path = os.path.realpath(absolute)
        normalized_real = normalize_path(real_path)
        is_real_path_allowed = any(
            normalized_real.startswith(dir) for dir in allowed_directories
        )
        if not is_real_path_allowed:
            raise ValueError(
                "Access denied - symlink target outside allowed directories"
            )
        return real_path
    except Exception:
        # For new files that don't exist yet, verify parent directory
        parent_dir = os.path.dirname(absolute)
        try:
            real_parent_path = os.path.realpath(parent_dir)
            normalized_parent = normalize_path(real_parent_path)
            is_parent_allowed = any(
                normalized_parent.startswith(dir) for dir in allowed_directories
            )
            if not is_parent_allowed:
                raise ValueError(
                    "Access denied - parent directory outside allowed directories"
                )
            return absolute
        except Exception:
            raise ValueError(f"Parent directory does not exist: {parent_dir}")


# File operation utilities
async def get_file_stats(file_path: str) -> FileInfo:
    """Get detailed file statistics."""
    stats = os.stat(file_path)
    return FileInfo(
        size=stats.st_size,
        created=datetime.fromtimestamp(stats.st_ctime),
        modified=datetime.fromtimestamp(stats.st_mtime),
        accessed=datetime.fromtimestamp(stats.st_atime),
        isDirectory=os.path.isdir(file_path),
        isFile=os.path.isfile(file_path),
        permissions=oct(stats.st_mode)[-3:],
    )


async def search_files(
    root_path: str, pattern: str, exclude_patterns: List[str] = []
) -> List[str]:
    """Recursively search for files matching a pattern."""
    results = []

    async def search(current_path: str):
        entries = os.listdir(current_path)

        for entry in entries:
            full_path = os.path.join(current_path, entry)

            try:
                # Validate each path before processing
                await validate_path(full_path)

                # Check if path matches any exclude pattern
                relative_path = os.path.relpath(full_path, root_path)
                should_exclude = any(
                    fnmatch.fnmatch(
                        relative_path,
                        glob_pattern if "*" in pattern else f"**/{pattern}/**",
                    )
                    for glob_pattern in exclude_patterns
                )

                if should_exclude:
                    continue

                if pattern.lower() in entry.lower():
                    results.append(full_path)

                if os.path.isdir(full_path):
                    await search(full_path)
            except Exception:
                # Skip invalid paths during search
                continue

    await search(root_path)
    return results


# File editing and diffing utilities
def normalize_line_endings(text: str) -> str:
    """Ensure consistent line endings by converting CRLF to LF."""
    return text.replace("\r\n", "\n")


def create_unified_diff(
    original_content: str, new_content: str, filepath: str = "file"
) -> str:
    """Create a unified diff between original and new content."""
    # Ensure consistent line endings for diff
    normalized_original = normalize_line_endings(original_content)
    normalized_new = normalize_line_endings(new_content)

    # Generate diff
    diff_lines = list(
        difflib.unified_diff(
            normalized_original.splitlines(),
            normalized_new.splitlines(),
            fromfile=f"{filepath} (original)",
            tofile=f"{filepath} (modified)",
            lineterm="",
        )
    )

    return "\n".join(diff_lines)


async def apply_file_edits(
    file_path: str, edits: List[dict], dry_run: bool = False
) -> str:
    """Apply edits to a file and return the diff."""
    # Read file content and normalize line endings
    with open(file_path, "r", encoding="utf-8") as f:
        content = normalize_line_endings(f.read())

    # Apply edits sequentially
    modified_content = content
    for edit in edits:
        normalized_old = normalize_line_endings(edit["oldText"])
        normalized_new = normalize_line_endings(edit["newText"])

        # If exact match exists, use it
        if normalized_old in modified_content:
            modified_content = modified_content.replace(normalized_old, normalized_new)
            continue

        # Otherwise, try line-by-line matching with flexibility for whitespace
        old_lines = normalized_old.split("\n")
        content_lines = modified_content.split("\n")
        match_found = False

        for i in range(len(content_lines) - len(old_lines) + 1):
            potential_match = content_lines[i : i + len(old_lines)]

            # Compare lines with normalized whitespace
            is_match = all(
                old_line.strip() == content_line.strip()
                for old_line, content_line in zip(old_lines, potential_match)
            )

            if is_match:
                # Preserve original indentation of first line
                original_indent = ""
                indent_match = potential_match[0].match(r"^\s*")
                if indent_match:
                    original_indent = indent_match.group(0)

                new_lines = []
                for j, line in enumerate(normalized_new.split("\n")):
                    if j == 0:
                        new_lines.append(original_indent + line.lstrip())
                    else:
                        # For subsequent lines, try to preserve relative indentation
                        old_indent = ""
                        new_indent = ""

                        if j < len(old_lines):
                            old_indent_match = old_lines[j].match(r"^\s*")
                            if old_indent_match:
                                old_indent = old_indent_match.group(0)

                        new_indent_match = line.match(r"^\s*")
                        if new_indent_match:
                            new_indent = new_indent_match.group(0)

                        if old_indent and new_indent:
                            relative_indent = len(new_indent) - len(old_indent)
                            new_lines.append(
                                original_indent
                                + " " * max(0, relative_indent)
                                + line.lstrip()
                            )
                        else:
                            new_lines.append(line)

                content_lines[i : i + len(old_lines)] = new_lines
                modified_content = "\n".join(content_lines)
                match_found = True
                break

        if not match_found:
            raise ValueError(f"Could not find exact match for edit:\n{edit['oldText']}")

    # Create unified diff
    diff = create_unified_diff(content, modified_content, file_path)

    # Format diff with appropriate number of backticks
    num_backticks = 3
    while "`" * num_backticks in diff:
        num_backticks += 1
    formatted_diff = f"{'`' * num_backticks}diff\n{diff}\n{'`' * num_backticks}\n\n"

    if not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(modified_content)

    return formatted_diff


async def build_directory_tree(current_path: str) -> List[TreeEntry]:
    """Build a recursive tree structure of directories and files."""
    valid_path = await validate_path(current_path)
    entries = os.listdir(valid_path)
    result = []

    for entry in entries:
        entry_path = os.path.join(valid_path, entry)
        is_dir = os.path.isdir(entry_path)

        entry_data = TreeEntry(
            name=entry,
            type="directory" if is_dir else "file",
            children=[] if is_dir else None,
        )

        if is_dir:
            entry_data.children = await build_directory_tree(entry_path)

        result.append(entry_data)

    return result


# Tool execution functions
async def execute_read_file(arguments: Dict[str, Any]) -> str:
    """ファイルを読み込むツール実行関数"""
    args = ReadFileArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    async with asyncio.to_thread(open, valid_path, "r", encoding="utf-8") as f:
        content = await asyncio.to_thread(f.read)
    return content


async def execute_write_file(arguments: Dict[str, Any]) -> str:
    """ファイルを書き込むツール実行関数"""
    args = WriteFileArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    async with asyncio.to_thread(open, valid_path, "w", encoding="utf-8") as f:
        await asyncio.to_thread(f.write, args.content)
    return f"ファイル '{args.path}' への書き込みに成功しました。"


async def execute_edit_file(arguments: Dict[str, Any]) -> str:
    """ファイルを編集するツール実行関数"""
    args = EditFileArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    # 型変換: EditOperation オブジェクトのリストから辞書のリストへ
    edits_as_dicts = [edit.dict() for edit in args.edits]
    return await apply_file_edits(valid_path, edits_as_dicts, args.dryRun)


async def execute_list_directory(arguments: Dict[str, Any]) -> str:
    """ディレクトリの内容を一覧表示するツール実行関数"""
    args = ListDirectoryArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    entries = await asyncio.to_thread(os.listdir, valid_path)
    formatted = []

    for entry in entries:
        entry_path = os.path.join(valid_path, entry)
        try:
            # 各エントリも検証
            await validate_path(entry_path)
            is_dir = await asyncio.to_thread(os.path.isdir, entry_path)
            formatted.append(f"[DIR] {entry}" if is_dir else f"[FILE] {entry}")
        except ValueError:
            # アクセス不可のエントリはスキップまたは表示
            continue

    return (
        "\n".join(formatted)
        if formatted
        else "ディレクトリは空かアクセス可能なファイルがありません"
    )


async def execute_search_files(arguments: Dict[str, Any]) -> str:
    """ファイルを検索するツール実行関数"""
    args = SearchFilesArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    results = await search_files(valid_path, args.pattern, args.excludePatterns)
    return "\n".join(results) if results else "一致するファイルは見つかりませんでした"


async def execute_create_directory(arguments: Dict[str, Any]) -> str:
    """ディレクトリを作成するツール実行関数"""
    args = CreateDirectoryArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    await asyncio.to_thread(os.makedirs, valid_path, exist_ok=True)
    return f"ディレクトリ '{args.path}' の作成に成功しました"


async def execute_get_file_info(arguments: Dict[str, Any]) -> str:
    """ファイル情報を取得するツール実行関数"""
    args = GetFileInfoArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    info = await get_file_stats(valid_path)
    return "\n".join(f"{key}: {value}" for key, value in info.dict().items())


async def execute_directory_tree(arguments: Dict[str, Any]) -> str:
    """ディレクトリツリーを取得するツール実行関数"""
    args = DirectoryTreeArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

    tree_data = await build_directory_tree(valid_path)
    return json.dumps([entry.dict() for entry in tree_data], indent=2, default=str)


def get_filesystem_tools() -> List[Dict[str, Any]]:
    """ファイルシステム操作ツールのリストを返します"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "ファイルシステムからファイルの内容を読み込みます。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "読み込むファイルのパス",
                        }
                    },
                    "required": ["path"],
                },
            },
            "execute": execute_read_file,
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "ファイルシステムにファイルを書き込みます。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "書き込み先のファイルパス",
                        },
                        "content": {
                            "type": "string",
                            "description": "ファイルに書き込む内容",
                        },
                    },
                    "required": ["path", "content"],
                },
            },
            "execute": execute_write_file,
        },
        {
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "既存ファイルの一部を編集します。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "編集するファイルのパス",
                        },
                        "edits": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "oldText": {
                                        "type": "string",
                                        "description": "置換対象のテキスト",
                                    },
                                    "newText": {
                                        "type": "string",
                                        "description": "新しいテキスト",
                                    },
                                },
                                "required": ["oldText", "newText"],
                            },
                            "description": "適用する編集のリスト",
                        },
                        "dryRun": {
                            "type": "boolean",
                            "description": "TrueならDiffのみ表示し、実際には編集しない",
                            "default": False,
                        },
                    },
                    "required": ["path", "edits"],
                },
            },
            "execute": execute_edit_file,
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "ディレクトリ内のファイルとフォルダをリストアップします。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "リストアップするディレクトリのパス",
                        }
                    },
                    "required": ["path"],
                },
            },
            "execute": execute_list_directory,
        },
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "パターンに一致するファイルを検索します。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "検索を開始するディレクトリのパス",
                        },
                        "pattern": {"type": "string", "description": "検索パターン"},
                        "excludePatterns": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "除外するパターンのリスト",
                        },
                    },
                    "required": ["path", "pattern"],
                },
            },
            "execute": execute_search_files,
        },
        {
            "type": "function",
            "function": {
                "name": "create_directory",
                "description": "新しいディレクトリを作成します。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "作成するディレクトリのパス",
                        }
                    },
                    "required": ["path"],
                },
            },
            "execute": execute_create_directory,
        },
        {
            "type": "function",
            "function": {
                "name": "get_file_info",
                "description": "ファイルやディレクトリの詳細情報を取得します。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "情報を取得するファイルまたはディレクトリのパス",
                        }
                    },
                    "required": ["path"],
                },
            },
            "execute": execute_get_file_info,
        },
        {
            "type": "function",
            "function": {
                "name": "directory_tree",
                "description": "指定されたパスから始まるディレクトリとファイルの再帰的なツリー構造を取得します。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "ツリーのルートディレクトリ",
                        }
                    },
                    "required": ["path"],
                },
            },
            "execute": execute_directory_tree,
        },
    ]
    return tools
