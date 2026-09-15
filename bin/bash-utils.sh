
prepend_PATH() {
	if [[ ! ":$PATH:" =~ ":$1:" ]]; then
		export PATH="$1:$PATH"
	fi
}

duplicates_in_PATH() {
	echo "$PATH" | tr ':' '\n' | sort | uniq -d
}

