---
license: apache-2.0
language: en
library_name: transformers
tags:
- text-compression
- token-classification
- modernbert
- lora
- kompress
base_model: answerdotai/ModernBERT-base
pipeline_tag: token-classification
---

# kompress-v2-base

Extractive prompt compressor for LLM proxies. Predicts a keep/drop label per
token; the surviving tokens form a compressed version of the input that
preserves meaning while reducing token count. It has no decoder: the output is
always a subsequence of the input, in the original order.

Based on **ModernBERT-base** (150M params) with a LoRA adapter
(4.4M trainable params, 2.9%) plus a custom dual head
(token classifier + 1-D span conv). Trained on 126,617 accepted Pipeline A+B
labels (compressor + faithfulness judge) across 17 sources: narrative, dialog,
code, agent traces, healthcare, finance, government, scientific, web, summary,
and tool-calling.

**Distribution.** Public. Apache 2.0, free for commercial use.

## Use with Headroom (recommended)

Headroom's proxy loads `onnx/kompress-int8-wo.onnx` from this repo and runs it
on CPU with ONNX Runtime; no torch needed. Point it at this repo:

```python
from headroom.transforms.kompress_compressor import KompressCompressor, KompressConfig

compressor = KompressCompressor(KompressConfig(model_id="chopratejas/kompress-v2-base"))
result = compressor.compress(long_tool_output)
print(result.compressed, result.compression_ratio)
```

Or serve it as an endpoint from this repository's `modal_jobs/modal_serve.py`
with `KOMPRESS_MODEL_ID=chopratejas/kompress-v2-base` set at deploy time.

## Use directly (PyTorch)

```python
import torch
from transformers import AutoModel, AutoTokenizer
from huggingface_hub import hf_hub_download

ckpt = torch.load(hf_hub_download("chopratejas/kompress-v2-base", "merged.pt"), map_location="cpu", weights_only=False)
encoder = AutoModel.from_pretrained("answerdotai/ModernBERT-base", attn_implementation="eager")
encoder.load_state_dict({k: v.float() for k, v in ckpt["encoder_state_dict"].items()})
H = encoder.config.hidden_size
token_head = torch.nn.Linear(H, 2)
span_conv = torch.nn.Sequential(torch.nn.Conv1d(H, 256, 5, padding=2), torch.nn.GELU(),
                                torch.nn.Conv1d(256, 1, 3, padding=1))
token_head.load_state_dict(ckpt["token_head_state_dict"])
span_conv.load_state_dict(ckpt["span_conv_state_dict"])

tok = AutoTokenizer.from_pretrained("chopratejas/kompress-v2-base")
enc = tok("The quick brown fox jumps over the lazy dog.", return_tensors="pt")
with torch.no_grad():
    h = encoder(**enc).last_hidden_state
    p_keep = torch.softmax(token_head(h), -1)[..., 1]
    span = torch.sigmoid(span_conv(h.transpose(1, 2)).squeeze(1))
    scores = p_keep * (0.5 + 0.5 * span)          # final_scores in [0, 1]
kept = enc["input_ids"][0][scores[0] >= 0.5]
print(tok.decode(kept, skip_special_tokens=True))
```

`model.safetensors` is the HF Trainer checkpoint of `HeadroomCompressorV2`
(PEFT-wrapped encoder + LoRA + heads) and loads through the `kompress` package;
`merged.pt` is the same model with LoRA folded into the encoder and is what the
ONNX exports were traced from.

## Threshold tuning

The model emits `final_scores ∈ [0, 1]` per subword. Raise the threshold
to compress harder; lower it to protect must-keep recall.

| Threshold | keep_rate | must_keep_recall | F1 | precision | recall |
|---|---|---|---|---|---|
| **0.30** | 0.946 (5% drop) | 0.997 | 0.942 | 0.920 | 0.964 |
| **0.40** | 0.910 (9% drop) | 0.994 | 0.933 | 0.929 | 0.937 |
| **0.50** (default) | 0.866 (13% drop) | 0.989 | 0.920 | 0.940 | 0.901 |
| **0.60** | 0.818 (18% drop) | 0.980 | 0.902 | 0.949 | 0.860 |
| **0.70** | 0.752 (25% drop) | 0.953 | 0.870 | 0.958 | 0.798 |

Measured on the held-out test split (n=12,697 rows, 16,827,490 scored subwords), checkpoint `best`, PyTorch bf16 on H100.

**Test split.** `dataset_v2_v2.1-f00` test: split by source document, exact and near duplicates of training rows removed. An earlier version of this card reported metrics on the v2.0 split, where 12.2% of test rows were byte-identical to training rows; those numbers were optimistic by roughly 0.02 F1 and have been replaced.
**At the default threshold (0.5):** F1 0.920, must-keep recall 0.989, keep rate 0.866 (13% of subwords removed).

On the subset the labeller actually compressed (it dropped at least 5% of the words, 6,559,681 subwords), at 0.5: F1 0.893, must-keep recall 0.986, keep rate 0.853. The rest of the split is text where almost every word should be kept, which inflates F1 for any model.

## Training data

- **126,617 labeled examples** after `min_drop_ratio=0.05` filtering and
  same-conversation packing (from 367,525 accepted labels).
- **Sources**: arxiv, pubmed-scientific, govreport, swe-smith, swe-gym-openhands, toolmind, xlam-fc, fineweb-edu, cnn-dailymail, xsum, glaive-fc, lmsys-chat, claude-code-sessions, meetingbank, the-stack-smol-md, samsum, swe-bench-verified.
- **Labeler**: DeepSeek-V4-Flash (compressor) + DeepSeek-V4-Pro (judge) with
  Pipeline A + B faithfulness loop. Hard-keep overlay enforces names, dates,
  numbers, URLs, code identifiers via GLiNER + regex + lexicons.
- **Bucket split**: short=48%, mid=31%, long=21% (max_length 8,192 native ModernBERT context).
- **Split**: train=126,617 / val=7,037 / test=7,037.
- Data card, per-source licences and the two non-commercial sources (4.78% of
  the corpus): `DATA.md` and `LICENSES.md` in the training repository.

## Training details

- Base: ModernBERT-base (150M params)
- Encoder fine-tuning: **LoRA** (r=16, alpha=32, target_modules=Wqkv/Wi/Wo)
- Heads: per-token CE (must-keep loss weight = 3.0) + 1-D span conv (BCE,
  weight 0.3 on total loss)
- Trainable params: 4.4M (2.9% of total)
- Optim: AdamW (lr=2e-4 cosine, warmup_ratio=0.06, weight_decay=0.01)
- Effective batch: 48; epochs: 3; bf16 with FlashAttention-2 + gradient checkpointing
- Hardware: 1×H100 80GB, ~39 min wall-clock

## Validation curve (n=7,037, threshold=0.5)

| step | epoch | eval_loss | F1 | must_keep_recall | keep_rate | precision |
|---|---|---|---|---|---|---|
| 2000 | 0.76 | 0.347 | 0.905 | 0.9849 | 0.867 | 0.868 |
| 4000 ← selected (best must_keep_recall) | 1.52 | 0.342 | 0.905 | 0.9909 | 0.900 | 0.852 |
| 6000 | 2.27 | 0.338 | 0.907 | 0.9865 | 0.881 | 0.863 |

The shipped weights are the checkpoint with the best validation must-keep recall (`metric_for_best_model`), evaluated every 2,000 steps.


## ONNX (what Headroom loads)

| artifact | size | notes |
|---|---|---|
| `onnx/kompress-int8-wo.onnx` | 274 MB | weight-only int8 (MatMulNBits), the default artifact; needs `onnxruntime>=1.24` |
| `onnx/kompress-fp32.onnx` | 601 MB | lossless reference |

Weight-only int8 agrees with fp32 on 99.6% of keep decisions. Headroom tries
`int8-wo` first and falls back to `fp32` on runtimes without the 8-bit kernel.

## Files in this repo

```
config.json                 # KompressV2Config + arch metadata
model.safetensors           # HF Trainer checkpoint (PEFT-wrapped encoder + LoRA + heads)
merged.pt                   # LoRA merged into the encoder; source of the ONNX exports
onnx/kompress-int8-wo.onnx  # weight-only int8, Headroom's default artifact
onnx/kompress-fp32.onnx     # lossless reference
adapter/                    # LoRA adapter + heads only, for stacking per-org adapters
  adapter/adapter_config.json
  adapter/adapter_model.safetensors
  token_head.pt
  span_conv.pt
tokenizer.json              # answerdotai/ModernBERT-base tokenizer
tokenizer_config.json
special_tokens_map.json
README.md                   # this file
```

## License

Apache 2.0 for the model artifact. ModernBERT-base is also Apache 2.0. Training-data
licences are per source; see `LICENSES.md` in the training repository.

## See also

- [`chopratejas/kompress-v2-base`](https://huggingface.co/chopratejas/kompress-v2-base)
  — ModernBERT-base variant (149M params, public)
- [`chopratejas/kompress-v2-large`](https://huggingface.co/chopratejas/kompress-v2-large)
  — ModernBERT-large variant (395M params, private/enterprise)
- Headroom proxy integration guide:
  [docs/CUSTOMER_QUICKSTART.md](https://github.com/chopratejas/kompress/blob/main/docs/CUSTOMER_QUICKSTART.md)
- Per-org fine-tuning (LoRA stacking):
  [docs/DEPLOYMENT_STRATEGY.md](https://github.com/chopratejas/kompress/blob/main/docs/DEPLOYMENT_STRATEGY.md)
