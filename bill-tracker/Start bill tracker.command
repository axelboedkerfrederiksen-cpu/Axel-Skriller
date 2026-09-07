#!/bin/zsh
cd -- "${0:A:h}" || exit 1
runtime_dir="$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies"
if ! command -v node >/dev/null 2>&1 && [[ -x "$runtime_dir/node/bin/node" ]]; then
  export PATH="$runtime_dir/node/bin:$PATH"
fi
if ! command -v pnpm >/dev/null 2>&1 && [[ -x "$runtime_dir/bin/fallback/pnpm" ]]; then
  export PATH="$runtime_dir/bin/fallback:$PATH"
fi
pnpm dev --host 127.0.0.1
