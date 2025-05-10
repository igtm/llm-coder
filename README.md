# llm_coder

llm による自立型 Cli コーディングエージェントライブラリ llm_coder

ユーザーの指示通りコーディングし、自前の linter や formatter や test コードを評価フェーズに実行でき、通るまで修正します。
llm api のインターフェースは litellm ライブラリを使用。Claude や OpenAI など自由な LLM を利用できます。

## インストール方法

1. リポジトリをクローンします:

   ```bash
   git clone <repository_url>
   cd llm_coder
   ```

2. 開発モードでパッケージをインストールします:

   ```bash
   pip install -e .
   ```

   これにより、プロジェクトディレクトリ内で `llm-coder` コマンドが利用可能になります。

### 開発中の直接実行

インストールせずに開発中に `cli.py` を直接実行することも可能です。挙動を試す用の `playground` ディレクトリを用意しているので、そのディレクトリから以下のコマンドを実行してください:

```bash
# playground ディレクトリに移動
cd playground
# 1階層上の llm_coder ディレクトリ内の cli.py を実行
uv run python ../llm_coder/cli.py <引数...>
```

例:

```bash
# playground ディレクトリにいることを想定
uv run python ../llm_coder/cli.py --prompt "Create a python script that outputs 'hello world'"
```

## 使い方

インストール後、以下のコマンドで CLI ツールを実行できます:

```bash
llm-coder
```

# Parameter

```sh
llm_coder --model claude-3-opus-20240229 --prompt "Create a python script that outputs 'hello world'"
```

# Configuration

Configuration can be done via command line arguments or a TOML file.

## TOML Configuration Example

Create a `config.toml` file with the following content:

```toml
# Global configuration
model = "claude-3-opus-20240229"
prompt = "Create a python script that outputs 'hello world'"
# log_level = "INFO"
# max_iterations = 5
# temperature = 0.7
# execute_tests = true

# Global lint/format/test commands
# lint_command = "pylint --disable=C0114,C0115,C0116,W0511"
# format_command = "black"
# test_command = "pytest"

# Directory-specific configurations
[directories.python_project]
path = "src/python_project"
lint_command = "pylint --disable=C0114,C0115,C0116,W0511"
format_command = "black"
test_command = "pytest"

[directories.typescript_project]
path = "src/typescript_project"
lint_command = "eslint"
format_command = "prettier --write"
test_command = "jest"
```

Then run `llm_coder` with the `--config` option:

```sh
llm_coder --config config.toml
```

The tool will apply the appropriate lint/format/test commands based on the directory path of the generated code. Directory-specific configurations override global settings.
