if exists('g:loaded_ollama')
    finish
endif
let g:loaded_ollama = 1
" Suppress 'Press ENTER' messages
set cmdheight=2

" Settings
let g:ollama_model   = get(g:, 'ollama_model',   'deepseek-coder:6.7b')
let g:ollama_timeout = get(g:, 'ollama_timeout',  30)

" Load Python
let s:plugin_dir = expand('<sfile>:p:h:h')
python3 << EOF
import sys, vim
path = vim.eval("s:plugin_dir") + "/autoload"
if path not in sys.path:
    sys.path.insert(0, path)
import ollama_complete
EOF

" Commands
command! OllamaComplete  python3 ollama_complete.insert_completion()
command! OllamaExplain   python3 ollama_complete.explain_code()
command! OllamaModels    python3 ollama_complete.list_models()
command! OllamaGenerate  python3 ollama_complete.generate_from_comment()
command! -nargs=1 OllamaModel let g:ollama_model = <q-args>

" Keymaps
inoremap <C-Space> <Esc>:OllamaComplete<CR>a
nnoremap <F2>      :OllamaExplain<CR>
vnoremap <F2>      :<C-u>OllamaExplain<CR>
nnoremap <F3>      :OllamaModels<CR>
nnoremap <F4>      :OllamaGenerate<CR>
nnoremap <F5>      :w<CR>:!python %<CR>
nnoremap <F6>      :OllamaComplete<CR>

echo "Ollama loaded! Model: " . g:ollama_model