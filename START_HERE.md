# Start Here

Most AI coding agents fail the same way twice. Polaris is what you install when you're tired of watching that.

It's a small memory layer for coding agents — the piece that kicks in when the model starts guessing instead of fixing. If you've watched Claude Code retry the same broken `pip install` four times in a row, or Cursor confidently delete a working migration to "fix" CI, you already know the shape of the problem.

Polaris is for people running agents on real repos. Not the todo-app demo. The one where the build is red, it's 11pm, and you can feel the model about to propose the same fix you already rejected twice.

## What it does

Polaris gives your agent a shorter path through the dumb, repeating kind of failure — a dependency that resolves on your machine and nowhere else, a test that only fails in CI, a toolchain version that was fine last Tuesday, a config file that drifted and nobody noticed, a build step that works until you clone fresh.

It doesn't think for your agent. It keeps it from burning twenty minutes on a mistake someone else already paid the tuition for.

## Your first test

Don't hand it a clean demo. Hand it the error you wasted your last coffee break on.

That's the one that tells you whether this is worth $2.49.

`INSTALL.md` for setup. `FACTS.md` if you want the numbers.
