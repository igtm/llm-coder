#!/usr/bin/env python3

import json
import sys
from typing import List, Dict, Any, TypedDict
import structlog

try:
    import litellm
except ImportError:
    print("Error: litellm package required. Install with 'pip install litellm'")
    sys.exit(1)

# structlog の設定は logging_config.py に移動
# 実際の設定は cli.py で行われる
logger = structlog.get_logger("llm_coder.agent")


# デフォルトプロンプト定数
COMPLETION_CHECK_PROMPT = "タスクは完了しましたか？まだ必要な操作がある場合は、ツールを呼び出して続行してください。"
FINAL_SUMMARY_PROMPT = (
    "タスクが完了しました。実行した内容の要約と結果を教えてください。"
)


# ツール実行用の型定義
class ToolCall(TypedDict):
    name: str
    arguments: Dict[str, Any]


class Message:
    """会話メッセージを表現するクラス"""

    def __init__(
        self,
        role: str,
        content: str = None,
        tool_calls: List[Dict] = None,
        tool_call_id: str = None,
        name: str = None,
    ):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id
        self.name = name

    def to_dict(self) -> Dict[str, Any]:
        """メッセージをlitellm用の辞書形式に変換"""
        result = {"role": self.role}

        if self.content is not None:
            result["content"] = self.content

        if self.tool_calls is not None:
            result["tool_calls"] = self.tool_calls

        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id

        if self.name is not None:
            result["name"] = self.name

        return result


class Agent:
    """LLMベースの自律型エージェント"""

    def __init__(
        self,
        model: str = "gpt-4.1-nano",
        temperature: float = 0.2,
        max_iterations: int = 10,
        available_tools: List[
            Dict[str, Any]
        ] = None,  # ツールリストをコンストラクタで受け取る
        completion_check_prompt: str = COMPLETION_CHECK_PROMPT,  # 完了確認用プロンプト
        final_summary_prompt: str = FINAL_SUMMARY_PROMPT,  # 最終要約用プロンプト
    ):
        self.model = model
        self.temperature = temperature
        self.max_iterations = max_iterations
        self.conversation_history: List[Message] = []
        self.completion_check_prompt = completion_check_prompt
        self.final_summary_prompt = final_summary_prompt

        # 利用可能なツールを設定
        self.available_tools = available_tools or []

        # LLMに渡すツールスキーマ (execute関数を除いたもの)
        self.tools = [
            {k: v for k, v in tool.items() if k != "execute"}
            for tool in self.available_tools
        ]

        logger.debug(
            "Agent initialized",
            model=self.model,
            temperature=self.temperature,
            max_iterations=self.max_iterations,
            tool_count=len(self.available_tools),
        )

    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """指定されたツールを実行してその結果を返す"""
        logger.debug("Executing tool", tool_name=tool_name, arguments=arguments)

        # ツール名に一致する実行関数を検索
        tool_def = next(
            (
                tool
                for tool in self.available_tools
                if tool["function"]["name"] == tool_name
            ),
            None,
        )

        if not tool_def or "execute" not in tool_def:
            logger.warning("Tool not found or not executable", tool_name=tool_name)
            return f"エラー: ツール '{tool_name}' が見つからないか実行できません"

        try:
            # ツールの実行関数を呼び出す
            execute_func = tool_def["execute"]
            result = await execute_func(arguments)
            logger.debug(
                "Tool executed successfully",
                tool_name=tool_name,
                result_length=len(str(result)),
            )
            return result
        except Exception as e:
            logger.error(
                "Error executing tool",
                tool_name=tool_name,
                arguments=arguments,
                exc_info=True,
            )
            return (
                f"エラー: ツール '{tool_name}' の実行中にエラーが発生しました: {str(e)}"
            )

    async def _planning_phase(self, prompt: str) -> None:
        """計画フェーズ - ユーザープロンプトから実行計画を作成"""
        logger.debug("Planning phase started", prompt=prompt)

        self.conversation_history = []
        logger.debug("Conversation history initialized")

        system_message_content = (
            "あなたは自律型のコーディングエージェントです。提示されたタスクを解決するために"
            "ファイルシステム上のコードを読み込み、編集し、必要なら新規作成します。\n"
            "タスクを次のステップで実行してください：\n"
            "1. タスクを解析し、必要な操作の計画を立てる\n"
            "2. 既存のコードを理解するために必要なファイルを読み込む\n"
            "3. 具体的な実装計画を立てる\n"
            "4. コードを記述、編集し、必要に応じてテストを実行する\n"
            "5. 結果を検証し、必要なら修正を行う\n\n"
            "ファイルシステムツールを使って作業を進めてください。"
        )
        system_message = Message(role="system", content=system_message_content)
        logger.debug("System message created", content=system_message_content)

        user_message = Message(role="user", content=prompt)
        logger.debug("User message created", content=prompt)

        self.conversation_history.append(system_message)
        self.conversation_history.append(user_message)
        logger.debug(
            "Initial messages added to conversation history",
            history_length=len(self.conversation_history),
        )

        logger.debug("Generating initial plan from LLM")
        try:
            response = await litellm.acompletion(
                model=self.model,
                messages=[msg.to_dict() for msg in self.conversation_history],
                temperature=self.temperature,
                tools=self.tools,  # 更新されたツールリストを使用
            )
            logger.debug(
                "LLM response received for initial plan", response_id=response.id
            )

            assistant_message_data = response.choices[0].message
            self.conversation_history.append(
                Message(
                    role="assistant",
                    content=assistant_message_data.get("content"),
                    tool_calls=assistant_message_data.get("tool_calls"),
                )
            )
            logger.debug(
                "Assistant message from initial plan added to history",
                content=assistant_message_data.get("content"),
                tool_calls=assistant_message_data.get("tool_calls"),
                history_length=len(self.conversation_history),
            )
            logger.debug("Planning phase completed")

        except Exception:
            logger.error("Error in planning phase", exc_info=True)
            raise

    async def _execution_phase(self) -> bool:
        """実行フェーズ - 計画を実行し、ツールを呼び出して結果を評価"""
        logger.debug("Execution phase started")

        try:
            assistant_message = next(
                (
                    msg
                    for msg in reversed(self.conversation_history)
                    if msg.role == "assistant"
                ),
                None,
            )

            if not assistant_message:
                logger.warning(
                    "No assistant message found in history for execution phase."
                )
                return False

            if not assistant_message.tool_calls:
                logger.debug(
                    "No tool calls found in assistant message, checking if task is complete."
                )

                completion_check_message = Message(
                    role="user", content=self.completion_check_prompt
                )
                self.conversation_history.append(completion_check_message)
                logger.debug(
                    "Sent completion check to LLM",
                    prompt=self.completion_check_prompt,
                    history_length=len(self.conversation_history),
                )

                response = await litellm.acompletion(
                    model=self.model,
                    messages=[msg.to_dict() for msg in self.conversation_history],
                    temperature=self.temperature,
                    tools=self.tools,  # 更新されたツールリストを使用
                )
                logger.debug(
                    "LLM response received for completion check",
                    response_id=response.id,
                )

                check_message_data = response.choices[0].message
                self.conversation_history.append(
                    Message(
                        role="assistant",
                        content=check_message_data.get("content"),
                        tool_calls=check_message_data.get("tool_calls"),
                    )
                )
                logger.debug(
                    "Assistant message from completion check added to history",
                    content=check_message_data.get("content"),
                    tool_calls=check_message_data.get("tool_calls"),
                    history_length=len(self.conversation_history),
                )

                if not check_message_data.get("tool_calls") and "完了" in (
                    check_message_data.get("content") or ""
                ):
                    logger.info("Task confirmed complete by LLM")
                    return True

                if check_message_data.get("tool_calls"):
                    logger.debug(
                        "New tool calls received from completion check, continuing execution."
                    )
                    return False

                logger.debug(
                    "LLM did not confirm completion and provided no new tool calls."
                )
                return False

            logger.debug(
                "Processing tool calls",
                tool_call_count=len(assistant_message.tool_calls),
            )
            for tool_call in assistant_message.tool_calls or []:
                tool_name = tool_call.get("function", {}).get("name")
                arguments_str = tool_call.get("function", {}).get("arguments", "{}")
                tool_call_id = tool_call.get("id")
                logger.debug(
                    "Preparing to execute tool",
                    tool_name=tool_name,
                    arguments_str=arguments_str,
                    tool_call_id=tool_call_id,
                )

                try:
                    arguments = json.loads(arguments_str)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to parse tool arguments JSON",
                        arguments_str=arguments_str,
                        tool_name=tool_name,
                    )
                    arguments = {}

                tool_result = await self._execute_tool(tool_name, arguments)
                logger.debug(
                    "Tool execution result",
                    tool_name=tool_name,
                    result_length=len(tool_result),
                )

                tool_message = Message(
                    role="tool",
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    content=tool_result,
                )
                self.conversation_history.append(tool_message)
                logger.debug(
                    "Tool result message added to history",
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    history_length=len(self.conversation_history),
                )

            logger.debug("Getting next actions from LLM after tool executions")
            response = await litellm.acompletion(
                model=self.model,
                messages=[msg.to_dict() for msg in self.conversation_history],
                temperature=self.temperature,
                tools=self.tools,  # 更新されたツールリストを使用
            )
            logger.debug(
                "LLM response received for next actions", response_id=response.id
            )

            new_message_data = response.choices[0].message
            self.conversation_history.append(
                Message(
                    role="assistant",
                    content=new_message_data.get("content"),
                    tool_calls=new_message_data.get("tool_calls"),
                )
            )
            logger.debug(
                "Assistant message for next actions added to history",
                content=new_message_data.get("content"),
                tool_calls=new_message_data.get("tool_calls"),
                history_length=len(self.conversation_history),
            )

            if (
                not new_message_data.get("tool_calls")
                and new_message_data.get("content")
                and (
                    "完了" in new_message_data.get("content")
                    or "成功" in new_message_data.get("content")
                )
            ):
                logger.info("Task completed successfully based on LLM response")
                return True

            logger.debug("Task not yet completed, continuing execution loop.")
            return False

        except Exception:
            logger.error("Error in execution phase", exc_info=True)
            raise

    async def run(self, prompt: str) -> str:
        """エージェントを実行し、プロンプトに応じたタスクを完了する"""
        logger.info("Starting agent run", initial_prompt=prompt)

        await self._planning_phase(prompt)

        for i in range(self.max_iterations):
            logger.debug(
                "Execution iteration",
                current_iteration=i + 1,
                max_iterations=self.max_iterations,
            )

            is_completed = await self._execution_phase()

            if is_completed:
                logger.info("Task completed", iterations=i + 1)

                final_prompt_message = Message(
                    role="user", content=self.final_summary_prompt
                )
                self.conversation_history.append(final_prompt_message)
                logger.debug(
                    "Requesting final summary from LLM",
                    prompt=self.final_summary_prompt,
                    history_length=len(self.conversation_history),
                )

                final_response = await litellm.acompletion(
                    model=self.model,
                    messages=[msg.to_dict() for msg in self.conversation_history],
                    temperature=self.temperature,
                )
                logger.debug(
                    "LLM response received for final summary",
                    response_id=final_response.id,
                )

                final_message_content = final_response.choices[0].message.get(
                    "content", "タスクは完了しましたが、要約情報はありません。"
                )
                logger.info(
                    "Agent run finished, returning final summary.",
                    summary_length=len(final_message_content),
                )
                return final_message_content

        logger.warning(
            "Maximum iterations reached without completion",
            max_iterations=self.max_iterations,
        )
        return "最大イテレーション数に達しました。タスクは未完了の可能性があります。"
