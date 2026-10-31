from app.main import app

if __name__ == "__main__":
    import uvicorn
    # proxy_headers must stay ON: uvicorn honours X-Forwarded-Proto from the
    # local cloudflared/nginx so the app sees scheme=https. With it off,
    # request.url_for() generated tus "Location: http://..." and browsers
    # silently blocked every upload PATCH (mixed content on an https page).
    # forwarded_allow_ips pins the trust to the loopback proxy only, so a
    # remote peer can never influence the client address we read; the real
    # client IP is still taken from CF-Connecting-IP via security_engine,
    # and _docs_local_only keeps rejecting proxied access to /docs.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )
