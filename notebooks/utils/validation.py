import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from scipy.stats import linregress
import matplotlib.pyplot as plt
from sklearn.metrics import precision_recall_fscore_support

def calculate_gini_stability_metric(df: pd.DataFrame, week_col: str, target_col: str, prediction_col: str) -> dict:
    """
    Calculates the Gini stability metric based on weekly Gini scores,
    a linear regression fit to these scores, and the variability of residuals.

    Args:
        df (pd.DataFrame): The input DataFrame containing predictions, true labels, and week numbers.
        week_col (str): The name of the column representing the week number (e.g., 'WEEK_NUM').
        target_col (str): The name of the column representing the true target labels (e.g., 'default_status_BOOLEAN').
        prediction_col (str): The name of the column representing the model's predicted probabilities.

    Returns:
        dict: A dictionary containing:
            - 'weekly_gini_scores': A pandas Series of Gini scores per week.
            - 'mean_gini': The mean of the weekly Gini scores.
            - 'a': The slope of the linear regression fit to weekly Gini scores.
            - 'b': The intercept of the linear regression fit to weekly Gini scores.
            - 'falling_rate_penalty': The penalized falling rate (min(0, a)).
            - 'std_residuals': The standard deviation of the linear regression residuals.
            - 'stability_metric': The final calculated stability metric.
            - 'gini_over_time_df': DataFrame with WEEK_NUM, actual Gini, and predicted Gini from regression.
    """

    # 1. Calculate Gini for each WEEK_NUM
    weekly_gini_scores = df.groupby(week_col).apply(
        lambda x: 2 * roc_auc_score(x[target_col], x[prediction_col]) - 1
    )

    # Ensure the week numbers are sorted for linear regression
    weekly_gini_scores = weekly_gini_scores.sort_index()

    # Convert WEEK_NUM (index) to a numpy array for regression
    x_weeks = weekly_gini_scores.index.values.astype(float)
    y_gini = weekly_gini_scores.values

    if len(x_weeks) < 2:
        raise ValueError("Not enough unique WEEK_NUM values (need at least 2) to perform linear regression.")

    # 2. Fit a linear regression: f(x) = a * x + b
    # linregress returns: slope, intercept, r_value, p_value, stderr
    a, b, r_value, p_value, stderr = linregress(x_weeks, y_gini)

    # 3. Calculate falling_rate
    falling_rate = min(0, a)

    # 4. Calculate residuals and their standard deviation
    predicted_gini_from_regression = a * x_weeks + b
    residuals = y_gini - predicted_gini_from_regression
    std_residuals = np.std(residuals)

    # 5. Calculate the final stability metric
    mean_gini = np.mean(weekly_gini_scores)
    stability_metric = mean_gini + 88.0 * falling_rate - 0.5 * std_residuals

    # Prepare DataFrame for plotting/inspection
    gini_over_time_df = pd.DataFrame({
        week_col: x_weeks,
        'actual_gini': y_gini,
        'predicted_gini_regression': predicted_gini_from_regression
    }).set_index(week_col)


    return {
        'weekly_gini_scores': weekly_gini_scores,
        'mean_gini': mean_gini,
        'a': a,
        'b': b,
        'falling_rate_penalty': falling_rate,
        'std_residuals': std_residuals,
        'stability_metric': stability_metric,
        'gini_over_time_df': gini_over_time_df
    }

def calculate_ece(y_true, y_prob, n_bins=10):
    """
    Calculate the Expected Calibration Error (ECE) for predicted probabilities.

    The purpose of this is to compare different model with each other.

    Args:
        y_true (array-like): True binary labels.
        y_prob (array-like): Predicted probabilities.
        n_bins (int): Number of bins to use for calibration.

    Returns:
        float: The ECE value.
    """
    # Bin the predicted probabilities
    bins = np.linspace(0, 1, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1

    ece = 0.0
    for i in range(n_bins):
        bin_mask = bin_indices == i
        if np.sum(bin_mask) > 0:
            bin_accuracy = np.mean(y_true[bin_mask])
            bin_confidence = np.mean(y_prob[bin_mask])
            ece += np.abs(bin_accuracy - bin_confidence) * np.sum(bin_mask)

    return ece / len(y_true)

def calculate_psi(expected, actual, n_bins=10):
    """
    Calculate the Population Stability Index (PSI) between expected and actual distributions.

    Args:
        expected (array-like): Expected distribution (e.g., training set).
        actual (array-like): Actual distribution (e.g., validation set).
        n_bins (int): Number of bins to use for PSI calculation.

    Returns:
        float: The PSI value.
    """
    # Create histograms for expected and actual distributions
    expected_hist, _ = np.histogram(expected, bins=n_bins, density=True)
    actual_hist, _ = np.histogram(actual, bins=n_bins, density=True)

    # Avoid division by zero
    expected_hist = np.where(expected_hist == 0, 1e-10, expected_hist)
    actual_hist = np.where(actual_hist == 0, 1e-10, actual_hist)

    # Calculate PSI
    psi = np.sum((expected_hist - actual_hist) * np.log(expected_hist / actual_hist))
    
    return psi

def calculate_gini_coef(y_true, y_prob):
    """
    Calculate the Gini coefficient for model evaluation.

    Args:
        y_true (array-like): True binary labels.
        y_prob (array-like): Predicted probabilities.

    Returns:
        float: The Gini coefficient.
    """
    # Calculate the Gini coefficient
    gini = 2 * roc_auc_score(y_true, y_prob) - 1
    return gini

def calculate_brier(y_true, y_prob):
    """
    Calculate the Prier metric for model evaluation.

    Args:
        y_true (array-like): True binary labels.
        y_prob (array-like): Predicted probabilities.

    Returns:
        float: The Prier metric value.
    """
    # Calculate the Prier metric
    prier = np.mean(np.sqrt((y_true - y_prob)**2))
    return prier

def model_evaluation_proba(y_true, y_prob, n_bins=10):
    """
    Evaluate model performance using Gini coefficient and ECE.

    Args:
        y_true (array-like): True binary labels.
        y_prob (array-like): Predicted probabilities.
        n_bins (int): Number of bins for ECE calculation.

    Returns:
        dict: A dictionary containing Gini coefficient and ECE.
    """
    # Calculate Gini coefficient
    gini = 2 * roc_auc_score(y_true, y_prob) - 1
    # Calculate ECE
    ece = calculate_ece(y_true, y_prob, n_bins)
    # calculate AUC, Recall, Precision, F1
    auc = roc_auc_score(y_true, y_prob)
    # precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='binary')
    # Calculate PSI
    # psi = calculate_psi(expected_distribution, actual_distribution)

    return {
        'gini': gini,
        'ece': ece,
        'auc': auc,
    }

def calculate_precision_at_k(y_true, y_prob, k=10):
    """
    Calculate precision at k for predicted probabilities.

    Args:
        y_true (array-like): True binary labels.
        y_prob (array-like): Predicted probabilities.
        k (int): The number of top predictions to consider.

    Returns:
        float: Precision at k.
    """
    # Get the indices of the top k predictions
    top_k_indices = np.argsort(y_prob)[-k:]
    # Calculate precision at k
    true_positives = np.sum(y_true[top_k_indices])
    precision_at_k = true_positives / k if k > 0 else 0.0
    return precision_at_k

def model_evaluation_pred(y_true, y_pred):
    """
    Evaluate model performance using Gini coefficient and ECE.

    Args:
        y_true (array-like): True binary labels.
        y_pred (array-like): Predicted binary labels.

    Returns:
        dict: A dictionary containing Gini coefficient and ECE.
    """
    precision, recall, fbeta_score, support = precision_recall_fscore_support(y_true, y_pred, average='binary')
    accuracy = np.mean(y_true == y_pred)
    return {
        'precision': precision,
        'recall': recall,
        'fbeta_score': fbeta_score,
        'support': support,
        'accuracy': accuracy
    }
def calculate_psi(expected, actual, n_bins=10):
    """
    Calculate the Population Stability Index (PSI) between expected and actual distributions.

    Args:
        expected (array-like): Expected distribution (e.g., training set).
        actual (array-like): Actual distribution (e.g., validation set).
        n_bins (int): Number of bins to use for PSI calculation.

    Returns:
        float: The PSI value.
    """
    # Create histograms for expected and actual distributions
    expected_hist, _ = np.histogram(expected, bins=n_bins, density=True)
    actual_hist, _ = np.histogram(actual, bins=n_bins, density=True)

    # Avoid division by zero
    expected_hist = np.where(expected_hist == 0, 1e-10, expected_hist)
    actual_hist = np.where(actual_hist == 0, 1e-10, actual_hist)

    # Calculate PSI
    psi = np.sum((expected_hist - actual_hist) * np.log(expected_hist / actual_hist))
    
    return psi

def unify_model_view(model_evaluation_proba, model_evaluation_pred):
    """
    Unify model evaluation results from probability and prediction evaluations.

    Args:
        model_evaluation_proba (dict): Evaluation results from probability predictions.
        model_evaluation_pred (dict): Evaluation results from binary predictions.

    Returns:
        dict: A unified dictionary containing all evaluation metrics.
    """
    unified_results = {
        'gini': model_evaluation_proba['gini'],
        'ece': model_evaluation_proba['ece'],
        'auc': model_evaluation_proba['auc'],
        'precision': model_evaluation_pred['precision'],
        'recall': model_evaluation_pred['recall'],
        'fbeta_score': model_evaluation_pred['fbeta_score'],
        'support': model_evaluation_pred['support'],
        'accuracy': model_evaluation_pred['accuracy']
    }
    return unified_results
