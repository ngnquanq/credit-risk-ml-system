# Quick Model Loading Script
# Generated on 20250906_155202

import pickle
import json

def load_best_model():
    """Load the best performing tuned model."""
    with open("../models/tuned_models/best_model_20250906_155202.pkl", 'rb') as f:
        model = pickle.load(f)
    return model

def load_model_metadata():
    """Load model metadata and performance information."""
    with open("../models/model_metadata_20250906_155202.json", 'r') as f:
        metadata = json.load(f)
    return metadata

def load_hyperparameters():
    """Load optimized hyperparameters."""
    with open("../models/hyperparameters/tuned_params_20250906_155202.json", 'r') as f:
        params = json.load(f)
    return params

# Example usage:
# model = load_best_model()
# predictions = model.predict_proba(X_test)[:, 1]
# metadata = load_model_metadata()
# print(f"Model AUC: {metadata['model_info']['final_score']:.6f}")
