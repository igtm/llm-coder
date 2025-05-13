import argparse
import asyncio
import sys
import structlog

logger = structlog.get_logger("llm_coder.litellm_cli")

try:
    import litellm
except ImportError:
    litellm = None  # litellm がない場合は None


def parse_litellm_args(argv):
    # litellm コマンド用の引数パーサー
    parser = argparse.ArgumentParser(
        description="litellm completion API ラッパー",
    )
    parser.add_argument("--model", type=str, required=True, help="モデル名")
    parser.add_argument("--temperature", type=float, default=0.2, help="温度パラメータ")
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
    return parser.parse_args(argv)


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


# エントリーポイント関数を追加
def run_litellm_cli():
    """llm-coder-litellm コマンドのエントリーポイント"""
    args = parse_litellm_args(sys.argv[1:])
    asyncio.run(run_litellm_from_cli(args))


if __name__ == "__main__":
    run_litellm_cli()
