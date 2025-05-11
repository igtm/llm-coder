#!/usr/bin/env python3

import asyncio
import sys
from typing import List, Dict, Any, Optional

import structlog

try:
    from pydantic import BaseModel, Field
except ImportError:
    print("Error: pydantic package required. Install with 'pip install pydantic'")
    sys.exit(1)

logger = structlog.get_logger(__name__)


# スキーマ定義
class ShellCommandArgs(BaseModel):
    command: str = Field(
        ..., description="実行するシェルコマンド文字列", min_length=1
    )  # min_length=1 を追加
    timeout: int = Field(default=60, description="コマンドのタイムアウト秒数")
    workspace: Optional[str] = Field(
        default=None,
        description="コマンドを実行するワークスペースディレクトリ。指定しない場合はカレントディレクトリ。",
    )


# ツール実行関数
async def execute_shell_command_async(arguments: Dict[str, Any]) -> str:
    """シェルコマンドを実行し、その出力を返すツール実行関数"""
    try:
        args = ShellCommandArgs.model_validate(arguments)
    except Exception as e:
        logger.error(
            "シェルコマンド引数の検証に失敗しました", error=str(e), arguments=arguments
        )
        return f"引数エラー: {str(e)}"

    logger.info(
        "シェルコマンドを実行します",
        command=args.command,
        timeout=args.timeout,
        workspace=args.workspace or "カレントディレクトリ",
    )

    try:
        # asyncio.create_subprocess_shell を使用してコマンドを実行
        process = await asyncio.create_subprocess_shell(
            args.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=args.workspace,  # ワークスペースを指定
        )

        # タイムアウト付きで待機
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=args.timeout
        )

        output = ""
        if stdout:
            output += f"Stdout:\n{stdout.decode(errors='replace')}\n"
        if stderr:
            output += f"Stderr:\n{stderr.decode(errors='replace')}\n"

        if process.returncode != 0:
            output += f"Return code: {process.returncode}\n"
            logger.warning(
                "シェルコマンドがエラーで終了しました",
                command=args.command,
                workspace=args.workspace or "カレントディレクトリ",
                return_code=process.returncode,
                stdout=stdout.decode(errors="replace"),
                stderr=stderr.decode(errors="replace"),
            )
        else:
            logger.info(
                "シェルコマンドの実行に成功しました",
                command=args.command,
                workspace=args.workspace or "カレントディレクトリ",
                return_code=process.returncode,
            )

        return output if output else "コマンドは出力を生成しませんでした。"

    except asyncio.TimeoutError:
        logger.error(
            "シェルコマンドがタイムアウトしました",
            command=args.command,
            timeout=args.timeout,
            workspace=args.workspace or "カレントディレクトリ",
        )
        # タイムアウトした場合、プロセスを強制終了しようと試みる
        if process and process.returncode is None:
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)  # terminate後の待機
            except asyncio.TimeoutError:
                process.kill()  # terminateが効かなければkill
                await process.wait()
            except Exception as e_kill:
                logger.error(
                    "タイムアウトしたプロセスの終了中にエラー", error=str(e_kill)
                )
        return f"コマンド '{args.command}' がタイムアウトしました ({args.timeout}秒)。"
    except FileNotFoundError:
        logger.error(
            "シェルコマンドの実行に失敗しました: コマンドまたはワークスペースが見つかりません",
            command=args.command,
            workspace=args.workspace,
        )
        if args.workspace:
            return f"コマンド '{args.command}' の実行に失敗しました。コマンドまたはワークスペース '{args.workspace}' が見つかりません。パスを確認してください。"
        return f"コマンド '{args.command}' が見つかりません。パスを確認してください。"
    except Exception as e:
        logger.error(
            "シェルコマンドの実行中に予期せぬエラーが発生しました",
            command=args.command,
            workspace=args.workspace or "カレントディレクトリ",
            error=str(e),
        )
        return f"コマンド '{args.command}' の実行中にエラーが発生しました: {str(e)}"


def get_shell_command_tools() -> List[Dict[str, Any]]:
    """シェルコマンド操作ツールのリストを返します"""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "execute_shell_command",
                "description": "指定されたシェルコマンドを実行し、標準出力と標準エラー出力を返します。セキュリティリスクを伴うため、注意して使用してください。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "実行する完全なシェルコマンド文字列。",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "コマンドがタイムアウトするまでの秒数。デフォルトは60秒。",
                            "default": 60,
                        },
                        "workspace": {
                            "type": "string",
                            "description": "コマンドを実行するワークスペースディレクトリ。指定しない場合はllm_coderのカレントディレクトリで実行されます。",
                        },
                    },
                    "required": ["command"],
                },
            },
            "execute": execute_shell_command_async,
        }
    ]
    return tools
