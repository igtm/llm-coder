"""
llm-coder: LLMによる自立型Cliコーディングエージェントライブラリ

ユーザーの指示通りコーディングし、自前のlinterやformatterやtestコードを評価フェーズに実行し、
通るまで修正するエージェントを提供します。
"""

# メインのクラスを公開APIとして再エクスポート
from llm_coder.agent import Agent
from llm_coder.filesystem import get_filesystem_tools, initialize_filesystem_settings
from llm_coder.shell_command import get_shell_command_tools

# 公開するAPIを定義
__all__ = [
    "Agent",
    "get_filesystem_tools",
    "initialize_filesystem_settings",
    "get_shell_command_tools",
]

# バージョン情報
__version__ = "0.0.4"
