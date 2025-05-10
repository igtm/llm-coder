import sys
import structlog
import logging as stdlib_logging


def configure_logging(log_level: int = stdlib_logging.DEBUG) -> None:
    """ロギング設定を初期化する関数"""
    # structlog の設定
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,  # ロガー名を追加
            structlog.stdlib.add_log_level,  # ログレベルを追加
            structlog.processors.StackInfoRenderer(),  # スタック情報を表示
            structlog.dev.set_exc_info,  # 例外情報を設定
            structlog.dev.ConsoleRenderer(),  # コンソール出力用にフォーマット
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),  # 標準ライブラリのロガー工場を使用
        wrapper_class=structlog.stdlib.BoundLogger,  # 標準ラッパークラスを使用
        cache_logger_on_first_use=True,
    )

    # 標準ライブラリのロギング設定
    stdlib_logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
