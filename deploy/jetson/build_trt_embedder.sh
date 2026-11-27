#!/usr/bin/env bash
# Build TensorRT FP16 engine for BAAI/bge-small-en-v1.5 on Jetson Orin Nano (SM 8.7, T12/#166).
set -euo pipefail

OUT_DIR="${1:-$HOME/models/bge-small-trt}"
ONNX_PATH="$OUT_DIR/bge-small.onnx"
ENGINE_PATH="$OUT_DIR/bge-small-fp16.engine"
TRTEXEC="${TRTEXEC:-/usr/src/tensorrt/bin/trtexec}"

mkdir -p "$OUT_DIR"

if [[ ! -f "$ONNX_PATH" ]]; then
  echo "Exporting BAAI/bge-small-en-v1.5 to $ONNX_PATH ..."
  python3 - <<'PY' "$ONNX_PATH"
import sys
import torch
from transformers import AutoModel, AutoTokenizer

out_path = sys.argv[1]
model_id = "BAAI/bge-small-en-v1.5"
tok = AutoTokenizer.from_pretrained(model_id)
model = AutoModel.from_pretrained(model_id).eval()
sample = tok("Perihelion Reach relay quarter status", return_tensors="pt")
torch.onnx.export(
    model,
    (sample["input_ids"], sample["attention_mask"]),
    out_path,
    input_names=["input_ids", "attention_mask"],
    output_names=["last_hidden_state"],
    dynamic_axes={
        "input_ids": {0: "batch", 1: "seq"},
        "attention_mask": {0: "batch", 1: "seq"},
        "last_hidden_state": {0: "batch", 1: "seq"},
    },
    opset_version=17,
)
PY
fi

echo "Compiling TensorRT FP16 engine -> $ENGINE_PATH ..."
"$TRTEXEC" \
  --onnx="$ONNX_PATH" \
  --saveEngine="$ENGINE_PATH" \
  --fp16 \
  --minShapes=input_ids:1x8,attention_mask:1x8 \
  --optShapes=input_ids:8x64,attention_mask:8x64 \
  --maxShapes=input_ids:32x128,attention_mask:32x128

echo "Done: $ENGINE_PATH"
