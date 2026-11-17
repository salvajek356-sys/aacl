"""The trained model: iris-logreg-v1 (Phase 4).

Phase 0's model was hand-authored — four weights a person picked. This one
is *trained*: multinomial logistic regression (softmax regression) over
the embedded Iris dataset (models/iris_data.py), fitted by full-batch
gradient descent on the 90-row train split. Nothing about it is tuned per
run: zero initialization, a fixed learning rate, a fixed epoch count, the
train split in its fixed order, plain Python floats. Training is therefore
a deterministic function of the dataset, and `train()` reproduces the
committed weights below exactly — a test holds it to that, and
train_iris.py at the repo root is the same check for humans.

The committed weights are the artifact's source. Their digest (computed
in models/registry.py like every model's) names the floating-point
artifact; the transformation service (optimization/quantization.py)
derives the int8 artifact from them.
"""
import math

from .iris_data import CLASSES, TRAIN_ROWS

MODEL_ID = "iris-logreg-v1"

# The training recipe, frozen. Changing any of these changes the weights,
# which changes the source digest, which renames every artifact — as it
# should: a different model is a different model.
LEARNING_RATE = 0.1
EPOCHS = 1000

# The trained parameters, exactly as train() produces them. Kept as a
# literal so the artifact exists without running training at import; the
# reproducibility test proves the literal and the trainer agree.
TRAINED_WEIGHTS = [
    [0.937748863422325, 2.0090812230614308, -2.850843335610274, -1.2684574203299845],
    [0.6947118153961879, -0.11569865738162181, -0.07348526432292153, -1.3797828366503873],
    [-1.6324606788185134, -1.8933825656798078, 2.924328599933199, 2.6482402569803787],
]
TRAINED_BIAS = [0.45391600014344385, 0.5874571629701295, -1.041373163113574]

MODEL = {"id": MODEL_ID, "kind": "multinomial-logreg",
         "weights": TRAINED_WEIGHTS, "bias": TRAINED_BIAS,
         "classes": list(CLASSES)}


def train(rows=TRAIN_ROWS, learning_rate=LEARNING_RATE, epochs=EPOCHS):
    """Fit softmax regression by full-batch gradient descent and return
    (weights, bias). Deterministic: same rows, same recipe, same floats,
    every run — this is the function the committed weights came from."""
    weights = [[0.0] * 4 for _ in range(3)]
    bias = [0.0] * 3
    n = len(rows)
    for _ in range(epochs):
        grad_w = [[0.0] * 4 for _ in range(3)]
        grad_b = [0.0] * 3
        for x, y in rows:
            logits = [sum(weights[c][j] * x[j] for j in range(4)) + bias[c]
                      for c in range(3)]
            peak = max(logits)
            exps = [math.exp(v - peak) for v in logits]
            total = sum(exps)
            for c in range(3):
                diff = exps[c] / total - (1.0 if c == y else 0.0)
                grad_b[c] += diff
                for j in range(4):
                    grad_w[c][j] += diff * x[j]
        for c in range(3):
            bias[c] -= learning_rate * grad_b[c] / n
            for j in range(4):
                weights[c][j] -= learning_rate * grad_w[c][j] / n
    return weights, bias


def logits(weights, bias, values, cast=float):
    """The class scores for one input. `cast` applies a precision's
    rounding at every step — the CPU backend passes its fp32 rounding for
    the fp32 artifact and plain float for fp64, exactly the discipline the
    demo model's math has always used."""
    scores = []
    for c in range(len(bias)):
        score = cast(bias[c])
        for j in range(len(values)):
            score = cast(score + cast(cast(weights[c][j]) * cast(values[j])))
        scores.append(score)
    return scores


def label(weights, bias, values, cast=float):
    scores = logits(weights, bias, values, cast)
    return max(range(len(scores)), key=lambda c: scores[c])
