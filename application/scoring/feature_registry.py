"""
Centralized Feature Registry - Single Source of Truth

This file defines ALL features used in the ML pipeline, eliminating inconsistencies
between Feast queries, model schemas, and feature mappings.

Usage:
    from feature_registry import FeatureRegistry
    
    registry = FeatureRegistry()
    feast_refs = registry.get_feast_feature_refs()
    model_columns = registry.get_model_expected_columns()
    mapping = registry.get_feast_to_model_mapping()
"""

from typing import Dict, List, Optional, NamedTuple
from enum import Enum
from dataclasses import dataclass


class FeatureSource(Enum):
    """Feature source types in the streaming pipeline."""
    APPLICATION = "application_features"
    EXTERNAL = "external_features"
    DWH = "dwh_features"


class FeatureType(Enum):
    """Feature data types for validation."""
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    BOOLEAN = "boolean"


@dataclass
class FeatureSpec:
    """Complete specification for a single feature."""
    feast_name: str          # Name in Feast feature store
    model_name: str          # Name expected by ML model
    source: FeatureSource    # Which feature view contains this feature
    feature_type: FeatureType # Data type for validation
    description: str         # Human-readable description
    required: bool = True    # Whether this feature is mandatory
    
    @property
    def feast_ref(self) -> str:
        """Full Feast reference: 'view_name:feature_name'"""
        return f"{self.source.value}:{self.feast_name}"


class FeatureRegistry:
    """Centralized registry of all features used in the ML pipeline."""
    
    # ========================================================================
    # MASTER FEATURE DEFINITIONS - SINGLE SOURCE OF TRUTH
    # ========================================================================
    
    _FEATURES: List[FeatureSpec] = [
        # Application Features (from Flink pipeline)
        FeatureSpec("cnt_children", "CNT_CHILDREN", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Number of children"),
        FeatureSpec("amt_income_total", "AMT_INCOME_TOTAL", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Total income amount"),
        FeatureSpec("amt_credit", "AMT_CREDIT", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Credit amount requested"),
        FeatureSpec("amt_annuity", "AMT_ANNUITY", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Loan annuity amount"),
        FeatureSpec("amt_goods_price", "AMT_GOODS_PRICE", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Price of goods for which loan is given"),
        FeatureSpec("days_birth", "DAYS_BIRTH", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Days before application when client was born (negative)"),
        FeatureSpec("days_employed", "DAYS_EMPLOYED", FeatureSource.APPLICATION, FeatureType.NUMERIC, "Days before application when client started current employment"),
        FeatureSpec("code_gender", "CODE_GENDER", FeatureSource.APPLICATION, FeatureType.CATEGORICAL, "Applicant gender"),
        FeatureSpec("name_education_type", "NAME_EDUCATION_TYPE", FeatureSource.APPLICATION, FeatureType.CATEGORICAL, "Education level"),
        FeatureSpec("name_family_status", "NAME_FAMILY_STATUS", FeatureSource.APPLICATION, FeatureType.CATEGORICAL, "Family status"),
        FeatureSpec("name_income_type", "NAME_INCOME_TYPE", FeatureSource.APPLICATION, FeatureType.CATEGORICAL, "Income type"),
        FeatureSpec("organization_type", "ORGANIZATION_TYPE", FeatureSource.APPLICATION, FeatureType.CATEGORICAL, "Type of organization where client works"),
        
        # External/Bureau Features (from training data)
        FeatureSpec("ext_source_1", "EXT_SOURCE_1", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "External risk score 1"),
        FeatureSpec("ext_source_2", "EXT_SOURCE_2", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "External risk score 2"),
        FeatureSpec("ext_source_3", "EXT_SOURCE_3", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "External risk score 3"),
        FeatureSpec("bureau_debt_to_credit_ratio", "BUREAU_DEBT_TO_CREDIT_RATIO", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "Bureau debt to credit ratio"),
        FeatureSpec("bureau_active_credit_sum", "BUREAU_ACTIVE_CREDIT_SUM", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "Active credit sum from bureau"),
        FeatureSpec("bureau_amt_max_overdue_ever", "BUREAU_AMT_MAX_OVERDUE_EVER", FeatureSource.EXTERNAL, FeatureType.NUMERIC, "Maximum overdue amount from bureau"),
        
        # DWH Features (from training data only)
        FeatureSpec("pos_mean_contract_length", "POS_MEAN_CONTRACT_LENGTH", FeatureSource.DWH, FeatureType.NUMERIC, "Mean POS contract length"),
        FeatureSpec("pos_latest_month", "POS_LATEST_MONTH", FeatureSource.DWH, FeatureType.NUMERIC, "Latest POS contract month"),
        FeatureSpec("pos_total_months_observed", "POS_TOTAL_MONTHS_OBSERVED", FeatureSource.DWH, FeatureType.NUMERIC, "Total POS months observed"),
        FeatureSpec("prev_annuity_mean", "PREV_ANNUITY_MEAN", FeatureSource.DWH, FeatureType.NUMERIC, "Mean previous application annuity"),
        FeatureSpec("prev_goods_to_credit_ratio", "PREV_GOODS_TO_CREDIT_RATIO", FeatureSource.DWH, FeatureType.NUMERIC, "Previous goods to credit ratio"),
        FeatureSpec("prev_refusal_rate", "PREV_REFUSAL_RATE", FeatureSource.DWH, FeatureType.NUMERIC, "Previous application refusal rate"),
    ]
    
    def __init__(self):
        """Initialize the feature registry."""
        self._validate_registry()
    
    def _validate_registry(self) -> None:
        """Validate the feature registry for consistency."""
        feast_names = set()
        model_names = set()
        
        for feature in self._FEATURES:
            # Check for duplicate feast names
            if feature.feast_name in feast_names:
                raise ValueError(f"Duplicate feast name: {feature.feast_name}")
            feast_names.add(feature.feast_name)
            
            # Check for duplicate model names  
            if feature.model_name in model_names:
                raise ValueError(f"Duplicate model name: {feature.model_name}")
            model_names.add(feature.model_name)
    
    # ========================================================================
    # AUTO-GENERATED CONFIGURATIONS (from master definitions above)
    # ========================================================================
    
    def get_feast_feature_refs(self, required_only: bool = True) -> List[str]:
        """Get Feast feature references in 'view:feature' format."""
        features = [f for f in self._FEATURES if not required_only or f.required]
        return [f.feast_ref for f in features]
    
    def get_feast_feature_refs_string(self, required_only: bool = True) -> str:
        """Get Feast feature references as comma-separated string (for config)."""
        return ",".join(self.get_feast_feature_refs(required_only))
    
    def get_model_expected_columns(self, required_only: bool = True) -> List[str]:
        """Get model column names in the order expected by ML model."""
        features = [f for f in self._FEATURES if not required_only or f.required]
        return [f.model_name for f in features]
    
    def get_feast_to_model_mapping(self) -> Dict[str, str]:
        """Get mapping from Feast names to model names."""
        return {f.feast_name: f.model_name for f in self._FEATURES}
    
    def get_feature_by_feast_name(self, feast_name: str) -> Optional[FeatureSpec]:
        """Get feature specification by Feast name."""
        for feature in self._FEATURES:
            if feature.feast_name == feast_name:
                return feature
        return None
    
    def get_feature_by_model_name(self, model_name: str) -> Optional[FeatureSpec]:
        """Get feature specification by model name."""
        for feature in self._FEATURES:
            if feature.model_name == model_name:
                return feature
        return None
    
    def get_features_by_source(self, source: FeatureSource) -> List[FeatureSpec]:
        """Get all features from a specific source."""
        return [f for f in self._FEATURES if f.source == source]
    
    def get_feature_summary(self) -> Dict[str, Dict]:
        """Get summary statistics about the feature registry."""
        total = len(self._FEATURES)
        required = len([f for f in self._FEATURES if f.required])
        by_source = {}
        by_type = {}
        
        for feature in self._FEATURES:
            source_name = feature.source.value
            type_name = feature.feature_type.value
            by_source[source_name] = by_source.get(source_name, 0) + 1
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        return {
            "total_features": total,
            "required_features": required,
            "optional_features": total - required,
            "by_source": by_source,
            "by_type": by_type
        }
    
    def validate_feast_result(self, feast_result: Dict[str, List]) -> Dict[str, List[str]]:
        """Validate Feast query result against expected features."""
        issues = {
            "missing_required": [],
            "unexpected_features": [],
            "type_mismatches": []
        }
        
        expected_refs = set(self.get_feast_feature_refs(required_only=True))
        received_refs = set(feast_result.keys())
        
        # Check for missing required features
        missing = expected_refs - received_refs
        issues["missing_required"] = list(missing)
        
        # Check for unexpected features
        unexpected = received_refs - set(self.get_feast_feature_refs(required_only=False))
        issues["unexpected_features"] = list(unexpected)
        
        return issues


# Global registry instance
FEATURE_REGISTRY = FeatureRegistry()


# ========================================================================
# CONVENIENCE FUNCTIONS (backwards compatibility)
# ========================================================================

def get_feast_feature_refs() -> str:
    """Get comma-separated Feast feature references (for config.py)."""
    return FEATURE_REGISTRY.get_feast_feature_refs_string(required_only=False)

def get_model_expected_columns() -> List[str]:
    """Get model column names (for service.py)."""
    return FEATURE_REGISTRY.get_model_expected_columns(required_only=False)

def get_feast_to_model_mapping() -> Dict[str, str]:
    """Get feature name mapping (for service.py)."""
    return FEATURE_REGISTRY.get_feast_to_model_mapping()


if __name__ == "__main__":
    # Print feature registry summary
    registry = FeatureRegistry()
    summary = registry.get_feature_summary()
    
    print("🎯 Feature Registry Summary")
    print("=" * 50)
    print(f"Total features: {summary['total_features']}")
    print(f"Required features: {summary['required_features']}")
    print(f"Optional features: {summary['optional_features']}")
    print("\nBy source:")
    for source, count in summary['by_source'].items():
        print(f"  {source}: {count}")
    print("\nBy type:")
    for type_name, count in summary['by_type'].items():
        print(f"  {type_name}: {count}")
    
    print("\n🔗 Generated Configurations:")
    print("-" * 30)
    print("Feast feature refs:", registry.get_feast_feature_refs_string()[:100] + "...")
    print("Model columns:", registry.get_model_expected_columns()[:5], "...")
    print("Mapping sample:", dict(list(registry.get_feast_to_model_mapping().items())[:3]))
