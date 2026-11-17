"""Reproduce the trained model's weights from the embedded dataset.

Phase 4's model (aacl/models/iris.py) is trained, not hand-authored, and
its committed weights are a claim anyone can check: this script retrains
multinomial logistic regression on the embedded Iris train split with
the frozen recipe and compares the result against the committed literal,
exactly — float for float. It prints the trained weights either way, so
a reader can see what the model is, and exits nonzero if retraining and
the literal disagree.
"""
import sys

from aacl.models import iris
from aacl.models.iris_data import EVAL_ROWS


def main():
    weights, bias = iris.train()
    exact = weights == iris.TRAINED_WEIGHTS and bias == iris.TRAINED_BIAS
    correct = sum(1 for x, y in EVAL_ROWS
                  if iris.label(weights, bias, x) == y)
    print(f"recipe: full-batch gradient descent, lr={iris.LEARNING_RATE}, "
          f"epochs={iris.EPOCHS}, zero init, {len(iris.TRAIN_ROWS)} train rows")
    print(f"eval accuracy (fp64, held-out split): {correct}/{len(EVAL_ROWS)}")
    print(f"weights reproduced exactly: {exact}")
    print(f"TRAINED_WEIGHTS = {weights!r}")
    print(f"TRAINED_BIAS = {bias!r}")
    if not exact:
        print("MISMATCH: retraining does not reproduce the committed weights",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
