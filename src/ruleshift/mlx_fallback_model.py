"""Pinned local MLX feasibility adapter; never pooled with CUDA results."""

from __future__ import annotations

import importlib.metadata
import platform
import time

MLX_MODELS = {
    "qwen": ("mlx-community/Qwen3-4B-Instruct-2507-4bit",
             "50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b"),
    "phi": ("mlx-community/Phi-4-mini-instruct-4bit",
            "ac1c269cb4222a4e136a3d09edad301056c1f36a"),
}


class LocalMlxModel:
    def __init__(self, model_key: str):
        if model_key not in MLX_MODELS:
            raise ValueError("Unknown pinned local MLX model")
        import mlx.core as mx
        from huggingface_hub import snapshot_download
        from mlx_lm import load

        model_id, revision = MLX_MODELS[model_key]
        path = snapshot_download(model_id, revision=revision, local_files_only=True)
        self.model, self.tokenizer = load(path)
        self.mx = mx
        self.provenance = {
            "backend": "local_mlx_4bit_development_not_cuda",
            "model": model_id,
            "revision": revision,
            "python": platform.python_version(),
            "mlx": importlib.metadata.version("mlx"),
            "mlx_lm": importlib.metadata.version("mlx-lm"),
            "quantization": "4bit",
        }

    def generate(self, system: str, user: str, max_new_tokens: int = 96) -> dict:
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        prompt = self.tokenizer.apply_chat_template(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tokenize=False, add_generation_prompt=True,
        )
        started = time.perf_counter()
        response = generate(self.model, self.tokenizer, prompt=prompt,
                            max_tokens=max_new_tokens, sampler=make_sampler(temp=0),
                            verbose=False)
        return {
            "text": response,
            "prompt_tokens": len(self.tokenizer.encode(prompt)),
            "completion_tokens": len(self.tokenizer.encode(response)),
            "seconds": time.perf_counter() - started,
            "peak_memory_bytes": self.mx.get_peak_memory(),
        }
