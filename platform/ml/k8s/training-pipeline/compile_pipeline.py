from kfp.compiler import Compiler
from pipeline import training_pipeline


if __name__ == "__main__":
    # Emit KFP v2 IR as YAML so UIs that require .yaml accept it.
    out = "services/ml/k8s/training-pipeline/training_pipeline.yaml"
    Compiler().compile(training_pipeline, package_path=out)
    print(f"Wrote {out}")
