# llm-coder

[日本語](./README.ja.md)

llm-coder is an autonomous CLI coding agent library powered by LLMs.

It codes according to user instructions, runs its own linter, formatter, and test code in an evaluation phase, and keeps fixing until all checks pass.
The LLM API interface uses the litellm library, allowing you to use any LLM such as Claude or OpenAI.
Model and API key configuration follows the litellm provider settings.  
See https://docs.litellm.ai/docs/providers for details.

## Installation

You can install llm-coder via PyPI:

```bash
pip install llm-coder
```

Or, install from source:

```bash
git clone https://github.com/igtm/llm-coder.git
cd llm-coder
pip install -e .
```

This makes the `llm-coder` command available in your project directory.

## Usage

After installation, you can run the CLI tool with:

```bash
llm-coder <prompt> [options...]
```

## Available Options

```
positional arguments:
  prompt                Prompt to execute (if omitted, read from stdin or TOML file)

options:
  -h, --help            Show help message and exit
  --config CONFIG       Path to TOML config file (default: llm-coder-config.toml)
  --model MODEL, -m MODEL
                        LLM model to use (default: gpt-4.1-nano)
  --temperature TEMPERATURE, -t TEMPERATURE
                        LLM temperature parameter (default: 0.5)
  --max-iterations MAX_ITERATIONS, -i MAX_ITERATIONS
                        Maximum execution iterations (default: 10)
  --allowed-dirs ALLOWED_DIRS [ALLOWED_DIRS ...]
                        Directories allowed for file system operations (space separated, default: ['.', 'playground'])
  --repository-description-prompt REPOSITORY_DESCRIPTION_PROMPT
                        Repository description prompt for LLM (default: from TOML file or empty)
  --output OUTPUT, -o OUTPUT
                        Output file path (default: none, stdout only)
  --conversation-history CONVERSATION_HISTORY, -ch CONVERSATION_HISTORY
                        Output file path for agent conversation history (default: none)
  --request-timeout REQUEST_TIMEOUT
                        Timeout per LLM API request in seconds (default: 60)
```

### Examples

```sh
# Basic usage
llm-coder "Create a python script that outputs 'hello world'"

# Specify model
llm-coder --model claude-3-opus-20240229 "Create a python script that outputs 'hello world'"

# Specify temperature and max iterations
llm-coder --temperature 0.7 --max-iterations 5 "Create a python script that outputs 'hello world'"

# Specify allowed directories
llm-coder --allowed-dirs . ./output ./src "Create a python script that outputs 'hello world'"

# Specify request timeout
llm-coder --request-timeout 120 "Create a python script that outputs 'hello world'"

# Output result to file
llm-coder --output result.txt "Create a python script that outputs 'hello world'"

# Output conversation history to file
llm-coder --conversation-history conversation.txt "Create a python script that outputs 'hello world'"

# Output both result and conversation history to files
llm-coder --output result.txt --conversation-history conversation.txt "Create a python script that outputs 'hello world'"
```

## Configuration

You can configure llm-coder via command line arguments or a TOML file.

**Priority:** Command line arguments > TOML config file > hardcoded defaults

### Example TOML Config File

By default, `llm-coder-config.toml` is loaded. You can specify a custom config file with `--config`.

```toml
# Global settings
model = "claude-3-opus-20240229"
prompt = "Create a python script that outputs 'hello world'"
temperature = 0.5
max_iterations = 10
request_timeout = 60
allowed_dirs = ["."]
repository_description_prompt = "This repository is a Python utility tool."
# output = "result.txt"
# conversation_history = "conversation.txt"
```

To use a config file:

```sh
# Use default config file (llm-coder-config.toml)
llm-coder

# Specify custom config file
llm-coder --config my_config.toml
```

### Running Directly During Development

You can run `cli.py` directly during development without installing. A `playground` directory is provided for testing, but you must run scripts from the project root directory.

From the project root (`llm-coder` top directory), run:

```bash
# Make sure you are in the project root directory
uv run python -m llm-coder.cli <args...>
```

Example:

```bash
# Assuming you are in the project root directory
uv run python -m llm-coder.cli "Create a python script that outputs 'hello world'"
```

## llm-coder-litellm Command

The `llm-coder-litellm` command is a simple wrapper for calling the LLM completion API directly using the LiteLLM library.

```bash
llm-coder-litellm --model <model> [options...] "prompt"
```

### Available Options

```text
usage: llm-coder-litellm [-h] --model MODEL [--temperature TEMPERATURE] [--max_tokens MAX_TOKENS] [--top_p TOP_P] [--n N] [--stream] [--stop [STOP ...]]
                         [--presence_penalty PRESENCE_PENALTY] [--frequency_penalty FREQUENCY_PENALTY] [--user USER] [--response_format RESPONSE_FORMAT]
                         [--seed SEED] [--timeout TIMEOUT] [--output OUTPUT] [--extra EXTRA]
                         [prompt]

litellm completion API wrapper

positional arguments:
  prompt                Prompt (if omitted, read from stdin)

options:
  -h, --help            show this help message and exit
  --model MODEL         Model name
  --temperature TEMPERATURE
                        Temperature parameter (default: 0.2)
  --max_tokens MAX_TOKENS
                        max_tokens
  --top_p TOP_P         top_p
  --n N                 n
  --stream              Stream output
  --stop [STOP ...]     Stop words
  --presence_penalty PRESENCE_PENALTY
                        presence_penalty
  --frequency_penalty FREQUENCY_PENALTY
                        frequency_penalty
  --user USER           user
  --response_format RESPONSE_FORMAT
                        response_format (e.g. json)
  --seed SEED           seed
  --timeout TIMEOUT     Request timeout in seconds (default: 60)
  --output OUTPUT, -o OUTPUT
                        Output file
  --extra EXTRA         Additional JSON parameters
```

### Examples

```bash
# Basic usage
llm-coder-litellm --model gpt-4.1-nano "Generate a summary of the following text"

# Specify temperature
llm-coder-litellm --model gpt-4.1-nano --temperature 0.7 "Generate a summary of the following text"

# Save output to file
llm-coder-litellm --model gpt-4.1-nano --output summary.txt "Generate a summary of the following text"
```
