#!/usr/bin/env python3

import asyncio
import os
import json
import sys
from typing import List, Dict, Any, Optional, Literal
from datetime import datetime
import fnmatch
import difflib
import structlog  # structlog をインポート

# Third-party imports (you may need to install these)
try:
    from pydantic import BaseModel
except ImportError:
    print("Error: pydantic package required. Install with 'pip install pydantic'")
    sys.exit(1)

# structlog の基本的な設定
logger = structlog.get_logger(__name__)


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
allowed_directories: list[str] = []


def initialize_filesystem_settings(directories: list[str]) -> None:
    """ファイルシステム操作が許可されるディレクトリを設定します。"""
    global allowed_directories

    if not directories:
        logger.warning(
            "許可されたディレクトリが指定されていません。ファイルシステム操作は制限されます。"
        )
        allowed_directories = []
        return

    valid_directories = []
    for dir_path in directories:
        expanded_dir = expand_home(dir_path)
        abs_dir = os.path.abspath(expanded_dir)
        norm_dir = normalize_path(abs_dir)

        if not os.path.exists(norm_dir):
            logger.warning(
                "ディレクトリが存在しません。",
                path=dir_path,
                resolved_path=norm_dir,
            )
            continue

        if not os.path.isdir(norm_dir):
            logger.warning(
                "パスはディレクトリではありません。",
                path=dir_path,
                resolved_path=norm_dir,
            )
            continue

        valid_directories.append(norm_dir)

    allowed_directories = valid_directories
    logger.info(
        "ファイルシステム設定完了。",
        allowed_directories=allowed_directories,
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


async def get_gitignore_patterns(directory: str) -> List[str]:
    """指定されたディレクトリの .gitignore ファイルからパターンを読み込みます。"""
    gitignore_path = os.path.join(directory, ".gitignore")
    patterns = []
    if await asyncio.to_thread(os.path.exists, gitignore_path):
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line and not stripped_line.startswith("#"):
                        patterns.append(stripped_line)
        except Exception as e:
            logger.warning(
                "Error reading .gitignore file", path=gitignore_path, error=e
            )
    return patterns


async def search_files(
    root_path: str,
    pattern: str,
    exclude_patterns: List[str] = [],
    exact_match: bool = False,
) -> List[str]:
    """Recursively search for files matching a pattern."""
    results = []

    async def search(current_path: str, current_exclude_patterns: List[str]):
        combined_exclude_patterns = current_exclude_patterns

        try:
            entries = await asyncio.to_thread(os.listdir, current_path)
        except OSError:
            return

        for entry in entries:
            full_path = os.path.join(current_path, entry)
            relative_path_to_root = os.path.relpath(full_path, root_path)

            try:
                should_exclude = any(
                    fnmatch.fnmatch(relative_path_to_root, p)
                    or fnmatch.fnmatch(entry, p)
                    for p in combined_exclude_patterns
                )

                if should_exclude:
                    continue

                await validate_path(full_path)

                if await asyncio.to_thread(os.path.isfile, full_path):
                    if exact_match:
                        if entry.lower() == pattern.lower():
                            results.append(full_path)
                    else:
                        if pattern.lower() in entry.lower():
                            results.append(full_path)

                if await asyncio.to_thread(os.path.isdir, full_path):
                    await search(full_path, combined_exclude_patterns)
            except ValueError:
                continue
            except Exception as e:
                logger.debug(
                    "Error processing path during search", path=full_path, error=str(e)
                )
                continue

    await search(root_path, exclude_patterns)
    return results


# File editing and diffing utilities
def normalize_line_endings(text: str) -> str:
    """Ensure consistent line endings by converting CRLF to LF."""
    return text.replace("\r\n", "\n")


def create_unified_diff(
    original_content: str, new_content: str, filepath: str = "file"
) -> str:
    """Create a unified diff between original and new content."""
    normalized_original = normalize_line_endings(original_content)
    normalized_new = normalize_line_endings(new_content)

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
    with open(file_path, "r", encoding="utf-8") as f:
        content = normalize_line_endings(f.read())

    modified_content = content
    for edit in edits:
        normalized_old = normalize_line_endings(edit["oldText"])
        normalized_new = normalize_line_endings(edit["newText"])

        if normalized_old in modified_content:
            modified_content = modified_content.replace(normalized_old, normalized_new)
            continue

        old_lines = normalized_old.split("\n")
        content_lines = modified_content.split("\n")
        match_found = False

        for i in range(len(content_lines) - len(old_lines) + 1):
            potential_match = content_lines[i : i + len(old_lines)]

            is_match = all(
                old_line.strip() == content_line.strip()
                for old_line, content_line in zip(old_lines, potential_match)
            )

            if is_match:
                original_indent = ""
                indent_match = potential_match[0].match(r"^\s*")
                if indent_match:
                    original_indent = indent_match.group(0)

                new_lines = []
                for j, line in enumerate(normalized_new.split("\n")):
                    if j == 0:
                        new_lines.append(original_indent + line.lstrip())
                    else:
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

    diff = create_unified_diff(content, modified_content, file_path)

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
    try:
        valid_path = await validate_path(args.path)
        f = await asyncio.to_thread(open, valid_path, "r", encoding="utf-8")
        try:
            content = await asyncio.to_thread(f.read)
            return content
        finally:
            await asyncio.to_thread(f.close)
    except FileNotFoundError:
        logger.info(
            f"File not found: {args.path}. Searching for alternatives in allowed directories."
        )
        filename_to_search = os.path.basename(args.path)
        candidate_files = set()

        for allowed_dir in allowed_directories:
            current_exclude_patterns = await get_gitignore_patterns(allowed_dir)

            try:
                validated_allowed_dir = await validate_path(allowed_dir)
                found_in_dir = await search_files(
                    validated_allowed_dir,
                    filename_to_search,
                    exclude_patterns=current_exclude_patterns,
                    exact_match=True,
                )
                candidate_files.update(found_in_dir)
            except ValueError as e:
                logger.debug(
                    f"Skipping search in {allowed_dir} due to validation error: {e}"
                )
                continue
            except Exception as e:
                logger.warning(f"Error searching in directory {allowed_dir}: {e}")
                continue

        if candidate_files:
            candidates_str = "\n".join(sorted(list(candidate_files)))
            return (
                f"ファイル '{args.path}' は見つかりませんでした。\n"
                f"以下の候補が見つかりました:\n{candidates_str}"
            )
        else:
            return f"ファイル '{args.path}' は見つからず、他の場所でも候補は見つかりませんでした。"
    except Exception as e:
        logger.error(f"Error reading file {args.path}: {e}")
        return f"ファイル '{args.path}' の読み込み中にエラーが発生しました: {str(e)}"


async def execute_write_file(arguments: Dict[str, Any]) -> str:
    """ファイルを書き込むツール実行関数"""
    args = WriteFileArgs.model_validate(arguments)
    try:
        valid_path = await validate_path(args.path)

        # 親ディレクトリが存在するか確認
        parent_dir = os.path.dirname(valid_path)
        if not os.path.exists(parent_dir):
            raise FileNotFoundError(f"親ディレクトリが存在しません: {parent_dir}")

        f = await asyncio.to_thread(open, valid_path, "w", encoding="utf-8")
        try:
            await asyncio.to_thread(f.write, args.content)
            return f"ファイル '{args.path}' への書き込みに成功しました。"
        finally:
            await asyncio.to_thread(f.close)
    except FileNotFoundError as e:
        logger.info(
            f"File cannot be written: {args.path}. Searching for alternative locations."
        )
        filename = os.path.basename(args.path)
        alternative_paths = []

        for allowed_dir in allowed_directories:
            try:
                validated_allowed_dir = await validate_path(allowed_dir)
                if os.path.exists(validated_allowed_dir) and os.access(
                    validated_allowed_dir, os.W_OK
                ):
                    alternative_path = os.path.join(validated_allowed_dir, filename)
                    alternative_paths.append(alternative_path)
            except ValueError as ve:
                logger.debug(
                    f"Skipping alternative directory {allowed_dir} due to validation error: {ve}"
                )
                continue
            except Exception as ex:
                logger.warning(f"Error checking directory {allowed_dir}: {ex}")
                continue

        if alternative_paths:
            alternatives_str = "\n".join(sorted(alternative_paths))
            return (
                f"ファイル '{args.path}' に書き込めませんでした: {str(e)}\n"
                f"以下の場所に代わりに書き込むことができます:\n{alternatives_str}"
            )
        else:
            return f"ファイル '{args.path}' に書き込めず、代替の書き込み先も見つかりませんでした。"
    except Exception as e:
        logger.error(f"Error writing file {args.path}: {e}")
        return f"ファイル '{args.path}' の書き込み中にエラーが発生しました: {str(e)}"


async def execute_edit_file(arguments: Dict[str, Any]) -> str:
    """ファイルを編集するツール実行関数"""
    args = EditFileArgs.model_validate(arguments)
    valid_path = await validate_path(args.path)

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
            await validate_path(entry_path)
            is_dir = await asyncio.to_thread(os.path.isdir, entry_path)
            formatted.append(f"[DIR] {entry}" if is_dir else f"[FILE] {entry}")
        except ValueError:
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

    gitignore_patterns = await get_gitignore_patterns(valid_path)
    combined_exclude_patterns = list(set(gitignore_patterns + args.excludePatterns))

    results = await search_files(
        valid_path, args.pattern, combined_exclude_patterns, exact_match=False
    )
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
