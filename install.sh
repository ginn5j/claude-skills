#!/bin/sh
# Link every skill in this repo into ~/.claude/skills so Claude Code finds it.
#
# Symlinks rather than copies, so editing a skill here takes effect immediately
# and `git status` still tells you what has changed. Re-run it after cloning on
# a new machine, or after adding a skill.
#
#   ./install.sh           link them
#   ./install.sh --dry-run show what would happen and change nothing
#   ./install.sh --uninstall  remove the links this script made
set -eu

repo=$(cd "$(dirname "$0")" && pwd)
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mode=install
case "${1:-}" in
  --dry-run) mode=dry ;;
  --uninstall) mode=uninstall ;;
  "") ;;
  *) echo "usage: $0 [--dry-run|--uninstall]" >&2; exit 2 ;;
esac

[ "$mode" = dry ] || mkdir -p "$dest"

for src in "$repo"/skills/*/; do
  [ -d "$src" ] || continue
  name=$(basename "$src")
  link="$dest/$name"

  if [ "$mode" = uninstall ]; then
    # Only ever remove our own symlink. A real directory there is someone's
    # own skill and is not ours to delete.
    if [ -L "$link" ] && [ "$(readlink "$link")" = "${src%/}" ]; then
      rm "$link"; echo "unlinked $name"
    else
      echo "skipped  $name (not a link to this repo)"
    fi
    continue
  fi

  if [ -L "$link" ] && [ "$(readlink "$link")" = "${src%/}" ]; then
    echo "ok       $name (already linked)"
    continue
  fi

  # A directory or foreign link already there would be destroyed by ln -sf.
  # Move it aside instead: losing a skill to an install script is not on.
  if [ -e "$link" ] || [ -L "$link" ]; then
    backup="$link.backup.$(date +%Y%m%d%H%M%S)"
    if [ "$mode" = dry ]; then
      echo "would move aside $link -> $backup, then link $name"
      continue
    fi
    mv "$link" "$backup"
    echo "moved    $name aside to $(basename "$backup")"
  elif [ "$mode" = dry ]; then
    echo "would link $name -> $dest/$name"
    continue
  fi

  ln -s "${src%/}" "$link"
  echo "linked   $name"
done

[ "$mode" = dry ] && echo "(dry run — nothing changed)"
exit 0
