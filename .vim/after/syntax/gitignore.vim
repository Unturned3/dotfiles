
" Custom Vim syntax file for .gitignore files
" Author: Richard Hu

set fdl=0
set foldmethod=marker
set foldmarker=#\ {-,#\ -}

syn match Comment /^\s*#.*$/
syn match Ignore /^\s*[^#!]*$/
syn match Keep /^\s*!.*$/
syn match Modeline /^# vim:.*$/

syn match FoldM /^# {-.*$/
syn match FoldM /^# -}.*$/

hi Comment	ctermfg=12	guifg=#0000ff
hi Ignore	ctermfg=1	guifg=#800000
hi Keep		ctermfg=2	guifg=#008000

hi Modeline	ctermfg=208	guifg=#ff8700

hi FoldM ctermbg=253 guibg=#dadada
hi Folded ctermbg=253 guibg=#dadada


