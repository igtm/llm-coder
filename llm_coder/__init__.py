"""
llm-coder: LLMによる自立型Cliコーディングエージェントライブラリ

ユーザーの指示通りコーディングし、自前のlinterやformatterやtestコードを評価フェーズに実行し、
通るまで修正するエージェントを提供します。
"""

# メインのクラスを公開APIとして再エクスポート
from llm_coder.agent import Agent

# 公開するAPIを定義
__all__ = ["Agent"]

# バージョン情報
__version__ = "0.0.2"
