import pytest
from unittest.mock import patch, AsyncMock
import json
import sys
import os
from typing import Dict, Any, List

# テスト対象のモジュールをインポート
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from llm_coder.agent import Agent


# モック用のレスポンスクラス群
class MockChoiceMessage:
    """LiteLLM レスポンスの message 部分を模倣するクラス"""

    def __init__(self, content: str = None, tool_calls: List[Dict[str, Any]] = None):
        self.content = content
        self.tool_calls = tool_calls

    def get(self, key: str, default: Any = None) -> Any:
        """辞書風の get メソッドを提供"""
        if key == "content":
            return self.content
        elif key == "tool_calls":
            return self.tool_calls
        return default


class MockChoice:
    """LiteLLM レスポンスの choices 配列の要素を模倣するクラス"""

    def __init__(self, message: MockChoiceMessage):
        self.message = message


class MockResponse:
    """litellm.acompletion のレスポンス全体を模倣するクラス"""

    def __init__(self, id: str, choices_data: List[Dict[str, Any]]):
        self.id = id
        self.choices: List[MockChoice] = []
        for choice_item_data in choices_data:
            message_dict = choice_item_data.get("message", {})
            mock_message_obj = MockChoiceMessage(
                content=message_dict.get("content"),
                tool_calls=message_dict.get("tool_calls"),
            )
            self.choices.append(MockChoice(message=mock_message_obj))


# テスト用のフィクスチャ
@pytest.fixture
def mock_tools():
    """テスト用のモックツール定義"""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "ファイルの内容を読み込む",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            "execute": AsyncMock(return_value="ファイル内容のモック"),
        }
    ]


# 簡単なタスクのテスト
@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_run_with_simple_task(mock_acompletion, mock_tools):
    """簡単なタスクでagentのrunメソッドをテストする"""
    # litellm.acompletion の各呼び出しに対するモックレスポンスを設定

    # 計画フェーズのレスポンス
    planning_response = MockResponse(
        id="mock-plan-123",
        choices_data=[
            {
                "message": {
                    "content": "タスクを実行するには以下のステップが必要です：\n1. ファイルを読み込む\n2. 内容を確認する",
                    "tool_calls": [
                        {
                            "id": "call_123",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "test.txt"}),
                            },
                        }
                    ],
                }
            }
        ],
    )

    # 実行フェーズのレスポンス
    execution_response = MockResponse(
        id="mock-execution-123",
        choices_data=[
            {
                "message": {
                    "content": "ファイルを読み込みました。タスクは完了しました。",
                    "tool_calls": None,
                }
            }
        ],
    )

    # 最終要約のレスポンス
    summary_response = MockResponse(
        id="mock-summary-123",
        choices_data=[
            {"message": {"content": "タスクの要約: ファイルを正常に読み込みました。"}}
        ],
    )

    # モック関数が順番に異なるレスポンスを返すように設定
    mock_acompletion.side_effect = [
        planning_response,  # 計画フェーズの呼び出し
        execution_response,  # 実行フェーズの呼び出し
        summary_response,  # 最終要約の呼び出し
    ]

    # Agentのインスタンスを作成
    agent = Agent(
        model="mock-model",
        temperature=0.0,
        max_iterations=3,
        available_tools=mock_tools,
    )

    # エージェントを実行
    result = await agent.run("test.txtファイルを読み込んでください")

    # 結果を検証
    assert result == "タスクの要約: ファイルを正常に読み込みました。"

    # litellm.acompletion が正しく呼び出されたことを検証
    assert mock_acompletion.call_count == 3

    # 各呼び出しのパラメータを検証
    calls = mock_acompletion.call_args_list

    # 1回目の呼び出し (計画フェーズ)
    assert calls[0][1]["model"] == "mock-model"
    assert calls[0][1]["temperature"] == 0.0
    assert "tools" in calls[0][1]
    assert len(calls[0][1]["messages"]) == 2  # システムメッセージとユーザーメッセージ

    # 2回目の呼び出し (実行フェーズ)
    assert calls[1][1]["model"] == "mock-model"
    assert len(calls[1][1]["messages"]) > 2  # 履歴にツール実行結果が追加されている

    # 3回目の呼び出し (最終要約)
    assert calls[2][1]["model"] == "mock-model"
    assert "tools" not in calls[2][1]  # 要約フェーズではツールを使用しない


# 複数ツール呼び出しのテスト
@pytest.mark.asyncio
@patch("litellm.acompletion")
async def test_run_with_multiple_tool_calls(mock_acompletion, mock_tools):
    """複数のツール実行を含むタスクをテストする"""
    # 1回目: 計画フェーズ - 2つのツール呼び出しを含むレスポンス
    plan_response = MockResponse(
        id="mock-plan-456",
        choices_data=[
            {
                "message": {
                    "content": "複数ファイルを読み込む計画",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "file1.txt"}),
                            },
                        }
                    ],
                }
            }
        ],
    )

    # 2回目: ツール実行後のレスポンス - 別のツールを呼び出す
    next_response = MockResponse(
        id="mock-next-456",
        choices_data=[
            {
                "message": {
                    "content": "別のファイルも読み込みます",
                    "tool_calls": [
                        {
                            "id": "call_2",
                            "function": {
                                "name": "read_file",
                                "arguments": json.dumps({"path": "file2.txt"}),
                            },
                        }
                    ],
                }
            }
        ],
    )

    # 3回目: 全てのツール実行後の完了レスポンス
    complete_response = MockResponse(
        id="mock-complete-456",
        choices_data=[
            {
                "message": {
                    "content": "すべてのファイルを読み込みました。タスク完了。",
                    "tool_calls": None,
                }
            }
        ],
    )

    # 4回目: 要約レスポンス
    summary_response = MockResponse(
        id="mock-summary-456",
        choices_data=[
            {
                "message": {
                    "content": "2つのファイルを読み込みました: file1.txt と file2.txt"
                }
            }
        ],
    )

    # モック関数の応答を設定
    mock_acompletion.side_effect = [
        plan_response,  # 計画フェーズ
        next_response,  # 1つ目のツール実行後
        complete_response,  # 2つ目のツール実行後
        summary_response,  # 最終要約
    ]

    # Agentのインスタンスを作成
    agent = Agent(
        model="mock-model",
        temperature=0.0,
        max_iterations=5,
        available_tools=mock_tools,
    )

    # エージェントを実行
    result = await agent.run("file1.txt と file2.txt を読み込んでください")

    # 結果を検証
    assert result == "2つのファイルを読み込みました: file1.txt と file2.txt"

    # litellm.acompletion が正しく呼び出されたことを検証
    assert mock_acompletion.call_count == 4

    # ツール実行関数が2回呼ばれたことを検証
    tool_execute = mock_tools[0]["execute"]
    assert tool_execute.call_count == 2

    # 呼び出し引数を検証
    assert tool_execute.call_args_list[0][0][0] == {"path": "file1.txt"}
    assert tool_execute.call_args_list[1][0][0] == {"path": "file2.txt"}
