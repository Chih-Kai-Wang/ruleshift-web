"""Local Apple MLX decision-model adapter for v2 development only."""

from __future__ import annotations

import importlib.metadata
import platform
import time

from ruleshift.agents import MODEL_ID, MODEL_REVISION


class MlxDevModel:
    def __init__(self):
        import mlx.core as mx
        from huggingface_hub import snapshot_download
        from mlx_lm import load

        path = snapshot_download(MODEL_ID, revision=MODEL_REVISION)
        self.model, self.tokenizer = load(path)
        self.mx = mx
        self.provenance = {
            "backend": "mlx_dev_not_cuda",
            "model": MODEL_ID,
            "revision": MODEL_REVISION,
            "python": platform.python_version(),
            "mlx_lm": importlib.metadata.version("mlx-lm"),
        }

    def generate(self, system: str, user: str, max_new_tokens: int = 96) -> dict:
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True,
        )
        start = time.perf_counter()
        answer = generate(self.model, self.tokenizer, prompt=prompt,
                          max_tokens=max_new_tokens, sampler=make_sampler(temp=0), verbose=False)
        return {
            "text": answer,
            "prompt_tokens": len(self.tokenizer.encode(prompt)),
            "completion_tokens": len(self.tokenizer.encode(answer)),
            "seconds": time.perf_counter() - start,
            "peak_memory_bytes": self.mx.get_peak_memory(),
        }
