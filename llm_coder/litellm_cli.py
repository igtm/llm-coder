import argparse
import asyncio
import sys
import os
import structlog
import toml

logger = structlog.get_logger("llm_coder.litellm_cli")

try:
    import litellm
except ImportError:
    litellm = None  # litellm がない場合は None


def load_config(config_path=None):
    """TOML設定ファイルを読み込む関数"""
    config_values = {}
    default_config_filename = "llm_coder_config.toml"
    config_file_path_to_load = config_path or default_config_filename

    if os.path.exists(config_file_path_to_load):
        with open(config_file_path_to_load, "r", encoding="utf-8") as f:
            config_values = toml.load(f)

    return config_values


def parse_litellm_args(argv, config_values=None):
    # 設定ファイルからのデフォルト値を使用
    config_values = config_values or {}

    # 設定ファイル専用のパーサーを作成して、--config 引数を先に解析
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument(
        "--config",
        type=str,
        default="llm_coder_config.toml",  # デフォルトファイル名を設定
        help="TOML設定ファイルのパス (デフォルト: llm_coder_config.toml)",
    )
    config_args, remaining_argv = config_parser.parse_known_args(argv)

    # litellm コマンド用の引数パーサー
    parser = argparse.ArgumentParser(
        description="litellm completion API ラッパー",
        parents=[config_parser],
    )

    # 設定ファイルから値を取得、なければデフォルト値を使用
    model_default = config_values.get("model", None)
    temperature_default = config_values.get("temperature", 0.2)

    parser.add_argument(
        "--model",
        type=str,
        required=model_default is None,  # 設定ファイルにあれば必須でなくする
        default=model_default,
        help="モデル名",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=temperature_default,
        help=f"温度パラメータ (デフォルト: {temperature_default})",
    )
    parser.add_argument("--max_tokens", type=int, default=None, help="max_tokens")
    parser.add_argument("--top_p", type=float, default=None, help="top_p")
    parser.add_argument("--n", type=int, default=None, help="n")
    parser.add_argument("--stream", action="store_true", help="ストリーム出力")
    parser.add_argument("--stop", type=str, nargs="*", default=None, help="ストップ語")
    parser.add_argument(
        "--presence_penalty", type=float, default=None, help="presence_penalty"
    )
    parser.add_argument(
        "--frequency_penalty", type=float, default=None, help="frequency_penalty"
    )
    parser.add_argument("--user", type=str, default=None, help="user")
    parser.add_argument(
        "--response_format", type=str, default=None, help="response_format (json など)"
    )
    parser.add_argument("--seed", type=int, default=None, help="seed")
    parser.add_argument(
        "--timeout", type=float, default=60, help="リクエストタイムアウト秒数"
    )
    parser.add_argument("--output", "-o", type=str, default=None, help="出力ファイル")
    parser.add_argument("--extra", type=str, default=None, help="追加のJSONパラメータ")
    parser.add_argument(
        "prompt",
        type=str,
        nargs="?",
        default=None,
        help="プロンプト（省略時は標準入力）",
    )
    return parser.parse_args(remaining_argv)


async def run_litellm_from_cli(args):
    # litellm の acompletion を呼び出す
    if litellm is None:
        logger.error("litellm ライブラリがインストールされていません。")
        sys.exit(1)

    # プロンプト取得
    prompt = args.prompt
    if not prompt:
        if sys.stdin.isatty():
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

    # messages 形式に変換
    messages = [{"role": "user", "content": prompt}]

    # パラメータ辞書を作成
    params = {
        "model": args.model,
        "messages": messages,
        "temperature": args.temperature,
        "timeout": args.timeout,
    }
    # オプションパラメータを追加
    if args.max_tokens is not None:
        params["max_tokens"] = args.max_tokens
    if args.top_p is not None:
        params["top_p"] = args.top_p
    if args.n is not None:
        params["n"] = args.n
    if args.stream:
        params["stream"] = True
    if args.stop is not None:
        params["stop"] = args.stop
    if args.presence_penalty is not None:
        params["presence_penalty"] = args.presence_penalty
    if args.frequency_penalty is not None:
        params["frequency_penalty"] = args.frequency_penalty
    if args.user is not None:
        params["user"] = args.user
    if args.response_format is not None:
        # 文字列なら {"type": ...} 形式に変換
        params["response_format"] = {"type": args.response_format}
    if args.seed is not None:
        params["seed"] = args.seed
    # extra で追加パラメータ
    if args.extra:
        import json

        try:
            extra_dict = json.loads(args.extra)
            params.update(extra_dict)
        except Exception as e:
            logger.warning(f"extra パラメータのJSONデコードに失敗: {e}")

    try:
        # acompletion を呼び出し
        response = await litellm.acompletion(**params)

        # レスポンスの出力
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(str(response["choices"][0]["message"]["content"]))
            logger.info(f"レスポンスをファイル '{args.output}' に書き出しました")
        else:
            print(response["choices"][0]["message"]["content"])
    except Exception as e:
        logger.error(f"litellm acompletion 実行中にエラー: {e}")


# エントリーポイント関数を修正
def run_litellm_cli():
    """llm-coder-litellm コマンドのエントリーポイント"""
    # 最初に --config オプションのみを解析
    config_parser = argparse.ArgumentParser(add_help=False)
    config_parser.add_argument("--config", type=str, default="llm_coder_config.toml")
    config_args, _ = config_parser.parse_known_args(sys.argv[1:])

    # 設定ファイルを読み込む
    config_values = load_config(config_args.config)

    # 設定ファイルの値を引数パーサーに渡す
    args = parse_litellm_args(sys.argv[1:], config_values)
    asyncio.run(run_litellm_from_cli(args))


if __name__ == "__main__":
    run_litellm_cli()
