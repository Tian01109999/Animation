"""Private backend for the desktop window; never opens the default browser."""
from __future__ import annotations

import argparse
import os
import secrets


def build_app(token: str):
    from fastapi import FastAPI, Header, HTTPException
    import gradio as gr
    from . import activity, paths
    from .tools_bin import add_bundled_to_path
    from .ui import build_app as build_ui

    add_bundled_to_path()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    from .login_portal import LoginPortal, attach
    attach(app, LoginPortal())
    from .update_portal import attach as attach_updates
    attach_updates(app, token)

    @app.get('/__desktop__/status')
    def status(x_storytoon_desktop: str = Header(default='')):
        if not secrets.compare_digest(x_storytoon_desktop, token):
            raise HTTPException(status_code=403)
        return {'ready': True, 'busy': activity.busy(), 'app': 'StoryToon',
                'dataRoot': str(paths.ROOT), 'assetsRoot': str(paths.ASSETS),
                'projectsRoot': str(paths.PROJECTS)}

    ui=build_ui().queue(default_concurrency_limit=2)
    return gr.mount_gradio_app(
        app, ui, path='/',css=ui.css,js=ui.js,
        allowed_paths=[str(paths.ASSETS), str(paths.PROJECTS), str(paths.VOICE_PREVIEWS)],
        blocked_paths=[str(paths.ROOT / '.env'), str(paths.CONFIG_FILE), str(paths.RUNTIME)],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    token = os.environ.get('STORYTOON_DESKTOP_TOKEN', '')
    if len(token) < 32:
        raise RuntimeError('Desktop session token is missing.')
    import uvicorn
    uvicorn.run(build_app(token), host='127.0.0.1', port=args.port, access_log=False, log_level='warning')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
