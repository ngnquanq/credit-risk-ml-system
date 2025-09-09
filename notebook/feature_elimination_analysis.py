#!/usr/bin/env python3
"""
Feature Elimination Analysis Script

Based on the results from 06092025_all_data_modeling.ipynb:
- Best model: CatBoost Balanced (AUC: 0.782702)
- Total features: 273 
- Target: Reduce to ~150 high-value features while maintaining AUC >0.77

This script analyzes feature importance and creates an optimized feature set.
"""

import pandas as pd
import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import LabelEncoder
import warnings
warnings.filterwarnings('ignore')

# Import classifiers
try:
    from catboost import CatBoostClassifier
    print("✅ CatBoost imported successfully")
except ImportError as e:
    print(f"❌ CatBoost import failed: {e}")
    CatBoostClassifier = None

try:
    from xgboost import XGBClassifier
    print("✅ XGBoost imported successfully")
except ImportError as e:
    print(f"❌ XGBoost import failed: {e}")
    XGBClassifier = None

print("📦 Feature elimination analysis starting...\n")

def load_and_prepare_data():
    """Load and prepare the complete dataset as in the original notebook."""
    print("=== LOADING AND PREPARING DATA ===")
    
    # Load baseline + POS + bureau + credit card features
    print("Loading baseline + POS + bureau + credit card features...")
    baseline_pos_bureau_cc = pl.read_csv('./data/baseline_pos_bureau_cc.csv')
    print(f"✅ Baseline dataset loaded: {baseline_pos_bureau_cc.shape}")
    
    # Load previous application features
    print("Loading previous application features...")
    previous_app_features = pl.read_csv('./data/previous_application_features.csv')
    print(f"✅ Previous app features loaded: {previous_app_features.shape}")
    
    # Merge datasets
    print("Merging datasets...")
    complete_dataset = baseline_pos_bureau_cc.join(
        previous_app_features,
        on='SK_ID_CURR',
        how='left'
    )
    print(f"✅ Complete dataset created: {complete_dataset.shape}")
    
    # Convert to pandas and prepare features
    complete_dataset_pandas = complete_dataset.to_pandas()
    X_complete = complete_dataset_pandas.drop(['SK_ID_CURR', 'TARGET'], axis=1)
    y_complete = complete_dataset_pandas['TARGET']
    
    print(f"Feature matrix: {X_complete.shape}")
    print(f"Target distribution: {y_complete.value_counts().to_dict()}")
    
    return X_complete, y_complete

def clean_data(X, y):
    """Apply the same data cleaning as in the original notebook."""
    print("\n=== CLEANING DATA ===")
    
    # Handle infinite values
    X = X.replace([np.inf, -np.inf], np.nan)
    
    # Handle categorical columns
    categorical_columns = X.select_dtypes(include=['object']).columns.tolist()
    if categorical_columns:
        print(f"Encoding {len(categorical_columns)} categorical columns...")
        le = LabelEncoder()
        for col in categorical_columns:
            X[col] = X[col].fillna('Unknown')
            X[col] = le.fit_transform(X[col].astype(str))
    
    # Clip extreme values
    for col in X.columns:
        if X[col].dtype in ['float64', 'float32', 'int64', 'int32']:
            valid_values = X[col].dropna()
            if len(valid_values) > 0:
                lower_bound = valid_values.quantile(0.001)
                upper_bound = valid_values.quantile(0.999)
                X[col] = X[col].clip(lower=lower_bound, upper=upper_bound)
    
    # Handle missing values
    prev_app_cols = [col for col in X.columns if col.startswith('PREV_')]
    for col in prev_app_cols:
        if 'RATIO' in col or 'RATE' in col:
            X[col] = X[col].fillna(X[col].median())
        else:
            X[col] = X[col].fillna(0)
    
    non_prev_cols = [col for col in X.columns if not col.startswith('PREV_')]
    for col in non_prev_cols:
        X[col] = X[col].fillna(X[col].median())
    
    print(f"✅ Data cleaned. Final shape: {X.shape}")
    print(f"Missing values remaining: {X.isnull().sum().sum()}")
    
    return X, y

def train_reference_model(X_train, y_train, X_test, y_test):
    """Train the reference CatBoost model to replicate notebook results."""
    print("\n=== TRAINING REFERENCE MODEL ===")
    
    # Train CatBoost with class weights (replicating best notebook result)
    from sklearn.utils.class_weight import compute_class_weight
    class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
    
    cat_reference = CatBoostClassifier(
        random_state=42,
        verbose=False,
        iterations=300,
        depth=6,
        learning_rate=0.1,
        class_weights=[class_weights[0], class_weights[1]],
        subsample=0.8
    )
    
    cat_reference.fit(X_train, y_train)
    cat_pred = cat_reference.predict_proba(X_test)[:, 1]
    cat_auc = roc_auc_score(y_test, cat_pred)
    
    print(f"✅ Reference CatBoost AUC: {cat_auc:.6f}")
    print(f"Expected: ~0.782702 (from notebook)")
    
    return cat_reference, cat_auc

def analyze_feature_importance(model, feature_names):
    """Extract and analyze feature importance from trained model."""
    print("\n=== ANALYZING FEATURE IMPORTANCE ===")
    
    # Get feature importance
    importance_scores = model.get_feature_importance()
    
    # Create feature importance dataframe
    feature_importance = pd.DataFrame({
        'feature': feature_names,
        'importance': importance_scores
    }).sort_values('importance', ascending=False)
    
    print(f"✅ Feature importance extracted for {len(feature_names)} features")
    
    # Analyze importance distribution
    print(f"\n📊 IMPORTANCE DISTRIBUTION:")
    print(f"Max importance: {feature_importance['importance'].max():.6f}")
    print(f"Mean importance: {feature_importance['importance'].mean():.6f}")
    print(f"Median importance: {feature_importance['importance'].median():.6f}")
    print(f"Min importance: {feature_importance['importance'].min():.6f}")
    
    # Count features by importance thresholds
    thresholds = [0.1, 0.01, 0.001, 0.0001]
    print(f"\n📈 FEATURES BY IMPORTANCE THRESHOLD:")
    for threshold in thresholds:
        count = (feature_importance['importance'] >= threshold).sum()
        pct = count / len(feature_importance) * 100
        print(f"   >= {threshold:6.4f}: {count:3d} features ({pct:5.1f}%)")
    
    # Show top and bottom features
    print(f"\n🔝 TOP 20 MOST IMPORTANT FEATURES:")
    for i, (_, row) in enumerate(feature_importance.head(20).iterrows(), 1):
        print(f"   {i:2d}. {row['feature']:<30}: {row['importance']:8.6f}")
    
    print(f"\n🔻 BOTTOM 20 LEAST IMPORTANT FEATURES:")
    for i, (_, row) in enumerate(feature_importance.tail(20).iterrows(), 1):
        print(f"   {i:2d}. {row['feature']:<30}: {row['importance']:8.6f}")
    
    return feature_importance

def create_feature_selection_tiers(feature_importance):
    """Create feature selection tiers based on importance and business logic."""
    print("\n=== CREATING FEATURE SELECTION TIERS ===")
    
    # Define feature categories and their business importance
    core_indicators = [
        'AMT_INCOME_TOTAL', 'AMT_CREDIT', 'AMT_ANNUITY', 'AMT_GOODS_PRICE',
        'DAYS_BIRTH', 'DAYS_EMPLOYED', 'CNT_CHILDREN',
        'CODE_GENDER', 'NAME_INCOME_TYPE', 'NAME_EDUCATION_TYPE'
    ]
    
    bureau_indicators = [col for col in feature_importance['feature'] if 'BUREAU' in col.upper()]
    credit_card_indicators = [col for col in feature_importance['feature'] if 'CC_' in col or 'CREDIT_CARD' in col.upper()]
    pos_indicators = [col for col in feature_importance['feature'] if 'POS_' in col]
    prev_app_indicators = [col for col in feature_importance['feature'] if col.startswith('PREV_')]
    
    # Create tiers
    tiers = {}
    
    # Tier 1: Must-have features (core + high importance)
    tier1_features = []
    for feature in feature_importance['feature']:
        if (feature in core_indicators or 
            feature_importance[feature_importance['feature'] == feature]['importance'].iloc[0] >= 1.0):
            tier1_features.append(feature)
    
    # Tier 2: High-value features (importance >= 0.1)
    tier2_features = feature_importance[
        (feature_importance['importance'] >= 0.1) & 
        (~feature_importance['feature'].isin(tier1_features))
    ]['feature'].tolist()
    
    # Tier 3: Medium-value features (importance >= 0.01)
    tier3_features = feature_importance[
        (feature_importance['importance'] >= 0.01) & 
        (~feature_importance['feature'].isin(tier1_features + tier2_features))
    ]['feature'].tolist()
    
    # Tier 4: Low-value features (importance >= 0.001)
    tier4_features = feature_importance[
        (feature_importance['importance'] >= 0.001) & 
        (~feature_importance['feature'].isin(tier1_features + tier2_features + tier3_features))
    ]['feature'].tolist()
    
    # Tier 5: Very low-value features (candidates for elimination)
    tier5_features = feature_importance[
        (feature_importance['importance'] < 0.001)
    ]['feature'].tolist()
    
    tiers = {
        'Tier 1 (Must-have)': tier1_features,
        'Tier 2 (High-value)': tier2_features, 
        'Tier 3 (Medium-value)': tier3_features,
        'Tier 4 (Low-value)': tier4_features,
        'Tier 5 (Eliminate)': tier5_features
    }
    
    print(f"📊 FEATURE TIERS CREATED:")
    for tier_name, features in tiers.items():
        print(f"   {tier_name:<20}: {len(features):3d} features")
    
    return tiers

def test_reduced_feature_sets(X_train, y_train, X_test, y_test, tiers, reference_auc):
    """Test different reduced feature sets and validate performance."""
    print("\n=== TESTING REDUCED FEATURE SETS ===")
    
    results = {}
    feature_combinations = [
        ("Tier 1 Only", tiers['Tier 1 (Must-have)']),
        ("Tier 1+2", tiers['Tier 1 (Must-have)'] + tiers['Tier 2 (High-value)']),
        ("Tier 1+2+3", tiers['Tier 1 (Must-have)'] + tiers['Tier 2 (High-value)'] + tiers['Tier 3 (Medium-value)']),
        ("Tier 1+2+3+4", tiers['Tier 1 (Must-have)'] + tiers['Tier 2 (High-value)'] + tiers['Tier 3 (Medium-value)'] + tiers['Tier 4 (Low-value)']),
        ("All Features", list(X_train.columns))
    ]
    
    from sklearn.utils.class_weight import compute_class_weight
    class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
    
    for combo_name, selected_features in feature_combinations:
        if len(selected_features) == 0:
            continue
            
        print(f"\n📊 Testing {combo_name} ({len(selected_features)} features)...")
        
        # Filter features
        available_features = [f for f in selected_features if f in X_train.columns]
        X_train_subset = X_train[available_features]
        X_test_subset = X_test[available_features]
        
        # Train model
        model = CatBoostClassifier(
            random_state=42,
            verbose=False,
            iterations=300,
            depth=6,
            learning_rate=0.1,
            class_weights=[class_weights[0], class_weights[1]],
            subsample=0.8
        )
        
        model.fit(X_train_subset, y_train)
        predictions = model.predict_proba(X_test_subset)[:, 1]
        auc_score = roc_auc_score(y_test, predictions)
        
        # Calculate performance metrics
        auc_drop = reference_auc - auc_score
        feature_reduction = (1 - len(available_features) / len(X_train.columns)) * 100
        
        results[combo_name] = {
            'features': len(available_features),
            'auc': auc_score,
            'auc_drop': auc_drop,
            'feature_reduction': feature_reduction,
            'selected_features': available_features
        }
        
        print(f"   AUC: {auc_score:.6f} (drop: {auc_drop:+.6f})")
        print(f"   Feature reduction: {feature_reduction:.1f}%")
    
    return results

def recommend_optimal_feature_set(results, min_auc_threshold=0.77):
    """Recommend the optimal feature set based on performance and efficiency."""
    print(f"\n=== RECOMMENDING OPTIMAL FEATURE SET ===")
    
    print(f"📊 PERFORMANCE COMPARISON:")
    print(f"{'Feature Set':<15} {'Features':<10} {'AUC':<10} {'Drop':<10} {'Reduction'}")
    print("-" * 65)
    
    for name, metrics in results.items():
        print(f"{name:<15} {metrics['features']:<10d} {metrics['auc']:<10.6f} "
              f"{metrics['auc_drop']:+<10.6f} {metrics['feature_reduction']:6.1f}%")
    
    # Find best balance of performance and efficiency
    viable_options = {name: metrics for name, metrics in results.items() 
                     if metrics['auc'] >= min_auc_threshold}
    
    if not viable_options:
        print(f"\n⚠️ No feature sets meet minimum AUC threshold of {min_auc_threshold}")
        return None
    
    # Recommend based on highest feature reduction while maintaining performance
    best_option = min(viable_options.items(), key=lambda x: x[1]['features'])
    recommended_name, recommended_metrics = best_option
    
    print(f"\n🏆 RECOMMENDED FEATURE SET: {recommended_name}")
    print(f"   Features: {recommended_metrics['features']} (vs {results['All Features']['features']} original)")
    print(f"   AUC: {recommended_metrics['auc']:.6f}")
    print(f"   AUC drop: {recommended_metrics['auc_drop']:+.6f}")
    print(f"   Feature reduction: {recommended_metrics['feature_reduction']:.1f}%")
    
    return recommended_name, recommended_metrics

def save_feature_selection_results(feature_importance, tiers, results, recommended_features):
    """Save all analysis results to files."""
    print(f"\n=== SAVING ANALYSIS RESULTS ===")
    
    # Save feature importance
    importance_path = './data/feature_importance_analysis.csv'
    feature_importance.to_csv(importance_path, index=False)
    print(f"✅ Feature importance saved to: {importance_path}")
    
    # Save recommended features
    recommended_path = './data/recommended_features.csv'
    pd.DataFrame({'selected_features': recommended_features}).to_csv(recommended_path, index=False)
    print(f"✅ Recommended features saved to: {recommended_path}")
    
    # Save tiers
    tiers_path = './data/feature_tiers.csv'
    tier_data = []
    for tier_name, features in tiers.items():
        for feature in features:
            tier_data.append({'tier': tier_name, 'feature': feature})
    pd.DataFrame(tier_data).to_csv(tiers_path, index=False)
    print(f"✅ Feature tiers saved to: {tiers_path}")
    
    # Save performance comparison
    performance_path = './data/feature_selection_performance.csv'
    perf_data = []
    for name, metrics in results.items():
        perf_data.append({
            'feature_set': name,
            'feature_count': metrics['features'],
            'auc_score': metrics['auc'],
            'auc_drop': metrics['auc_drop'],
            'feature_reduction_pct': metrics['feature_reduction']
        })
    pd.DataFrame(perf_data).to_csv(performance_path, index=False)
    print(f"✅ Performance comparison saved to: {performance_path}")

def main():
    """Main execution function."""
    print("🚀 FEATURE ELIMINATION ANALYSIS")
    print("="*50)
    
    # Load and prepare data
    X, y = load_and_prepare_data()
    X_clean, y_clean = clean_data(X.copy(), y.copy())
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(
        X_clean, y_clean, test_size=0.2, random_state=42, stratify=y_clean
    )
    print(f"\nTraining set: {X_train.shape}")
    print(f"Test set: {X_test.shape}")
    
    # Train reference model
    reference_model, reference_auc = train_reference_model(X_train, y_train, X_test, y_test)
    
    # Analyze feature importance
    feature_importance = analyze_feature_importance(reference_model, X_train.columns.tolist())
    
    # Create feature tiers
    tiers = create_feature_selection_tiers(feature_importance)
    
    # Test reduced feature sets
    results = test_reduced_feature_sets(X_train, y_train, X_test, y_test, tiers, reference_auc)
    
    # Get recommendation
    recommendation = recommend_optimal_feature_set(results)
    
    if recommendation:
        recommended_name, recommended_metrics = recommendation
        recommended_features = recommended_metrics['selected_features']
        
        # Save results
        save_feature_selection_results(feature_importance, tiers, results, recommended_features)
        
        print(f"\n🎉 FEATURE ELIMINATION ANALYSIS COMPLETE!")
        print(f"Recommended: {len(recommended_features)} features (from {len(X.columns)} original)")
        print(f"Performance maintained: AUC {recommended_metrics['auc']:.6f}")
    else:
        print(f"\n⚠️ Could not find suitable feature reduction while maintaining performance")

if __name__ == "__main__":
    main()