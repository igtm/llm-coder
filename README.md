# llm_coder

llm による自立型 Cli コーディングエージェントライブラリ llm_coder

ユーザーの指示通りコーディングし、自前の linter や formatter や test コードを評価フェーズに実行でき、通るまで修正します。
llm api のインターフェースは litellm ライブラリを使用。Claude や OpenAI など自由な LLM を利用できます。
モデルや API キーの設定方法は litellm のプロバイダ設定に準拠します。  
詳細は https://docs.litellm.ai/docs/providers を参照してください。

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

## 使い方

インストール後、以下のコマンドで CLI ツールを実行できます:

```bash
llm-coder <プロンプト> [オプション...]
```

## 利用可能なオプション

```
positional arguments:
  prompt                実行するプロンプト (省略時は標準入力から。TOMLファイルでも指定可能)

options:
  -h, --help            ヘルプメッセージを表示して終了
  --config CONFIG       TOML設定ファイルのパス (デフォルト: llm_coder_config.toml)
  --model MODEL, -m MODEL
                        使用するLLMモデル (デフォルト: gpt-4.1-nano)
  --temperature TEMPERATURE, -t TEMPERATURE
                        LLMの温度パラメータ (デフォルト: 0.5)
  --max-iterations MAX_ITERATIONS, -i MAX_ITERATIONS
                        最大実行イテレーション数 (デフォルト: 10)
  --allowed-dirs ALLOWED_DIRS [ALLOWED_DIRS ...]
                        ファイルシステム操作を許可するディレクトリ（スペース区切りで複数指定可） (デフォルト: ['.', 'playground'])
  --repository-description-prompt REPOSITORY_DESCRIPTION_PROMPT
                        LLMに渡すリポジトリの説明プロンプト (デフォルト: TOMLファイルまたは空)
  --output OUTPUT, -o OUTPUT
                        実行結果を出力するファイルパス (デフォルト: なし、標準出力のみ)
  --conversation-history CONVERSATION_HISTORY, -ch CONVERSATION_HISTORY
                        エージェントの会話履歴を出力するファイルパス (デフォルト: なし)
  --request-timeout REQUEST_TIMEOUT
                        LLM APIリクエスト1回あたりのタイムアウト秒数 (デフォルト: 60)
```

### 使用例

```sh
# 基本的な使い方
llm-coder "Create a python script that outputs 'hello world'"

# モデルを指定
llm-coder --model claude-3-opus-20240229 "Create a python script that outputs 'hello world'"

# 温度と最大イテレーション数を指定
llm-coder --temperature 0.7 --max-iterations 5 "Create a python script that outputs 'hello world'"

# 許可するディレクトリを指定
llm-coder --allowed-dirs . ./output ./src "Create a python script that outputs 'hello world'"

# リクエストタイムアウトを指定
llm-coder --request-timeout 120 "Create a python script that outputs 'hello world'"

# 実行結果をファイルに出力
llm-coder --output result.txt "Create a python script that outputs 'hello world'"

# 会話履歴をファイルに出力
llm-coder --conversation-history conversation.txt "Create a python script that outputs 'hello world'"

# 実行結果と会話履歴の両方をファイルに出力
llm-coder --output result.txt --conversation-history conversation.txt "Create a python script that outputs 'hello world'"
```

## 設定

設定はコマンドライン引数または TOML ファイルを通じて行うことができます。

**設定の優先順位**: コマンドライン引数 > TOML 設定ファイル > ハードコードされたデフォルト値

### TOML 設定ファイルの例

デフォルトでは `llm_coder_config.toml` という名前の設定ファイルが読み込まれます。カスタム設定ファイルは `--config` オプションで指定できます。

```toml
# グローバル設定
model = "claude-3-opus-20240229"
prompt = "Create a python script that outputs 'hello world'"
temperature = 0.5
max_iterations = 10
request_timeout = 60
allowed_dirs = ["."]
repository_description_prompt = "このリポジトリはPythonのユーティリティツールです"
# output = "result.txt"
# conversation_history = "conversation.txt"
```

設定ファイルを使用する場合:

```sh
# デフォルトの設定ファイル (llm_coder_config.toml) を使用
llm-coder

# カスタム設定ファイルを指定
llm-coder --config my_config.toml
```

### 開発中の直接実行

インストールせずに開発中に `cli.py` を直接実行することも可能です。挙動を試す用の `playground` ディレクトリを用意していますが、スクリプトの実行はプロジェクトのルートディレクトリから行う必要があります。

プロジェクトのルートディレクトリ (`llm_coder` ディレクトリのトップ) から以下のコマンドを実行してください:

```bash
# プロジェクトのルートディレクトリにいることを確認
# (例: /home/igtm/tmp/llm_coder)
uv run python -m llm_coder.cli <引数...>
```

例:

```bash
# プロジェクトのルートディレクトリにいることを想定
uv run python -m llm_coder.cli "Create a python script that outputs 'hello world'"
```

## llm-coder-litellm コマンドの使用方法

`llm-coder-litellm` コマンドは LiteLLM ライブラリを直接使用して LLM の completion API を呼び出すためのシンプルなラッパーです。

```bash
llm-coder-litellm --model <モデル名> [オプション...] "プロンプト"
```

### 利用可能なオプション

```text
usage: llm-coder-litellm [-h] --model MODEL [--temperature TEMPERATURE] [--max_tokens MAX_TOKENS] [--top_p TOP_P] [--n N] [--stream] [--stop [STOP ...]]
                         [--presence_penalty PRESENCE_PENALTY] [--frequency_penalty FREQUENCY_PENALTY] [--user USER] [--response_format RESPONSE_FORMAT]
                         [--seed SEED] [--timeout TIMEOUT] [--output OUTPUT] [--extra EXTRA]
                         [prompt]

litellm completion API ラッパー

positional arguments:
  prompt                プロンプト（省略時は標準入力）

options:
  -h, --help            show this help message and exit
  --model MODEL         モデル名
  --temperature TEMPERATURE
                        温度パラメータ (デフォルト: 0.2)
  --max_tokens MAX_TOKENS
                        max_tokens
  --top_p TOP_P         top_p
  --n N                 n
  --stream              ストリーム出力
  --stop [STOP ...]     ストップ語
  --presence_penalty PRESENCE_PENALTY
                        presence_penalty
  --frequency_penalty FREQUENCY_PENALTY
                        frequency_penalty
  --user USER           user
  --response_format RESPONSE_FORMAT
                        response_format (json など)
  --seed SEED           seed
  --timeout TIMEOUT     リクエストタイムアウト秒数 (デフォルト: 60)
  --output OUTPUT, -o OUTPUT
                        出力ファイル
  --extra EXTRA         追加のJSONパラメータ
```

### 使用例

```bash
# 基本的な使い方
llm-coder-litellm --model gpt-4.1-nano "Generate a summary of the following text"

# 温度を指定
llm-coder-litellm --model gpt-4.1-nano --temperature 0.7 "Generate a summary of the following text"

# 出力をファイルに保存
llm-coder-litellm --model gpt-4.1-nano --output summary.txt "Generate a summary of the following text"
```
