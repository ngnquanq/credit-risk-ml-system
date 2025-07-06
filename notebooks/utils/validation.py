import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from scipy.stats import linregress
import matplotlib.pyplot as plt

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

# --- Example Usage ---
if __name__ == "__main__":
    # Create a dummy DataFrame for demonstration
    # In a real scenario, this would be your actual dataset with millions of records
    # and the relevant columns.
    np.random.seed(42)
    num_records = 10000
    weeks = np.sort(np.random.randint(1, 20, num_records)) # Weeks from 1 to 19

    # Simulate true labels (0 or 1)
    true_labels = np.random.randint(0, 2, num_records)

    # Simulate predictions with some weekly trend and variability
    # Let's make it slightly declining over time for demonstration of falling_rate
    # And add some noise
    base_preds = 0.5 + 0.1 * np.random.randn(num_records)
    # Add a slight decline based on week number
    predictions = base_preds - (weeks / np.max(weeks)) * 0.2 + 0.05 * np.random.randn(num_records)
    predictions = np.clip(predictions, 0.01, 0.99) # Ensure probabilities are within (0,1)

    dummy_df = pd.DataFrame({
        'WEEK_NUM': weeks,
        'TARGET': true_labels,
        'PREDICTION': predictions
    })

    print("Dummy DataFrame Head:")
    print(dummy_df.head())
    print("\nDummy DataFrame Info:")
    dummy_df.info()

    try:
        results = calculate_gini_stability_metric(
            df=dummy_df,
            week_col='WEEK_NUM',
            target_col='TARGET',
            prediction_col='PREDICTION'
        )

        print("\n--- Gini Stability Metric Results ---")
        print(f"Weekly Gini Scores:\n{results['weekly_gini_scores']}")
        print(f"\nMean Gini: {results['mean_gini']:.4f}")
        print(f"Linear Regression Slope (a): {results['a']:.4f}")
        print(f"Linear Regression Intercept (b): {results['b']:.4f}")
        print(f"Falling Rate Penalty (min(0, a)): {results['falling_rate_penalty']:.4f}")
        print(f"Standard Deviation of Residuals (variability penalty): {results['std_residuals']:.4f}")
        print(f"\nFinal Stability Metric: {results['stability_metric']:.4f}")

        print("\n--- Gini Over Time (Actual vs. Regression Predicted) ---")
        print(results['gini_over_time_df'])

        # You could also plot this for visual inspection:
        plt.figure(figsize=(10, 6))
        plt.plot(results['gini_over_time_df'].index, results['gini_over_time_df']['actual_gini'], marker='o', linestyle='-', label='Actual Weekly Gini')
        plt.plot(results['gini_over_time_df'].index, results['gini_over_time_df']['predicted_gini_regression'], linestyle='--', color='red', label='Regression Line (f(x) = ax + b)')
        plt.title('Weekly Gini Scores and Regression Fit')
        plt.xlabel('WEEK_NUM')
        plt.ylabel('Gini Score')
        plt.grid(True)
        plt.legend()
        plt.show()


    except ValueError as e:
        print(f"Error calculating stability metric: {e}")

    # Example with insufficient data for regression
    print("\n--- Testing with insufficient data ---")
    small_df = pd.DataFrame({
        'WEEK_NUM': [1, 1, 2, 2],
        'TARGET': [0, 1, 0, 1],
        'PREDICTION': [0.1, 0.9, 0.2, 0.8]
    })
    try:
        calculate_gini_stability_metric(small_df, 'WEEK_NUM', 'TARGET', 'PREDICTION')
    except ValueError as e:
        print(f"Caught expected error: {e}")