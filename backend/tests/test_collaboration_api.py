"""Collaboration API route registration tests."""

from app.main import app


def test_collaboration_routes_use_api_prefix():
    paths = {route.path for route in app.routes}

    assert "/api/collaboration/addCollaborator" in paths
    assert "/api/collaboration/removeCollaborator" in paths
    assert "/api/collaboration/ownedCollaborations" in paths
    assert "/api/collaboration/myCollaborations" in paths
