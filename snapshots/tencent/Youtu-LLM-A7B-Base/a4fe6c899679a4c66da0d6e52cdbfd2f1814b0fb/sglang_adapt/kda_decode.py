"""Process-local H=4 specialization of SGLang's fused KDA decode kernel."""

import hashlib
import os
from pathlib import Path
import tempfile


def _h4_source(source: str) -> str:
    """Extend the known upstream dispatch; reject incompatible revisions."""
    source = source.replace(
        "kH == 3 || kH == 6 || kH == 12",
        "kH == 3 || kH == 4 || kH == 6 || kH == 12",
    ).replace(
        'local head counts 3, 6, or 12, got "',
        'local head counts 3, 4, 6, or 12, got "',
    )
    old = """auto kernel = kH == 3 ? select_kda_fused_decode_k3_kernel<3, kUsePDL>(use_lower_bound, tma_stages)
                          : (kH == 6 ? select_kda_fused_decode_k3_kernel<6, kUsePDL>(use_lower_bound, tma_stages)
                                     : select_kda_fused_decode_k3_kernel<12, kUsePDL>(use_lower_bound, tma_stages));"""
    new = """auto kernel = kH == 3 ? select_kda_fused_decode_k3_kernel<3, kUsePDL>(use_lower_bound, tma_stages)
                          : (kH == 4 ? select_kda_fused_decode_k3_kernel<4, kUsePDL>(use_lower_bound, tma_stages)
                          : (kH == 6 ? select_kda_fused_decode_k3_kernel<6, kUsePDL>(use_lower_bound, tma_stages)
                                     : select_kda_fused_decode_k3_kernel<12, kUsePDL>(use_lower_bound, tma_stages)));"""
    source = source.replace(old, new)
    if (
        "kH == 3 || kH == 4 || kH == 6 || kH == 12" not in source
        or new not in source
    ):
        raise RuntimeError("Unsupported SGLang fused KDA source revision")
    return source


def apply_kda_fused_decode_h4_patch() -> None:
    """Compile a private source copy; never modify the installed SGLang tree."""
    if os.environ.get("UTU_FUSED_KDA_DECODE", "0") != "1":
        return

    import sglang.kernels.ops.attention.kda_fused_decode as kda
    from sglang.kernels.jit.utils import (
        cache_once, is_arch_support_pdl, load_jit, make_cpp_args,
    )

    if 4 in kda._SUPPORTED_HEADS:
        return
    source = (
        Path(kda.__file__).resolve().parents[2]
        / "jit" / "csrc" / "attention" / "kda_fused_decode.cuh"
    )
    patched = _h4_source(source.read_text())
    digest = hashlib.sha256(patched.encode()).hexdigest()
    cache = Path(tempfile.gettempdir()) / f"utu-kda-{os.getuid()}" / digest
    cache.mkdir(parents=True, exist_ok=True)
    private_source = cache / "kda_fused_decode.cuh"
    # Different TP workers may initialize simultaneously. Publish complete
    # identical content atomically, so none can compile a half-written header.
    if not private_source.exists():
        with tempfile.NamedTemporaryFile(mode="w", dir=cache, delete=False) as tmp:
            tmp.write(patched)
        os.replace(tmp.name, private_source)

    @cache_once
    def _jit_h4_module():
        args = make_cpp_args(is_arch_support_pdl())
        return load_jit(
            "utu_kda_fused_decode_h4", *args,
            cuda_files=[str(private_source)],
            cuda_wrappers=[("run", f"KdaFusedDecodeKernel<{args}>::run")],
            extra_cuda_cflags=["-O3", "--use_fast_math"],
        )

    kda._jit_kda_fused_decode_module = _jit_h4_module
    kda._SUPPORTED_HEADS.add(4)
    print("[UTU] enabled fused KDA decode for H=4 (private JIT source).", flush=True)
