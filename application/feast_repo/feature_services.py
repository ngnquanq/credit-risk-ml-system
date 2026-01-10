from feast import FeatureService

# Support both package and direct imports
try:
    from .feature_views import (
        fv_application_features,
        fv_external,
        fv_dwh,
    )
except Exception:  # pragma: no cover
    from feature_views import (  # type: ignore
        fv_application_features,
        fv_external,
        fv_dwh,
    )


"""Feature service selection.

For now, include ALL features from the three FeatureViews. You can narrow this
list later by slicing (fv_view[["feature_a","feature_b"]]).
"""

realtime_scoring_v1 = FeatureService(
    name="realtime_scoring_v1",
    features=[
        fv_application_features,
        fv_external,
        fv_dwh,
    ],
)
