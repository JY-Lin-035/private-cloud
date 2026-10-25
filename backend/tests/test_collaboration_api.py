"""Collaboration API route registration tests."""

from app.main import app


def _collect_paths(routes):
    paths = set()
    for route in routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "original_router"):
            paths |= _collect_paths(route.original_router.routes)
    return paths


def test_collaboration_routes_use_api_prefix():
    paths = _collect_paths(app.routes)

    assert "/api/collaboration/addCollaborator" in paths
    assert "/api/collaboration/removeCollaborator" in paths
    assert "/api/collaboration/ownedCollaborations" in paths
    assert "/api/collaboration/myCollaborations" in paths
