"""Pinned, no-paid-API CUDA inference adapter for the v2 Colab batch runner."""

from __future__ import annotations

import importlib.metadata
import platform
import time

SUPPORTED = {"Qwen/Qwen3-4B-Instruct-2507", "microsoft/Phi-4-mini-instruct"}


class CudaModel:
    def __init__(self, model_id: str, revision: str):
        if model_id not in SUPPORTED or len(revision) != 40:
            raise ValueError("Use a supported model and a pinned 40-character commit SHA")
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA GPU unavailable; do not run a CPU/offloaded pilot")
        self.model_id, self.revision, self.torch = model_id, revision, torch
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_id, revision=revision, trust_remote_code=False
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, revision=revision, torch_dtype=torch.float16,
            device_map="auto", trust_remote_code=False,
        )
        placement = getattr(self.model, "hf_device_map", {})
        if any(str(value) in ("cpu", "disk") for value in placement.values()):
            raise RuntimeError(f"Model offloaded outside CUDA: {placement}")
        if self.model.device.type != "cuda":
            raise RuntimeError(f"Model is not on CUDA: {self.model.device}")
        self.provenance = {
            "backend": "cuda_transformers",
            "model": model_id,
            "revision": revision,
            "python": platform.python_version(),
            "torch": torch.__version__,
            "transformers": importlib.metadata.version("transformers"),
            "accelerate": importlib.metadata.version("accelerate"),
            "huggingface_hub": importlib.metadata.version("huggingface-hub"),
            "fastapi": importlib.metadata.version("fastapi"),
            "httpx": importlib.metadata.version("httpx"),
            "pydantic": importlib.metadata.version("pydantic"),
            "cuda_device": torch.cuda.get_device_name(),
            "device_map": {key: str(value) for key, value in placement.items()},
        }

    def generate(self, system: str, user: str, max_new_tokens: int = 96) -> dict:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        prompt = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        self.torch.cuda.synchronize()
        start = time.perf_counter()
        with self.torch.inference_mode():
            output = self.model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )
        self.torch.cuda.synchronize()
        seconds = time.perf_counter() - start
        prompt_tokens = int(inputs["input_ids"].shape[1])
        completion_tokens = int(output.shape[1] - prompt_tokens)
        text = self.tokenizer.decode(output[0][prompt_tokens:], skip_special_tokens=True)
        return {
            "text": text,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "seconds": seconds,
            "peak_gpu_memory_bytes": self.torch.cuda.max_memory_allocated(),
        }
