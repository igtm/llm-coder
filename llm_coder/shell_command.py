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

# シェルコマンドの最大出力長。これを超えると丸め処理が行われる。
MAX_OUTPUT_THRESHOLD = 7500


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

        # 出力を丸める処理
        # 実際の出力は truncate_part_length + 省略記号 + truncate_part_length となるため、
        # 指定された最大長を若干超える可能性があります。
        truncate_part_length = (
            MAX_OUTPUT_THRESHOLD // 2
        )  # 先頭・末尾それぞれで保持する文字数

        original_output_length = len(output)

        if original_output_length > MAX_OUTPUT_THRESHOLD:
            ellipsis = (
                f"\n... (出力が長すぎるため省略されました。"
                f"合計 {original_output_length} 文字。"
                f"先頭と末尾の各{truncate_part_length}文字を表示) ...\n"
            )

            output_head = output[:truncate_part_length]
            output_tail = output[-truncate_part_length:]

            output = output_head + ellipsis + output_tail

            logger.info(
                "シェルコマンドの出力が長すぎるため丸められました",
                command=args.command,
                original_length=original_output_length,
                truncated_length=len(output),  # 丸め後の実際の長さ
                max_threshold=MAX_OUTPUT_THRESHOLD,
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
                            "description": "コマンドを実行するワークスペースディレクトリ。指定しない場合はカレントディレクトリで実行されます。",
                        },
                    },
                    "required": ["command"],
                },
            },
            "execute": execute_shell_command_async,
        }
    ]
    return tools
