"""Compatibility entry point: builds the root desktop app, without dist."""
from build_root_desktop import ROOT, compile_exe, main

if __name__ == "__main__":
    raise SystemExit(main())
