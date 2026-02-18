# Ollama Vim Completion Plugin

This plugin integrates Ollama's local LLM API with Vim, enabling AI-powered code completion, explanation, and snippet generation directly in your editor.

## Features
- **Code Completion**: Generate code completions using Ollama models.
- **Code Explanation**: Get step-by-step explanations for selected code.
- **Snippet Generation**: Generate executable code snippets from comments.
- **Session Context**: Maintains conversation history and cached snippets for context-aware completions.
- **Model Listing**: View available Ollama models and select active model.

## Demo Video
[Watch a demo on YouTube](https://youtu.be/BLNidD2BSEM)

## Requirements
- Python 3
- Vim with Python support
- Ollama server running locally (default: `http://localhost:11434`)

## Installation
1. Clone or copy this repository into your Vim configuration directory:
  ```sh
  git clone <repo-url> ~/.vim
  ```
2. Ensure `ollama_complete.py` is in your `autoload/` directory and `ollama.vim` in your `plugin/` directory.
3. Start the Ollama server:
  ```sh
  ollama serve
  ```
4. (Optional) Pull desired models:
  ```sh
  ollama pull deepseek-coder:6.7b
  ```

## Usage
- **Code Completion**: Place cursor where you want completion and run:
  ```vim
  :py3 autoload.ollama_complete.insert_completion()
  ```
- **Explain Code**: Select code and run:
  ```vim
  :py3 autoload.ollama_complete.explain_code()
  ```
- **Generate from Comment**: Add a comment (starting with `#`) and run:
  ```vim
  :py3 autoload.ollama_complete.generate_from_comment()
  ```
- **List Models**: Show available Ollama models:
  ```vim
  :py3 autoload.ollama_complete.list_models()
  ```
- **Show Context**: View session turns and cached snippets:
  ```vim
  :py3 autoload.ollama_complete.show_context()
  ```

## Configuration
Set these Vim global variables to customize:
- `g:ollama_model` — Model name (default: `deepseek-coder:6.7b`)
- `g:ollama_timeout` — Request timeout (default: `30`)

## Commands
- `:OllamaContext` — Show context view
- `:OllamaClearHistory` — Clear session turns
- `:OllamaClearAll` — Clear all context and disk cache

## Troubleshooting
- Ensure Ollama server is running and accessible at the configured URL.
- Check Python and Vim integration.
- Review error messages in Vim for HTTP or connection issues.

## License
MIT License

## Credits
- [Ollama](https://ollama.com/) for the LLM API
- Inspired by open-source Vim and AI tooling

