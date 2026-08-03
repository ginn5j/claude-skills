# claude-skills

Skills for [Claude Code](https://claude.com/claude-code), kept in version control
so they survive a machine.

## Install

```sh
git clone https://github.com/ginn5j/claude-skills.git
cd claude-skills
./install.sh
```

That symlinks each directory under `skills/` into `~/.claude/skills/`, where
Claude Code looks for them. Symlinks rather than copies, so an edit here takes
effect at once and `git status` still shows what changed.

`./install.sh --dry-run` prints what it would do. `./install.sh --uninstall`
removes only the links it made. Anything already sitting at a target path is
moved aside with a timestamped `.backup` suffix rather than overwritten.

## Skills

### trace-to-svg

Traces a bitmap drawing into a single simplified SVG path that can be tinted
with `currentColor` — for icons, glyphs, game tiles, logos, silhouettes.

Stdlib Python plus macOS `sips`. No `potrace`, no PIL, nothing to install.

```sh
python3 ~/.claude/skills/trace-to-svg/trace.py art.png --preview /tmp/p.html > /tmp/path.txt
```

Thresholds to ink, dilates to close gaps in the linework, flood-fills the
background inward, walks the boundary, then simplifies with Douglas–Peucker.
Enclosed regions come back as extra rings, so fill the result with
`fill-rule="evenodd"`.

macOS only, and it wants a drawing on a light background with a mostly closed
outline — see [the skill](skills/trace-to-svg/SKILL.md) for the tuning guide and
the full list of limits.

## Adding a skill

Drop it in `skills/<name>/` with a `SKILL.md` carrying `name` and `description`
frontmatter, then re-run `./install.sh`. The `description` is what Claude matches
against when deciding whether a skill applies, so make it say when to reach for
it, not just what it does.
