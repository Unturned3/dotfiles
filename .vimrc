call plug#begin()
	Plug 'tpope/vim-repeat'
	Plug 'tpope/vim-surround'
	Plug 'airblade/vim-gitgutter'
call plug#end()

" Git gutter
set signcolumn=auto
set updatetime=250	" milliseconds

" https://stackoverflow.com/q/526858
"set wildmode=longest,list,full
"set wildmenu
"set wildoptions=fuzzy,tagfile "pum
"set pumwidth=50
"set completeopt=menu,longest "meuone,preview,noinsert

set tabstop=4
set softtabstop=4
set shiftwidth=4
set expandtab
set smartindent
set number
set relativenumber

set wrap
set breakindent  " https://stackoverflow.com/a/26015800
set linebreak    " https://stackoverflow.com/a/9692577
set breakat=\ \	!@*-+;:,/?"

highlight ExtraWhitespace ctermbg=red guibg=red
match ExtraWhitespace /\s\+$/

"function! CustomSyntax()
"	hi TrailingWhitespace ctermbg=red guibg=Pink1
"	hi StatusLineNC ctermfg=247 ctermbg=255 guifg=Grey30 guibg=Grey85
"endfunction

"autocmd BufRead,BufNewFile * match TrailingWhitespace /\s\+$/
"autocmd ColorScheme * call CustomSyntax()
"autocmd FileType tex setlocal conceallevel=2 spell spelllang=en_us
"autocmd FileType haskell setlocal shiftwidth=2 softtabstop=2 expandtab
"autocmd FileType python setlocal shiftwidth=4 softtabstop=4 expandtab
"autocmd FileType markdown setlocal conceallevel=2 spell spelllang=en_us
"autocmd FileType markdown let b:coc_suggest_disable = 1
autocmd FileType help setlocal number relativenumber

" Use space bar as the leader key
nnoremap <Space> <Nop>
let mapleader="\<space>"
let maplocalleader="\<space>"

nnoremap <leader>ff <cmd>Files<CR>
nnoremap <leader>fg <cmd>GFiles<CR>

" Default to case-insensitive search
nnoremap / /\c

" Default to moving by visual lines (due to text
" wrapping), not actual lines (delimited by newlines)
noremap <expr> k (v:count == 0 ? 'gk' : 'k')
noremap <expr> j (v:count == 0 ? 'gj' : 'j')
noremap <expr> $ (v:count == 0 ? 'g$' : '$')
noremap <expr> 0 (v:count == 0 ? 'g0' : '0')
noremap <expr> gk (v:count == 0 ? 'k' : 'gk')
noremap <expr> gj (v:count == 0 ? 'j' : 'gj')
noremap <expr> g$ (v:count == 0 ? '$' : 'g$')
noremap <expr> g0 (v:count == 0 ? '0' : 'g0')

" Show syntax highlighting group under cursor
" https://tinyurl.com/mry5t3xf
"nnoremap <F10> :echo "hi<" . synIDattr(synID(line("."),col("."),1),"name") . '> trans<'
"\ . synIDattr(synID(line("."),col("."),0),"name") . "> lo<"
"\ . synIDattr(synIDtrans(synID(line("."),col("."),1)),"name") . ">"<CR>

" Quickly go to tab by number
noremap <leader>1 1gt
noremap <leader>2 2gt
noremap <leader>3 3gt
noremap <leader>4 4gt
noremap <leader>5 5gt
noremap <leader>6 6gt
noremap <leader>7 7gt
noremap <leader>8 8gt
noremap <leader>9 9gt
noremap <leader>0 :tablast<cr>

"if $COLORTERM ==# 'truecolor' || $COLORTERM ==# '24bit'
"	"colorscheme vscode
"	colorscheme github_light
"	"colorscheme github_dark_dimmed
"	"colorscheme github_dark
"else
"	colorscheme default
"endif
