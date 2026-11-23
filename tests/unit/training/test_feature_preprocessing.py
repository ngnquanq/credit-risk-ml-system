import json

import pandas as pd
import pytest

from training import feature_preprocessing
from training.feature_preprocessing import build_preprocessor, load_feature_set, select_training_data


def test_select_training_data_excludes_snapshot_metadata():
    columns = load_feature_set("legacy-v1").columns
    frame = pd.DataFrame({
        "SK_ID_CURR": [10, 20],
        **{column: [0, 1] for column in reversed(columns)},
        "TARGET": ["0", "1"],
        "snapshot_version": ["example", "example"],
    })

    features, target = select_training_data(frame)

    assert list(features.columns) == columns
    assert target.tolist() == [0, 1]


@pytest.mark.parametrize("column", ["TARGET", "DAYS_EMPLOYED"])
def test_select_training_data_rejects_incomplete_snapshot(column):
    frame = pd.DataFrame({name: [0] for name in [*load_feature_set("legacy-v1").columns, "TARGET"]})

    with pytest.raises(ValueError, match=column):
        select_training_data(frame.drop(columns=column))


def test_alternative_feature_set_controls_selection_and_preprocessing(tmp_path, monkeypatch):
    sets = tmp_path / "sets"
    sets.mkdir(parents=True)
    monkeypatch.setattr(feature_preprocessing, "_sets_dir", lambda: sets)
    path = sets / "challenger-v1.json"
    config = {
        "version": "challenger-v1",
        "features": [
            {"name": "CATEGORY", "preprocessing_group": "cat"},
            {"name": "NUMERIC", "preprocessing_group": "num_prev_other"},
        ],
    }
    path.write_text(json.dumps(config))
    original = load_feature_set("challenger-v1")
    frame = pd.DataFrame({"NUMERIC": [1.0, 2.0], "CATEGORY": ["a", "b"], "TARGET": [0, 1]})
    X, _ = select_training_data(frame, original)
    assert list(X.columns) == ["CATEGORY", "NUMERIC"]
    preprocessor = build_preprocessor(feature_set=original)
    assert [group for group, _, _ in preprocessor.transformers] == ["num_prev_other", "cat"]
    path.write_text(json.dumps(config, indent=4))
    assert load_feature_set("challenger-v1").digest == original.digest
    config["features"].reverse()
    path.write_text(json.dumps(config))
    assert load_feature_set("challenger-v1").digest != original.digest


@pytest.mark.parametrize("name", ["SK_ID_CURR", "TARGET", "VALID"])
def test_feature_set_rejects_reserved_or_duplicate_columns(tmp_path, monkeypatch, name):
    sets = tmp_path / "sets"
    sets.mkdir(parents=True)
    monkeypatch.setattr(feature_preprocessing, "_sets_dir", lambda: sets)
    features = [{"name": column, "preprocessing_group": "num_other"} for column in ["VALID", name]]
    (sets / "bad.json").write_text(json.dumps({"version": "bad", "features": features}))

    with pytest.raises(ValueError, match="Invalid or duplicate"):
        load_feature_set("bad")
