#!/usr/bin/env python3
import asyncio
import argparse
import os  # os モジュールをインポート
import sys  # sys モジュールをインポート

# agent と filesystem モジュールをインポート
from llm_coder.agent import Agent
from llm_coder.filesystem import initialize_filesystem_settings, get_filesystem_tools
import structlog  # structlog をインポート (agent.py と同様の設定を想定)

# structlog の基本的な設定 (agent.py と同様に設定するか、共通の設定モジュールを作るのが望ましい)
# ここでは簡易的に設定
logger = structlog.get_logger("llm_coder.cli")


def parse_args():
    parser = argparse.ArgumentParser(description="LLM Coder CLI")
    # Add subparsers for different commands
    subparsers = parser.add_subparsers(
        dest="command", help="Command to run", required=True
    )  # command を必須に

    # Agent command
    agent_parser = subparsers.add_parser("agent", help="Run the LLM coding agent")
    agent_parser.add_argument(
        "prompt", type=str, nargs="?", help="実行するプロンプト (省略時は標準入力から)"
    )  # prompt を位置引数に変更、nargs='?' で省略可能に
    agent_parser.add_argument(
        "--model",
        "-m",
        type=str,
        default="gpt-4.1-nano",
        help="使用するLLMモデル",
    )
    agent_parser.add_argument(
        "--temperature", "-t", type=float, default=0.2, help="LLMの温度パラメータ"
    )
    agent_parser.add_argument(
        "--max-iterations", "-i", type=int, default=10, help="最大実行イテレーション数"
    )
    agent_parser.add_argument(
        "--allowed-dirs",
        nargs="+",
        help="ファイルシステム操作を許可するディレクトリ（スペース区切りで複数指定可）",
        default=[os.getcwd()],  # デフォルトは現在の作業ディレクトリ
    )
    # Filesystem server command is removed

    return parser.parse_args()


async def run_agent_from_cli(args):
    """CLIからエージェントを実行するための非同期関数"""
    prompt = args.prompt
    if not prompt:  # プロンプトが引数で指定されなかった場合
        if sys.stdin.isatty():  # 標準入力がTTY（対話的）の場合のみメッセージ表示
            print("プロンプトを標準入力から読み込みます (Ctrl+D で終了):")
        lines = []
        try:
            for line in sys.stdin:
                lines.append(line.rstrip("\n"))
        except KeyboardInterrupt:
            print("\n入力が中断されました。")
            return
        prompt = "\n".join(lines)
        if not prompt.strip():
            logger.error("プロンプトが空です。実行を中止します。")
            return

    logger.debug("Command line arguments parsed for agent", args=vars(args))

    # ファイルシステム設定を初期化
    try:
        initialize_filesystem_settings(args.allowed_dirs)
        logger.info(
            "Filesystem settings initialized with allowed directories.",
            directories=args.allowed_dirs,
        )
    except (FileNotFoundError, NotADirectoryError) as e:
        logger.error(
            "Failed to initialize filesystem settings due to invalid directory.",
            error=str(e),
        )
        sys.exit(1)  # エラーで終了

    # ファイルシステムツールを取得
    filesystem_tools = get_filesystem_tools()
    logger.debug("Retrieved filesystem tools", tool_count=len(filesystem_tools))

    logger.debug("Initializing agent from CLI")
    agent_instance = Agent(  # Agent クラスのインスタンス名変更
        model=args.model,
        temperature=args.temperature,
        max_iterations=args.max_iterations,
        available_tools=filesystem_tools,
    )

    logger.info("Starting agent run from CLI", prompt_length=len(prompt))
    result = await agent_instance.run(prompt)  # agent_instance を使用
    print("\n===== 実行結果 =====\n")
    print(result)
    logger.info("Agent run completed from CLI")


def run_cli():
    """Entry point for the CLI script."""
    args = parse_args()

    if args.command == "agent":
        asyncio.run(run_agent_from_cli(args))  # 新しい非同期関数を呼び出し
    # Filesystem command handling is removed
    else:
        # Default behavior if no command is specified or for other commands
        # For now, if no command (or an unknown one) is given,
        # we can show help or run the default main.
        # If only 'agent' is supported, we might want to make it default or error.
        # For this change, we assume 'agent' is the primary command.
        # If args.command is None (no subcommand given), print help.
        # `required=True` にしたので、command が None になることはない
        # if args.command is None:
        #     parse_args().print_help()
        # else:
        # Fallback for any other case, though currently only 'agent' is defined.
        # asyncio.run(default_main()) # default_main を呼び出し
        # 不明なコマンドの場合はヘルプを表示
        logger.error(f"不明なコマンド: {args.command}")
        parse_args().print_help()
        sys.exit(1)


if __name__ == "__main__":
    run_cli()
