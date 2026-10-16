"""Run the Fish API server (fish-speech ``tools/api_server.py``) with less memory.

Runs under the Fish environment's Python with the fish-speech checkout as the
working directory; it imports nothing from Omnix.

fish-speech builds the model in float32 with random weights before reading the
checkpoint: about 20 GB of host memory for S2 Pro on top of its 9 GB of weights.
Next to the other Omnix services that exhausted the Windows commit limit and the
server crashed while loading. This wrapper builds the model on the meta device
(no memory, no random init); the checkpoint then supplies every parameter, and
the three tensors the constructor computes (rotary tables, causal mask) are
built again on the CPU exactly as the constructor does. Anything still on the
meta device afterwards (a parameter the checkpoint lacks) stops the server.

``--max-seq-len N`` (an option of this wrapper) sizes the model's context. S2
Pro's 32768 positions need a 4.8 GB KV cache and a 1 GB attention mask on the
GPU; a shorter context frees most of that. One request's prompt (reference
plus the text so far) must stay under N - 2048 tokens.
"""
from __future__ import annotations

import contextlib
import itertools
import runpy
import sys
from pathlib import Path


def _materialize_computed_buffers(model) -> None:
    import torch
    from fish_speech.models.text2semantic import llama

    config = model.config
    model.freqs_cis = llama.precompute_freqs_cis(config.max_seq_len, config.head_dim, config.rope_base)
    model.causal_mask = torch.tril(torch.ones(config.max_seq_len, config.max_seq_len, dtype=torch.bool))
    if hasattr(model, "fast_freqs_cis"):
        model.fast_freqs_cis = llama.precompute_freqs_cis(
            config.num_codebooks, config.fast_head_dim, config.rope_base,
        )
    unloaded = [name for name, tensor in itertools.chain(model.named_parameters(), model.named_buffers())
                if tensor.is_meta]
    if unloaded:
        raise RuntimeError(f"the checkpoint did not supply: {unloaded[:10]}")


def _patch_model_loading(max_seq_len: int | None) -> None:
    import torch
    from fish_speech.models.text2semantic import llama

    original = llama.BaseTransformer.from_pretrained
    model_classes = {name: getattr(llama, name) for name in ("DualARTransformer", "NaiveTransformer")}

    def on_meta(model_class):
        def build(config):
            with torch.device("meta"):
                return model_class(config)
        return build

    def from_pretrained(*args, **kwargs):
        if max_seq_len is not None and kwargs.get("max_length") is None:
            kwargs["max_length"] = max_seq_len
        if not kwargs.get("load_weights", args[1] if len(args) > 1 else False):
            return original(*args, **kwargs)
        with contextlib.ExitStack() as stack:
            for name, model_class in model_classes.items():
                setattr(llama, name, on_meta(model_class))
                stack.callback(setattr, llama, name, model_class)
            model = original(*args, **kwargs)
        _materialize_computed_buffers(model)
        return model

    llama.BaseTransformer.from_pretrained = staticmethod(from_pretrained)


def main() -> None:
    code_dir = Path.cwd()
    server = code_dir / "tools" / "api_server.py"
    if not server.is_file():
        raise SystemExit(f"run from the fish-speech checkout: {server} is missing")
    sys.path.insert(0, str(code_dir))
    arguments = sys.argv[1:]
    max_seq_len = None
    if "--max-seq-len" in arguments:
        index = arguments.index("--max-seq-len")
        max_seq_len = int(arguments[index + 1])
        del arguments[index:index + 2]
    _patch_model_loading(max_seq_len)
    sys.argv = [str(server), *arguments]
    runpy.run_path(str(server), run_name="__main__")


if __name__ == "__main__":
    main()
