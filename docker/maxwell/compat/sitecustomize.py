"""Local GTX 750 Ti policy, loaded by Python via PYTHONPATH.

Keep CUDA for separation; CTranslate2 4.8 requires a newer CUDA stack, so
transcription and alignment use CPU. No upstream analyzer files are modified.
"""
import os

if os.environ.get("NIGHTINGALE_GPU_COMPAT", "1") == "1":
    import torch

    # Maxwell has no flash attention kernels or tensor cores.
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    torch.backends.cudnn.enabled = False

    # ONNX is CPU-only here. Its default preload selects leftover CUDA 12
    # libraries, poisoning CUDA 11's BLAS handles before the first operation.
    import onnxruntime
    onnxruntime.preload_dlls = lambda *args, **kwargs: None

    from audio_separator.separator.uvr_lib_v5.roformer import attend
    from torch.nn.attention import SDPBackend

    attend._sdpa_backends = lambda config: [SDPBackend.MATH]

    # Deserialize on CPU to avoid two copies of the 900 MB checkpoint in VRAM.
    from audio_separator.separator.roformer.roformer_loader import RoformerLoader

    _load_roformer = RoformerLoader.load_model

    def _load_roformer_on_cpu(self, model_path, config, device="cpu"):
        return _load_roformer(self, model_path, config, device="cpu")

    RoformerLoader.load_model = _load_roformer_on_cpu

    from audio_separator.separator import Separator

    _separator_init = Separator.__init__

    def _small_separator(self, *args, **kwargs):
        kwargs["mdxc_params"] = {
            "segment_size": int(os.environ.get("NIGHTINGALE_GPU_SEGMENT", "128")),
            "override_model_segment_size": True,
            "batch_size": 1,
            "overlap": 4,
            "pitch_shift": 0,
        }
        kwargs["use_autocast"] = False
        kwargs["use_native_fp16"] = False
        kwargs["use_torch_compile"] = False
        return _separator_init(self, *args, **kwargs)

    Separator.__init__ = _small_separator

    import pipeline
    import gpu
    import whisper_compat

    _compute_type_for = whisper_compat.compute_type_for
    whisper_compat.compute_type_for = lambda device: "int8" if device == "cpu" else _compute_type_for(device)

    _move_to_cpu = gpu.move_to_cpu

    def _release_separator_models(model):
        for attr in ("model_instance", "model_run"):
            inner = getattr(model, attr, None)
            if inner is not None and inner is not model:
                _release_separator_models(inner)
        _move_to_cpu(model)

    gpu.move_to_cpu = _release_separator_models

    import demucs.apply
    _demucs_apply = demucs.apply.apply_model

    def _small_demucs(model, mix, **kwargs):
        if str(kwargs.get("device", mix.device)).startswith("cuda"):
            kwargs["segment"] = 2.0
        return _demucs_apply(model, mix, **kwargs)

    demucs.apply.apply_model = _small_demucs

    _transcribe_or_align = pipeline.transcribe_or_align

    def _cpu_transcribe_or_align(vocals_path, audio_path, device, **kwargs):
        print("[nightingale:LOG] GTX 750 Ti: separation on CUDA; transcription/alignment on CPU", flush=True)
        return _transcribe_or_align(vocals_path, audio_path, "cpu", **kwargs)

    pipeline.transcribe_or_align = _cpu_transcribe_or_align
