import pandas as pd
import pytest

from training.feature_preprocessing import FEATURES, select_training_data


def test_select_training_data_excludes_snapshot_metadata():
    frame = pd.DataFrame({
        "SK_ID_CURR": [10, 20],
        **{column: [0, 1] for column in reversed(FEATURES)},
        "TARGET": ["0", "1"],
        "snapshot_version": ["example", "example"],
    })

    features, target = select_training_data(frame)

    assert list(features.columns) == FEATURES
    assert target.tolist() == [0, 1]


@pytest.mark.parametrize("column", ["TARGET", "DAYS_EMPLOYED"])
def test_select_training_data_rejects_incomplete_snapshot(column):
    frame = pd.DataFrame({name: [0] for name in [*FEATURES, "TARGET"]})

    with pytest.raises(ValueError, match=column):
        select_training_data(frame.drop(columns=column))
