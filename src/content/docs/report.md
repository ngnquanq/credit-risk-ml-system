---
title: "Fairness without the protected attribute: an end-to-end study in a credit-decisioning platform"
description: Technical report (draft). What happens to discrimination and accuracy when a production credit model stops using gender, and its proxies stay?
sidebar:
  label: Fairness without the protected attribute
---

**Status: draft.** The method and protocol are fixed. The **results are pending** until the two models below have been trained and evaluated on the frozen split. Numbers on this page will only come from that run.

<div class="abstract">

**Abstract.** Credit-scoring models are often made "fair" by removing protected attributes such as gender from their inputs. This *fairness through unawareness* is known to be insufficient, because other inputs can act as proxies [5, 6].

We measure the effect in a complete decisioning platform rather than on a model alone. Our platform is open source, built on the Home Credit Default Risk data [1], and covers change-data capture, streaming feature engineering, a feature store, model serving, a three-band decision policy and human review. We train the same gradient-boosted model [3] on two versioned feature sets: `legacy-v1`, which includes `CODE_GENDER`, and `v2-no-gender`, which does not. We then compare:
- **discrimination**: ROC AUC and PR AUC;
- **calibration**: Brier score and expected calibration error;
- **decision outcomes** under the platform's thresholds;
- **group fairness**: demographic parity and equal-opportunity differences between genders, where gender is kept only as an audit attribute [4, 5].

<span class="pending">Results: pending.</span>

</div>

## 1. Introduction

A lender that scores applications must be able to explain each decision and show that it does not discriminate. Removing protected attributes is the simplest policy to state and to audit. Whether it achieves anything depends on the rest of the feature set, and on how scores turn into decisions.

This report asks three questions:
- **RQ1.** How much predictive performance does the model lose without `CODE_GENDER`?
- **RQ2.** Do approval rates and true-positive rates between genders move closer together, or do proxies keep the gap?
- **RQ3.** How do the answers change once the three-band policy routes borderline cases to human review?

## 2. Related work

Group fairness criteria, and the impossibility of satisfying all of them at once, are surveyed in [5]. Equality of opportunity is introduced in [4].

Proxy discrimination was described early in discrimination-aware data mining [6]: dropping a sensitive attribute does not remove the discrimination carried by correlated attributes.

For explanations, we use SHAP values [2]. On the engineering side, we follow [7] for the production ML lifecycle, and the related practice of keeping a single source of truth for features.

## 3. System

The platform is described in the [architecture section](/credit-risk-ml-system/architecture/at-a-glance/). The parts that matter for this study are:
- **Versioned feature sets.** A catalog defines each feature and tags protected attributes and proxies. Training refuses a set that uses them unless the set is marked legacy.
- **Decision policy.** Applications with a predicted default probability below 0.25 are approved, those above 0.35 are rejected, and the rest go to an underwriter. Missing features or a scoring failure also go to review, never to approval.
- **Reason codes.** Each automated decision stores its top SHAP contributions, mapped to plain-language reasons.

## 4. Method

| | Setting |
|---|---|
| Data | Home Credit Default Risk, `application_train` with its binary default label [1] |
| Split | One stratified hold-out split with a fixed seed, frozen for both models |
| Feature sets | `legacy-v1` (24 inputs, includes `CODE_GENDER`) and `v2-no-gender` (the same without it) |
| Model | XGBoost [3]: 300 trees, depth 4, learning rate 0.05, the same preprocessing pipeline for both sets |
| Performance | ROC AUC, PR AUC, Brier score, expected calibration error (10 bins), F1 |
| Decisions | Approve, review and reject rates under the 0.25 / 0.35 bands |
| Fairness (audit only) | Demographic parity difference and equal-opportunity difference between genders, with bootstrap confidence intervals |
| Proxies | For each input: mutual information with `CODE_GENDER`, and the AUC of predicting gender from the `v2-no-gender` inputs |

Both models are trained with the repository's `train_register.py` and registered in MLflow with the feature-set version and its digest, so every number can be traced to a model version.

## 5. Results

<span class="pending">Pending: the two training runs and the evaluation on the frozen split.</span>

## 6. Threats to validity

- **Construct.** The data has a gender field but no other protected attributes, and its labels reflect past lending decisions (selection bias).
- **Internal.** A single split and one model family. Hyperparameters are not re-tuned per feature set.
- **External.** The data comes from one lender and one period, and the decision thresholds are illustrative, not a published cost matrix.
- **Legal.** Fairness definitions are statistical. Which one applies, and how it is enforced, depends on the jurisdiction. This report does not give legal advice.

## 7. Reproducibility

All code, the feature catalog, the decision policy and the evaluation live in the repository. The page footer names the commit this site was built from.

## References

<ol class="references">
<li>Home Credit Group. <em>Home Credit Default Risk</em>. Kaggle competition, 2018. <a href="https://www.kaggle.com/competitions/home-credit-default-risk">kaggle.com/competitions/home-credit-default-risk</a></li>
<li>S. M. Lundberg and S.-I. Lee. A unified approach to interpreting model predictions. <em>Advances in Neural Information Processing Systems 30 (NeurIPS)</em>, 2017.</li>
<li>T. Chen and C. Guestrin. XGBoost: A scalable tree boosting system. <em>Proceedings of the 22nd ACM SIGKDD Conference</em>, 2016.</li>
<li>M. Hardt, E. Price and N. Srebro. Equality of opportunity in supervised learning. <em>Advances in Neural Information Processing Systems 29 (NeurIPS)</em>, 2016.</li>
<li>S. Barocas, M. Hardt and A. Narayanan. <em>Fairness and Machine Learning: Limitations and Opportunities</em>. MIT Press, 2023. <a href="https://fairmlbook.org">fairmlbook.org</a></li>
<li>D. Pedreshi, S. Ruggieri and F. Turini. Discrimination-aware data mining. <em>Proceedings of the 14th ACM SIGKDD Conference</em>, 2008.</li>
<li>B. Wilson. <em>Machine Learning Engineering in Action</em>. Manning, 2022.</li>
</ol>
