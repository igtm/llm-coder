#!/usr/bin/env python3
import asyncio
import argparse
import os  # os モジュールをインポート
import sys  # sys モジュールをインポート
import toml  # toml をインポート

# agent と filesystem モジュールをインポート
from llm_coder.agent import Agent
from llm_coder.filesystem import initialize_filesystem_settings, get_filesystem_tools
from llm_coder.shell_command import (
    get_shell_command_tools,
)  # get_shell_command_tools をインポート
import structlog  # structlog をインポート (agent.py と同様の設定を想定)

logger = structlog.get_logger("llm_coder.cli")


def parse_args():
    # 設定ファイル専用のパーサーを作成して、--config 引数を先に解析
    config_parser = argparse.ArgumentParser(add_help=False)
    default_config_filename = "llm_coder_config.toml"
    config_parser.add_argument(
        "--config",
        type=str,
        default=default_config_filename,  # デフォルトファイル名を設定
        help=f"TOML設定ファイルのパス (デフォルト: {default_config_filename})",
    )
    config_args, remaining_argv = config_parser.parse_known_args()

    config_values = {}
    # config_args.config は常に値を持つ (指定されたパスまたはデフォルトパス)
    config_file_path_to_load = config_args.config

    try:
        if os.path.exists(config_file_path_to_load):
            with open(config_file_path_to_load, "r", encoding="utf-8") as f:
                config_values = toml.load(f)
            logger.info(f"設定ファイル {config_file_path_to_load} を読み込みました。")
        else:
            if config_file_path_to_load == default_config_filename:
                logger.debug(
                    f"デフォルトの設定ファイルが見つかりません: {config_file_path_to_load}。設定は無視されます。"
                )
            else:
                logger.warning(
                    f"指定された設定ファイルが見つかりません: {config_file_path_to_load}"
                )
    except Exception as e:
        logger.error(
            f"設定ファイル {config_file_path_to_load} の読み込み中にエラーが発生しました: {e}"
        )
        # 設定ファイルの読み込みエラーは警告に留め、デフォルト値やCLI引数で続行する

    # メインのパーサーを作成
    parser = argparse.ArgumentParser(
        description="LLM Coder CLI",
        # epilog を追加して、設定ファイルの優先順位について説明
        epilog="設定の優先順位: コマンドライン引数 > TOML設定ファイル > ハードコードされたデフォルト値",
        # 親パーサーとして config_parser を含めることで --config ヘルプも表示
        parents=[config_parser],
    )

    # 各引数のデフォルト値を TOML ファイルの値で上書きし、最終的なデフォルト値を設定
    # prompt は位置引数のため、TOMLでのデフォルト指定方法を考慮
    # nargs='?' の位置引数の場合、default はコマンドラインで省略された場合に適用される
    prompt_default = config_values.get("prompt", None)
    parser.add_argument(
        "prompt",
        type=str,
        nargs="?",
        default=prompt_default,
        help="実行するプロンプト (省略時は標準入力から。TOMLファイルでも指定可能)",
    )

    model_default = config_values.get("model", "gpt-4.1-nano")
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=model_default,
        help=f"使用するLLMモデル (デフォルト: {model_default})",
    )

    temperature_default = config_values.get("temperature", 0.2)
    parser.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=temperature_default,
        help=f"LLMの温度パラメータ (デフォルト: {temperature_default})",
    )

    max_iterations_default = config_values.get("max_iterations", 10)
    parser.add_argument(
        "--max-iterations",
        "-i",
        type=int,
        default=max_iterations_default,
        help=f"最大実行イテレーション数 (デフォルト: {max_iterations_default})",
    )

    allowed_dirs_default = config_values.get("allowed_dirs", [os.getcwd()])
    parser.add_argument(
        "--allowed-dirs",
        nargs="+",
        default=allowed_dirs_default,
        help="ファイルシステム操作を許可するディレクトリ（スペース区切りで複数指定可）"
        f" (デフォルト: {allowed_dirs_default if allowed_dirs_default != [os.getcwd()] else '現在の作業ディレクトリ'})",
    )

    repository_description_prompt_default = config_values.get(
        "repository_description_prompt", ""
    )
    parser.add_argument(
        "--repository-description-prompt",
        type=str,
        default=repository_description_prompt_default,
        help="LLMに渡すリポジトリの説明プロンプト (デフォルト: TOMLファイルまたは空)",
    )

    # 出力ファイルのオプションを追加
    output_default = config_values.get("output", None)
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=output_default,
        help="実行結果を出力するファイルパス (デフォルト: なし、標準出力のみ)",
    )

    # 会話履歴出力ファイルのオプションを追加
    conversation_history_default = config_values.get("conversation_history", None)
    parser.add_argument(
        "--conversation-history",
        "-ch",
        type=str,
        default=conversation_history_default,
        help="エージェントの会話履歴を出力するファイルパス (デフォルト: なし)",
    )

    # remaining_argv を使って、--config 以外の引数を解析
    return parser.parse_args(remaining_argv)


async def run_agent_from_cli(args):
    """CLIからエージェントを実行するための非同期関数"""
    prompt = args.prompt
    if not prompt:  # プロンプトが引数で指定されなかった場合
        if sys.stdin.isatty():  # 標準入力がTTY（対話的）の場合のみメッセージ表示
            logger.info("プロンプトを標準入力から読み込みます (Ctrl+D で終了):")
        lines = []
        try:
            for line in sys.stdin:
                lines.append(line.rstrip("\n"))
        except KeyboardInterrupt:
            logger.warning("入力が中断されました。")
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

    # シェルコマンドツールを取得
    shell_tools = get_shell_command_tools()
    logger.debug("Retrieved shell command tools", tool_count=len(shell_tools))

    # 利用可能な全ツールを結合
    all_available_tools = filesystem_tools + shell_tools
    logger.debug("Total available tools", tool_count=len(all_available_tools))

    logger.debug("Initializing agent from CLI")
    agent_instance = Agent(  # Agent クラスのインスタンス名変更
        model=args.model,
        temperature=args.temperature,
        max_iterations=args.max_iterations,
        available_tools=all_available_tools,  # 更新されたツールリストを使用
        repository_description_prompt=args.repository_description_prompt,  # リポジトリ説明プロンプトを渡す
    )

    logger.info("Starting agent run from CLI", prompt_length=len(prompt))
    result = await agent_instance.run(prompt)  # agent_instance を使用
    logger.info("===== 実行結果 =====")
    logger.info(result)  # result が複数行の場合もそのままログに出力

    # 出力ファイルが指定されている場合、結果をファイルに書き込む
    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(result)
            logger.info(f"実行結果をファイル '{args.output}' に書き出しました")
        except Exception as e:
            logger.error(
                f"ファイル '{args.output}' への書き込み中にエラーが発生しました: {e}"
            )

    # 会話履歴出力ファイルが指定されている場合、会話履歴をファイルに書き込む
    if args.conversation_history:
        try:
            with open(args.conversation_history, "w", encoding="utf-8") as f:
                for message in agent_instance.conversation_history:
                    # 各メッセージの内容をわかりやすく書き出す
                    role = message.get("role", "unknown")
                    content = message.get("content", "")
                    f.write(f"# {role.upper()}\n{content}\n\n")
            logger.info(
                f"会話履歴をファイル '{args.conversation_history}' に書き出しました"
            )
        except Exception as e:
            logger.error(
                f"ファイル '{args.conversation_history}' への会話履歴の書き込み中にエラーが発生しました: {e}"
            )

    logger.info("Agent run completed from CLI")


def run_cli():
    """Entry point for the CLI script."""
    args = parse_args()

    # agent サブコマンドがなくなったため、直接エージェント実行ロジックを呼び出す
    asyncio.run(run_agent_from_cli(args))


if __name__ == "__main__":
    run_cli()
