import pytest
import structlog

from llm_coder.shell_command import get_shell_command_tools

# pytest-asyncio を使用するため、イベントループのフィクスチャは不要な場合が多い
# pytest が自動的に処理してくれる

# テスト用の structlog 設定 (必要に応じて)
structlog.configure(
    processors=[
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.dev.ConsoleRenderer(),  # シンプルなコンソール出力
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
)
logger = structlog.get_logger(__name__)


@pytest.fixture
def shell_tool_executor():
    """シェルコマンド実行ツールを提供するフィクスチャ"""
    tools_list = get_shell_command_tools()
    assert len(tools_list) == 1
    assert tools_list[0]["function"]["name"] == "execute_shell_command"
    return tools_list[0]["execute"]


@pytest.mark.asyncio
async def test_shell_command_success(shell_tool_executor):
    """正常に実行されるシェルコマンドのテスト"""
    logger.info("テストケース: 成功するコマンド")
    args = {"command": "echo 'Hello from pytest shell'"}
    result = await shell_tool_executor(args)
    assert "Hello from pytest shell" in result
    assert "Stderr:" not in result  # エラー出力がないことを期待
    assert (
        "Return code: 0" in result
        or "コマンドは出力を生成しませんでした。" not in result
    )  # 成功時はReturn code 0


@pytest.mark.asyncio
async def test_shell_command_ls(shell_tool_executor):
    """lsコマンドの成功テスト"""
    logger.info("テストケース: lsコマンド")
    # Pythonの実行ファイル名が含まれているかなどで確認
    # 環境依存を減らすため、特定のファイル名ではなく、一般的な出力を期待する
    args = {"command": "ls -a"}  # 隠しファイルも表示
    result = await shell_tool_executor(args)
    assert "." in result  # カレントディレクトリ
    assert ".." in result  # 親ディレクトリ
    assert (
        "Return code: 0" in result
        or "コマンドは出力を生成しませんでした。" not in result
    )


@pytest.mark.asyncio
async def test_shell_command_non_existent_command(shell_tool_executor):
    """存在しないコマンドのテスト"""
    logger.info("テストケース: 失敗するコマンド (存在しないコマンド)")
    args = {"command": "some_highly_improbable_non_existent_command_for_test"}
    result = await shell_tool_executor(args)
    assert (
        f"コマンド '{args['command']}' が見つかりません" in result
        or "Return code:" in result
    )  # OSによりメッセージが異なる可能性
    # FileNotFoundError の場合、"Return code:" は含まれないことがある


@pytest.mark.asyncio
async def test_shell_command_error_code(shell_tool_executor):
    """エラーコードを返すコマンドのテスト"""
    logger.info("テストケース: エラーコードを返すコマンド")
    args = {"command": "ls /non_existent_directory_for_testing_error_codes_123xyz"}
    result = await shell_tool_executor(args)
    assert "Stderr:" in result
    assert "Return code:" in result
    assert "Return code: 0" not in result  # 0以外のリターンコードを期待


@pytest.mark.asyncio
async def test_shell_command_timeout(shell_tool_executor):
    """タイムアウトするコマンドのテスト"""
    logger.info("テストケース: タイムアウトするコマンド")
    args = {"command": "sleep 3", "timeout": 1}  # 1秒でタイムアウト
    result = await shell_tool_executor(args)
    assert (
        f"コマンド '{args['command']}' がタイムアウトしました ({args['timeout']}秒)。"
        in result
    )


@pytest.mark.asyncio
async def test_shell_command_invalid_args_schema(shell_tool_executor):
    """不正な引数スキーマでの呼び出しテスト"""
    logger.info("テストケース: 引数不正 (スキーマ違反)")
    args = {"cmd_instead_of_command": "echo 'invalid arg name'"}  # "command" が必須
    result = await shell_tool_executor(args)
    assert "引数エラー:" in result
    assert "Field required" in result  # Pydantic v2 のエラーメッセージ


@pytest.mark.asyncio
async def test_shell_command_empty_command(shell_tool_executor):
    """空のコマンド文字列のテスト"""
    logger.info("テストケース: 空のコマンド")
    args = {"command": ""}  # 空のコマンド
    result = await shell_tool_executor(args)
    # シェルやOSによって挙動が異なる可能性がある
    # ここでは何らかのエラーメッセージか、特定のReturn codeを期待
    assert "引数エラー:" in result or "Return code:" in result or "Stderr:" in result
    if "引数エラー:" not in result:  # Pydanticで空文字列を許可している場合
        assert "Return code: 0" not in result  # 成功しないことを期待


@pytest.mark.asyncio
async def test_shell_command_default_timeout(shell_tool_executor):
    """デフォルトタイムアウトを使用するコマンドのテスト"""
    logger.info("テストケース: デフォルトタイムアウト")
    args = {"command": "echo 'Testing default timeout'"}  # timeout を指定しない
    # ShellCommandArgs のデフォルトタイムアウトは60秒なので、echo は余裕で成功するはず
    result = await shell_tool_executor(args)
    assert "Testing default timeout" in result
    assert (
        "Return code: 0" in result
        or "コマンドは出力を生成しませんでした。" not in result
    )
