import vim
import urllib.request
import urllib.error
import json
import re
import os
import time
from collections import deque

OLLAMA_URL      = "http://localhost:11434/api/generate"
OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS     = "http://localhost:11434/api/tags"

# Context Storage — three layers:
#   1. _turn_history   — conversation turns this session (in-memory)
#   2. _snippet_cache  — generated snippets keyed by comment (in-memory)
#   3. CONTEXT_FILE    — persisted JSON across sessions (on disk)

CONTEXT_FILE = os.path.expanduser(r"C:\Users\KANDARP\vimfiles\ollama_context.json")

_turn_history: list = []   # list of {"role": ..., "content": ...}
MAX_TURNS = 10             # keep last N user/assistant pairs

_snippet_cache: dict = {}  # comment text → generated code string



def _load_context() -> dict:
    if os.path.exists(CONTEXT_FILE):
        try:
            with open(CONTEXT_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"snippets": {}, "file_summaries": {}}


def _save_context(ctx: dict):
    os.makedirs(os.path.dirname(CONTEXT_FILE), exist_ok=True)
    try:
        with open(CONTEXT_FILE, "w") as f:
            json.dump(ctx, f, indent=2)
    except Exception:
        pass


_disk_context = _load_context()

def add_turn(role: str, content: str):
    """Append a turn and trim to MAX_TURNS pairs."""
    _turn_history.append({"role": role, "content": content})
    max_items = MAX_TURNS * 2
    if len(_turn_history) > max_items:
        del _turn_history[0]


def get_history_messages(system_prompt: str) -> list:
    """
    Build messages list for /api/chat.
    Format:  [system]  [user, assistant, user, assistant ...]
    The model therefore 'remembers' all previous turns.
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(_turn_history[-(MAX_TURNS * 2):])
    return messages


def cache_snippet(comment: str, code: str):
    """Save snippet in memory and on disk."""
    _snippet_cache[comment] = code
    _disk_context.setdefault("snippets", {})[comment] = {
        "code":      code,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    _save_context(_disk_context)


def get_cached_snippet(comment: str):
    """Return cached code for this comment, or None."""
    if comment in _snippet_cache:
        return _snippet_cache[comment]
    entry = _disk_context.get("snippets", {}).get(comment)
    return entry.get("code") if entry else None


def store_file_summary(filepath: str, summary: str):
    """Remember a short description of a file for future context injection."""
    _disk_context.setdefault("file_summaries", {})[filepath] = {
        "summary":   summary,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    _save_context(_disk_context)


def get_file_summary(filepath: str):
    return _disk_context.get("file_summaries", {}).get(filepath, {}).get("summary")


def clear_history():
    _turn_history.clear()
    vim.command('echo "Session history cleared."')


def clear_all_context():
    _turn_history.clear()
    _snippet_cache.clear()
    _disk_context.clear()
    if os.path.exists(CONTEXT_FILE):
        os.remove(CONTEXT_FILE)
    vim.command('echo "All context cleared (memory + disk)."')

def get_config(key, default):
    try:
        return vim.eval(f"get(g:, '{key}', '{default}')")
    except:
        return default


def get_prefix():
    row, col  = vim.current.window.cursor
    lines     = list(vim.current.buffer[:row])
    lines[-1] = lines[-1][:col]
    return "\n".join(lines)


def get_suffix():
    row, col = vim.current.window.cursor
    first    = vim.current.buffer[row - 1][col:]
    rest     = list(vim.current.buffer[row:])
    return "\n".join([first] + rest)


def get_current_line_before_cursor():
    row, col = vim.current.window.cursor
    return vim.current.buffer[row - 1][:col]


def get_filetype():
    try:
        ft = vim.eval("&filetype")
        return ft if ft else "python"
    except:
        return "python"


def build_fim_prompt(prefix, suffix):
    return f"<｜fim▁begin｜>{prefix}<｜fim▁hole｜>{suffix}<｜fim▁end｜>"


def query_ollama(prompt, model, timeout=30):
    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "raw":    True,
        "options": {
            "temperature": 0.0,
            "num_predict": 50,
            "stop": [
                "<｜fim▁begin｜>", "<｜fim▁hole｜>",
                "<｜fim▁end｜>",   "<|endoftext|>", "\n\n"
            ]
        }
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("response", "").strip()


def clean_completion(completion, current_line_before_cursor):
    for token in ["<｜fim▁begin｜>", "<｜fim▁hole｜>", "<｜fim▁end｜>", "<|endoftext|>"]:
        completion = completion.replace(token, "")
    completion = completion.replace("```python", "").replace("```", "").strip()
    cur = current_line_before_cursor.strip()
    if cur and completion.startswith(cur):
        completion = completion[len(cur):].strip()
    completion = re.sub(r'^["\',`\s]+', '', completion)
    completion = completion.split("\n")[0]
    return completion.strip()


def _extract_code(content: str) -> str:
    m = re.search(r"```(?:python)?\n(.*?)```", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"```(?:python)?\n(.*)", content, re.DOTALL)
    if m:
        return m.group(1).strip()
    return content.strip()


def _clean_code_lines(generated: str, all_lines: list) -> list:
    """Filter prose, imports, fences, and already-present lines."""
    clean = []
    for line in generated.split("\n"):
        s = line.strip()
        if not s:
            clean.append("")
            continue
        if s.startswith("```"):
            continue
        if s.startswith("import ") or s.startswith("from "):
            continue
        if "read_csv" in s:
            continue
        has_code   = any(c in s for c in ["=", "(", ")", ".", "[", "]", ":", "#"])
        is_comment = s.startswith("#")
        is_prose   = (s[0].isupper() and not has_code) or s.endswith(("...", "?", "!"))
        if is_prose and not is_comment:
            continue
        clean.append(line)

    existing = set(l.strip() for l in all_lines if l.strip())
    return [l for l in clean if l.strip() not in existing]

def insert_completion():
    model   = get_config("ollama_model",   "deepseek-coder:6.7b")
    timeout = int(get_config("ollama_timeout", "30"))
    vim.command('echo "Completing..."')
    try:
        prefix       = get_prefix()
        suffix       = get_suffix()
        current_line = get_current_line_before_cursor()
        prompt       = build_fim_prompt(prefix, suffix)
        completion   = query_ollama(prompt, model, timeout)
        completion   = clean_completion(completion, current_line)

        if not completion:
            vim.command('echo "No completion received."')
            return

        row, col      = vim.current.window.cursor
        line          = vim.current.buffer[row - 1]
        before_cursor = line[:col]

        needs_space = (
            len(before_cursor) > 0
            and not before_cursor.endswith(" ")
            and not completion.startswith(" ")
        )
        if needs_space:
            completion = " " + completion

        vim.current.buffer[row - 1] = before_cursor + completion + line[col:]
        vim.current.window.cursor   = (row, col + len(completion))
        vim.command(f'echo "Done! -> {completion.strip()}"')

    except urllib.error.HTTPError as e:
        vim.command(f'echom "HTTP Error {e.code}: {e.reason}"')
    except urllib.error.URLError as e:
        vim.command(f'echom "Connection Error: {str(e)}"')
    except Exception as e:
        vim.command(f'echom "Error: {str(e)}"')


def explain_code():
    vim.command('echo "Explaining..."')
    try:
        start = vim.current.buffer.mark("<")
        end   = vim.current.buffer.mark(">")

        if start and end and start[0] != end[0]:
            lines = list(vim.current.buffer[start[0]-1 : end[0]])
            code  = "\n".join(lines)
        elif start and end and start[0] == end[0]:
            code = vim.current.buffer[start[0]-1]
        else:
            code = vim.current.line

        code = code.strip()
        if not code:
            vim.command('echo "No code selected!"')
            return

        model   = get_config("ollama_model",  "deepseek-coder:6.7b")
        timeout = int(get_config("ollama_timeout", "30"))

        user_msg = (
            f"Explain this Python code step by step in simple English. "
            f"Be clear and concise.\n\nCode:\n```python\n{code}\n```"
        )

        messages = get_history_messages(
            "You are a helpful Python coding assistant. "
            "Remember previous code and explanations in this session."
        )
        messages.append({"role": "user", "content": user_msg})

        payload = json.dumps({
            "model":    model,
            "messages": messages,
            "stream":   False,
            "options":  {"temperature": 0.3, "num_predict": 400}
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_CHAT_URL, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            result = data.get("message", {}).get("content", "").strip()

        add_turn("user",      user_msg)
        add_turn("assistant", result)

        vim.command("botright new")
        vim.command("setlocal buftype=nofile bufhidden=wipe noswapfile wrap")
        vim.command("resize 15")

        buf    = vim.current.buffer
        buf[0] = "YOUR CODE:"
        buf.append("=" * 50)
        for l in code.split("\n"):
            buf.append("  " + l)
        buf.append("")
        buf.append("EXPLANATION:")
        buf.append("=" * 50)
        for l in result.split("\n"):
            buf.append("  " + l)
        buf.append("")
        buf.append(f"  [Turn {len(_turn_history)//2} in session]  Press :q to close")
        vim.command('echo "Done! Press :q to close"')

    except urllib.error.HTTPError as e:
        vim.command(f'echom "HTTP Error {e.code}: {e.reason}"')
    except urllib.error.URLError as e:
        vim.command(f'echom "Connection Error: {str(e)}"')
    except Exception as e:
        vim.command(f'echom "Explain Error: {str(e)}"')


def list_models():
    try:
        req = urllib.request.Request(OLLAMA_TAGS, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data   = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]

        vim.command("new")
        vim.command("setlocal buftype=nofile bufhidden=wipe noswapfile")
        vim.current.buffer[0] = "Available Ollama Models:"
        vim.current.buffer.append("-" * 30)
        if models:
            for m in models:
                vim.current.buffer.append(f"  - {m}")
        else:
            vim.current.buffer.append("  No models found!")
            vim.current.buffer.append("  Run: ollama pull deepseek-coder:6.7b")
        vim.current.buffer.append("")
        vim.current.buffer.append(
            f"  Active   : {get_config('ollama_model', 'deepseek-coder:6.7b')}"
        )
        vim.current.buffer.append(
            f"  Context  : {CONTEXT_FILE}"
        )
        vim.current.buffer.append(
            f"  Turns    : {len(_turn_history)//2} in session  |  "
            f"Snippets cached: {len(_disk_context.get('snippets', {}))}"
        )
    except Exception as e:
        vim.command(f'echom "Error: {str(e)}"')


def generate_from_comment():
    vim.command('echo "Reading file and generating code..."')
    try:
        row, _  = vim.current.window.cursor
        comment = vim.current.buffer[row - 1].strip()

        if not comment:
            vim.command('echo "No comment on this line!"')
            return
        if not comment.startswith("#"):
            vim.command('echo "Line must start with #"')
            return

        description = comment.lstrip("#").strip()
        all_lines   = list(vim.current.buffer)
        whole_file  = "\n".join(all_lines)

        cached = get_cached_snippet(description)
        if cached:
            use_cache = vim.eval(
                f'input("Cached snippet exists for this comment. Use it? (y/n): ")'
            ).strip().lower()
            if use_cache == "y":
                lines = _clean_code_lines(cached, all_lines)
                if lines:
                    vim.current.buffer.append("", row)
                    for i, line in enumerate(lines):
                        vim.current.buffer.append(line, row + 1 + i)
                    vim.current.buffer.append("", row + 1 + len(lines))
                    vim.command(f'echo "Inserted from cache! {len(lines)} lines."')
                else:
                    vim.command('echo "Cached snippet had nothing new to insert."')
                return

        model   = get_config("ollama_model",   "deepseek-coder:6.7b")
        timeout = int(get_config("ollama_timeout", "60"))

        prior = ""
        assistant_turns = [
            t["content"] for t in _turn_history if t["role"] == "assistant"
        ]
        if assistant_turns:
            prior = (
                "\n\nSnippets generated earlier this session "
                "(already in file — do not repeat them):\n"
                + "\n---\n".join(assistant_turns[-3:])[-600:]
            )

        user_content = (
            f"Given this Python file:\n\n{whole_file}{prior}\n\n"
            f"Write ONLY executable Python code (no imports) to: {description}. "
            f"Use the existing variable 'df'."
        )

        messages = get_history_messages(
            "You are a Python code generator. "
            "Output ONLY raw executable Python code. "
            "No explanation, no prose. You may use markdown code fences. "
            "Remember what code you have generated earlier in this session "
            "and do not repeat it."
        )
        messages.append({"role": "user", "content": user_content})

        payload = json.dumps({
            "model":    model,
            "messages": messages,
            "stream":   False,
            "options": {
                "temperature": 0.1,
                "num_predict": 200,
                "stop": ["[INST]", "[/INST]", "<|im_end|>"]
            }
        }).encode("utf-8")

        req = urllib.request.Request(
            OLLAMA_CHAT_URL, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data    = json.loads(resp.read().decode("utf-8"))
            content = data.get("message", {}).get("content", "").strip()

        generated = _extract_code(content)
        lines     = _clean_code_lines(generated, all_lines)

        if not lines:
            vim.command('echo "Nothing new to insert."')
            return

        add_turn("user",      user_content)
        add_turn("assistant", generated)
        cache_snippet(description, generated)

        vim.current.buffer.append("", row)
        for i, line in enumerate(lines):
            vim.current.buffer.append(line, row + 1 + i)
        vim.current.buffer.append("", row + 1 + len(lines))

        vim.command(
            f'echo "Done! {len(lines)} lines  '
            f'[turns: {len(_turn_history)//2}  '
            f'cached: {len(_disk_context.get("snippets", {}))}]"'
        )

    except urllib.error.HTTPError as e:
        vim.command(f'echom "HTTP Error {e.code}: {e.reason}"')
    except urllib.error.URLError as e:
        vim.command(f'echom "Connection Error: {str(e)}"')
    except Exception as e:
        vim.command(f'echom "Error: {str(e)}"')

def show_context():
    """Open a buffer showing all stored context."""
    try:
        vim.command("botright new")
        vim.command("setlocal buftype=nofile bufhidden=wipe noswapfile wrap")
        vim.command("resize 20")

        buf    = vim.current.buffer
        buf[0] = "═══  Ollama Context Store  ═══"
        buf.append("")
        buf.append(f"  File   : {CONTEXT_FILE}")
        buf.append(f"  Turns  : {len(_turn_history)//2} / {MAX_TURNS} max")
        buf.append("")

        buf.append("─── Session Turns ─────────────────────────────")
        if _turn_history:
            for t in _turn_history:
                role    = t["role"].upper()
                snippet = t["content"][:80].replace("\n", " ")
                buf.append(f"  [{role}] {snippet}...")
        else:
            buf.append("  (empty — no generations yet this session)")

        buf.append("")
        buf.append("─── Cached Snippets (persisted) ───────────────")
        snippets = _disk_context.get("snippets", {})
        if snippets:
            for comment, entry in list(snippets.items())[-10:]:
                ts   = entry.get("timestamp", "?")
                code = entry.get("code", "")[:60].replace("\n", " ")
                buf.append(f"  [{ts}]")
                buf.append(f"    # {comment[:50]}")
                buf.append(f"    → {code}...")
                buf.append("")
        else:
            buf.append("  (no snippets cached yet)")

        buf.append("")
        buf.append("─── .vimrc commands ───────────────────────────")
        buf.append("  :OllamaContext       — this view")
        buf.append("  :OllamaClearHistory  — wipe session turns only")
        buf.append("  :OllamaClearAll      — wipe everything + disk")
        buf.append("")
        buf.append("  Press :q to close")

    except Exception as e:
        vim.command(f'echom "Context Error: {str(e)}"')