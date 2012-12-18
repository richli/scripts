#!/usr/bin/env bash

# For all the git annex objects with the 3-character directory hash, create
# links from 2-character directory hash to 3-character hash

# A proper git annex has files stored like this:
# .git/annex/objects/ab/cd/key/key
# where ab and cd are two-character values generated from the MD5 of the key

# A git annex directory or rsync special remote has files stored like this:
# .git/annex/abc/def/key/key
# where abc and def are three-character values generated differently from the
# key MD5

# The problem is the files in the git repo are symlinks to the annex, but they
# use the two-character directory style, whereas if the files are stored via
# rsync, they're in the three-character directory style.  This script symlinks
# the files in the three-character directories to where they *should* be, in
# the two-character directories

# Helpful information from here: http://git-annex.branchable.com/bugs/using_old_remote_format_generates_irritating_output/

# This script must be run in the root of the git repo

# Created 17 Dec 2012 richli

shopt -s nullglob
echo "$0: Symlink git annex objects from three-character directories to two-character ones"

# TODO: Find annex location by recursively searching up the directory tree?
ANNEX=$(pwd)/.git/annex

# Look for symbolic links that go into the annex
files_raw=($(find $(pwd) -type l -lname '*.git/annex/*' -printf '%l\n'))

if [[ "${#files[@]}" -eq 0 ]]; then
    echo "No git annexed files found"
else
    # Trim link to get to annex (Otherwise an annex file that is subdirectories
    # below the root will have lots of extra ../../.. prepending it, which we
    # don't care about so discard here)
    files=${files_raw[@]##*/.git/annex/}

    for file in "${files[@]}"; do

        # Compute the three-character directory name
        file_hash=$(echo -n ${file##*/} | md5sum)
        hash_dir="${file_hash:0:3}/${file_hash:3:3}"
        dest_file=${file/objects\/??\/??\//$hash_dir\/}

        # Make directory and symlink if needed
        echo $file
        if [[ -e $ANNEX/$file ]]; then
            echo "2-character hash exists"
        else
            echo "2-character hash DOES NOT exist"
            mkdir -p $ANNEX/${file%/*/*}
            #echo "${file%/*} should point to ${dest_file%/*}"
            ln -s $ANNEX/${dest_file%/*} $ANNEX/${file%/*}
        fi

    done

fi
