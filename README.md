# llm_coder

llm による自立型 Cli コーディングエージェントライブラリ llm_coder

ユーザーの指示通りコーディングし、自前の linter や formatter や test コードを評価フェーズに実行でき、通るまで修正します。
llm api のインターフェースは litellm ライブラリを使用。Claude や OpenAI など自由な LLM を利用できます。
