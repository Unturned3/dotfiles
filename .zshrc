prepend_PATH() {
	if [[ ! ":$PATH:" =~ ":$1:" ]]; then
		export PATH="$1:$PATH"
	fi
}

export STM32CubeMX_PATH='/Applications/STMicroelectronics/STM32CubeMX.app/Contents/Resources'
export STM32_PRG_PATH='/Applications/STMicroelectronics/STM32Cube/STM32CubeProgrammer/STM32CubeProgrammer.app/Contents/MacOs/bin'

#export CC=clang
#export CXX=clang++
#export CFLAGS='-std=c11'
#export CXXFLAGS='-std=c++20'
#export JAVA_HOME=`/usr/libexec/java_home`

prepend_PATH "/usr/local/opt/llvm/bin"
#prepend_PATH "/usr/local/sicstus4.7.1/bin"
prepend_PATH "$HOME/bin"
prepend_PATH "$HOME/.local/bin"

alias ffmpeg='ffmpeg -loglevel warning'
alias yt-dlp-mp4-avc='yt-dlp -S ext:mp4,codec:avc'
alias yt-dlp-mp3='yt-dlp -f bestaudio --extract-audio --audio-format mp3'
#alias vim=nvim
#alias make=gmake
alias ls="ls -G"
alias grep="grep --color=auto"
#alias airport="/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
#alias sicstus="rlwrap sicstus"


# Make arrow keys do history prefix search
autoload -U up-line-or-beginning-search
autoload -U down-line-or-beginning-search
zle -N up-line-or-beginning-search
zle -N down-line-or-beginning-search
bindkey '^[[A' up-line-or-beginning-search   # Arrow up
bindkey '^[[B' down-line-or-beginning-search # Arrow down

export WORDCHARS='*?_-[]~;!#$%^(){}<>'

# Do not add space after tab-completions
zstyle ':completion:*' add-space false

unfunction prepend_PATH
