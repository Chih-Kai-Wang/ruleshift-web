# Third-party components

RuleShift-Web code is Apache-2.0. Dependencies retain their own licenses;
the Python dependency snapshot is recorded in `uv.lock`.

- The formal study used public weights for
  [Qwen3-4B-Instruct-2507](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
  and [Phi-4-mini-instruct](https://huggingface.co/microsoft/Phi-4-mini-instruct).
  Their exact revisions are in `research/www2027/G3_FROZEN_PROTOCOL.json`.
  Model weights and tokenizer files are not included here and retain their
  respective upstream terms.
- CUDA inference used PyTorch, Transformers, Accelerate, and Hugging Face Hub;
  exact versions are in the frozen protocol. Local development also used MLX
  and MLX LM. None of these packages is vendored into this snapshot.
- This repository includes references to external papers and Web standards;
  those remain the works of their respective authors and publishers.

The included synthetic tasks and experiment records are licensed only to the
extent of the author's own rights; see `DATA_LICENSE.md`. No affiliation with
the model developers or cited research groups is implied.
