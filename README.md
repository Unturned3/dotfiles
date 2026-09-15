# Dotfiles

The configs and dotfiles in this home directory are tracked by Git. For more information, see the [Dotfiles](https://wiki.archlinux.org/title/Dotfiles) page in the Arch Linux wiki.

To clone these to a new machine, do:
```sh
git clone --bare git@github.com:Unturned3/dotfiles.git $HOME/.dotfiles.git
alias conf='git --git-dir="$HOME/.dotfiles.git/" --work-tree="$HOME"'
conf config --local status.showUntrackedFiles no
conf config --local remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
conf fetch origin
conf checkout SOME_BRANCH
```
Then restart your shell. Make sure your `PATH` contains `~/bin`, which is where the `conf` script is stored.


### Tips & Tricks

About git refspecs: [chatgpt](https://chatgpt.com/c/69580d7d-8f88-8333-a169-b4cb08c06aee)
```sh
$ conf config --get-all remote.origin.fetch
# Prints nothing? Your repo's missing the standard refspecs.
$ conf config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'
$ conf fetch origin
...
Unpacking objects: 100% (60/60), 373.04 KiB | 751.00 KiB/s, done.
From https://github.com/unturned3/dotfiles
 * [new branch]      babel      -> origin/babel
$ conf rev-parse origin/babel
6fccde72eddb8e2af236ed8e0171a1912177e6c0
```

To pull the latest changes to master and update a system-specific branch without using `checkout`:
```
conf update-master
conf merge master
# Or rebase (but needs force push)
conf rebase master
```
Perhaps we should never push machine-specific branches? They aren't intended to be shared anyways. However, pushing could be for backup though.


To list remote branches:
```
git branch -r
```

To checkout a remote branch as a local branch:
```
git checkout -b local_branch_name origin/remote_branch_name
```
