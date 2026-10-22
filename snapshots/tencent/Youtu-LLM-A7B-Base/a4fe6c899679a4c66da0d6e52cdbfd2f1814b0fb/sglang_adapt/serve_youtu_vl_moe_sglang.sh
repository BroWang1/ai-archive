#!/usr/bin/env bash
# 启动 UTU-VL Tiny MoE Pro 的 sglang server。
#
# 用法：
#   bash serve_youtu_vl_moe_sglang.sh
#   TP_SIZE=4 PORT=8001 bash serve_youtu_vl_moe_sglang.sh
#   MODEL_PATH=/path/to/hf_ckpt bash serve_youtu_vl_moe_sglang.sh
#   bash serve_youtu_vl_moe_sglang.sh --model-path /path --port 31042 --tp-size 8
#
# 同时支持环境变量与 CLI 参数（CLI 优先）。CLI 兼容 run_sglang_infer_eval.sh
# 的调用约定（它只传 --tag / --port），--tag 在此被忽略。

set -euo pipefail

DEFAULT_TP_SIZE="${TP_SIZE:-8}"
DEFAULT_EP_SIZE="${EP_SIZE:-$DEFAULT_TP_SIZE}"
# External data-parallel replicas. Total GPUs = TP * DP (e.g. TP=4,DP=2 -> 8).
# Do not enable dp-attention here: multimodal sgl_shm_mm_* can crash.
DEFAULT_DP_SIZE="${DP_SIZE:-${DP:-1}}"
DEFAULT_PORT="${PORT:-8000}"
DEFAULT_MODEL_PATH="${MODEL_PATH:-/path/to/utuvl_120b_kda_hf}"
MODEL_PATH="${MODEL_PATH:-$DEFAULT_MODEL_PATH}"
MOE_TP_SIZE="${DEFAULT_TP_SIZE}"
MOE_EP_SIZE="${DEFAULT_EP_SIZE}"
MOE_DP_SIZE="${DEFAULT_DP_SIZE}"
MOE_PORT="${DEFAULT_PORT}"
MOE_MEM_FRACTION_STATIC="${MEM_FRACTION_STATIC:-0.78}"
MOE_SERVED_MODEL_NAME="${SERVED_MODEL_NAME:-utu-vl-120b-kda-moe}"
MOE_DISABLE_CUDA_GRAPH="${DISABLE_CUDA_GRAPH:-0}"
# 训练和 checkpoint 权重均为 BF16。config 若未声明 dtype，SGLang 的 auto
# 会把它当作 FP32 模型并默认降到 FP16，长上下文 prefill 可能产生 NaN。
MOE_DTYPE="${DTYPE:-bfloat16}"
MOE_KV_CACHE_DTYPE="${KV_CACHE_DTYPE:-bfloat16}"
MOE_CONTEXT_LENGTH="${CONTEXT_LENGTH:-}"
MOE_CUDA_GRAPH_CONFIG="${CUDA_GRAPH_CONFIG:-}"
MOE_DISABLE_CHUNKED_PREFIX_CACHE="${DISABLE_CHUNKED_PREFIX_CACHE:-0}"
# Off by default: event_loop_overlap + ViT .item() can hang DP0 on image prefill.
MOE_DISABLE_OVERLAP_SCHEDULE="${DISABLE_OVERLAP_SCHEDULE:-1}"
# prefill chunk / 单次 prefill 上限。默认翻倍：8192 -> 16384 / 16384 -> 32768，
# 让每个 prefill batch 装下更多序列（原来 #new-seq 只有 5），提升 MoE prefill MFU。
# loglikelihood 任务（短序列、无生成）尤其受益。KV 余量充足（334k），不会 OOM。
MOE_CHUNKED_PREFILL_SIZE="${CHUNKED_PREFILL_SIZE:-16384}"
MOE_MAX_PREFILL_TOKENS="${MAX_PREFILL_TOKENS:-32768}"

# ---- CLI 参数解析（CLI > env > 默认） ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model-path)        MODEL_PATH="$2"; shift 2;;
        --port)              MOE_PORT="$2"; shift 2;;
        --tp-size|--tp)      MOE_TP_SIZE="$2"; shift 2;;
        --ep-size|--ep)      MOE_EP_SIZE="$2"; shift 2;;
        --dp-size|--dp)      MOE_DP_SIZE="$2"; shift 2;;
        --mem-fraction-static) MOE_MEM_FRACTION_STATIC="$2"; shift 2;;
        --chunked-prefill-size) MOE_CHUNKED_PREFILL_SIZE="$2"; shift 2;;
        --max-prefill-tokens) MOE_MAX_PREFILL_TOKENS="$2"; shift 2;;
        --served-model-name) MOE_SERVED_MODEL_NAME="$2"; shift 2;;
        --dtype)              MOE_DTYPE="$2"; shift 2;;
        --kv-cache-dtype)     MOE_KV_CACHE_DTYPE="$2"; shift 2;;
        --context-length)     MOE_CONTEXT_LENGTH="$2"; shift 2;;
        --cuda-graph-config)  MOE_CUDA_GRAPH_CONFIG="$2"; shift 2;;
        --disable-cuda-graph) MOE_DISABLE_CUDA_GRAPH=1; shift;;
        --disable-chunked-prefix-cache) MOE_DISABLE_CHUNKED_PREFIX_CACHE=1; shift;;
        --disable-overlap-schedule) MOE_DISABLE_OVERLAP_SCHEDULE=1; shift;;
        --tag)               shift 2;;  # 兼容 run_sglang_infer_eval.sh，忽略
        --host)              shift 2;;  # host 固定 0.0.0.0，忽略
        -h|--help) sed -n '2,12p' "$0"; exit 0;;
        *) echo "[ERROR] unknown arg: $1" >&2; exit 1;;
    esac
done

if [[ -n "${MOE_CONTEXT_LENGTH}" ]] && ! [[ "${MOE_CONTEXT_LENGTH}" =~ ^[1-9][0-9]*$ ]]; then
    echo "[ERROR] --context-length / CONTEXT_LENGTH must be a positive integer, got: ${MOE_CONTEXT_LENGTH}" >&2
    exit 1
fi

# 避免继承外部 SageMaker handler 路径
unset CUSTOM_FASTAPI_PING_HANDLER
unset CUSTOM_FASTAPI_INVOCATION_HANDLER
unset CUSTOM_SCRIPT_FILENAME

# sglang 的 deep_gemm 需从 pip 安装的 nvidia cu13 wheels 加载 libnvrtc.so.13，
# 该路径不在默认动态链接搜索路径中。把 site-packages/nvidia/*/lib 全部加入。
# Optional SGLANG_ENV=/path/to/env; otherwise use python3/python on PATH.
if [[ -n "${SGLANG_ENV:-${VLMEVAL_SGLANG_ENV:-}}" ]]; then
    SGLANG_ENV="${SGLANG_ENV:-${VLMEVAL_SGLANG_ENV}}"
else
    __py_on_path="$(command -v python3 || command -v python || true)"
    if [[ -z "${__py_on_path}" ]]; then
        echo "[ERROR] python3/python not on PATH; set SGLANG_ENV to a conda env that has sglang." >&2
        exit 1
    fi
    SGLANG_ENV="$(cd "$(dirname "${__py_on_path}")/.." && pwd)"
fi
if [[ ! -x "${SGLANG_ENV}/bin/python" ]]; then
    echo "[ERROR] SGLANG_ENV does not contain an executable python: ${SGLANG_ENV}/bin/python" >&2
    echo "[HINT] Set SGLANG_ENV=/path/to/the-validated-sglang-conda-env, or put that env first on PATH." >&2
    exit 1
fi

__conda_env="${SGLANG_ENV}"
__nvidia_lib_dirs=()
shopt -s nullglob
__nvidia_lib_dirs=("${__conda_env}"/lib/python*/site-packages/nvidia/*/lib)
shopt -u nullglob
if [[ "${#__nvidia_lib_dirs[@]}" -gt 0 ]]; then
    printf -v __nvidia_libs '%s:' "${__nvidia_lib_dirs[@]}"
    export LD_LIBRARY_PATH="${__nvidia_libs}${LD_LIBRARY_PATH:-}"
fi
unset __nvidia_lib_dirs __nvidia_libs

# ── 注册 sglang 外部模型 / processor ──────────────────────────────────────────
# PYTHONPATH 指向 youtu_vl_moe 目录本身（而非 utu_v2_init），使外部 package 名为
# `sglang_adapt`，避免触发 youtu_vl_moe/__init__.py 里 HF modeling 的重依赖 import。
__adapt_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${__adapt_dir}${PYTHONPATH:+:${PYTHONPATH}}"

export SGLANG_EXTERNAL_MODEL_PACKAGE=sglang_adapt
export SGLANG_EXTERNAL_MM_PROCESSOR_PACKAGE=sglang_adapt
# 多模态 arch 白名单（告诉 sglang 该 architecture 是多模态模型）
export SGLANG_EXTERNAL_MM_MODEL_ARCH=YoutuVLMoEForConditionalGeneration

export HF_HUB_OFFLINE=1

# Validated optimization defaults; numerical comparisons can disable each path.
# pipeline_utuvl_moe.sh exports the same flags so smoke/text/VLM share this path.
# Router granularity comes from the converted config.json
# (moe_router_token_level_modality), not from these fusion switches.
export SGLANG_OPT_FUSE_SWIGLU_INTERLEAVED="${SGLANG_OPT_FUSE_SWIGLU_INTERLEAVED:-1}"
# Shared-expert side-stream overlap: on by default (set 0 to disable).
export UTU_SHARED_EXPERT_OVERLAP="${UTU_SHARED_EXPERT_OVERLAP:-1}"
# FP32 conv + fused decode changes logprobs; it is not bitwise equivalent.
export UTU_FUSED_KDA_DECODE="${UTU_FUSED_KDA_DECODE:-1}"
export UTU_FUSED_EXPERT_REMAP="${UTU_FUSED_EXPERT_REMAP:-1}"
export UTU_SMALL_NUMEL_MOE_ALIGN="${UTU_SMALL_NUMEL_MOE_ALIGN:-1}"
# Undo the multimodal guard above disabling prefill CUDA graph; helps text and
# image prefills alike below SGLang's 2048-token MLA capture ceiling (-70 ms on
# a 720p single-image request).  Off by default because it is not numerically
# equivalent: piecewise capture changes MLA kernel dispatch, and 256 greedy
# steps off a 1024-token prompt diverge at step 10 (max |dlogprob| 2.1e-1).
# The graphed schedule is itself reproducible -- two runs were bit-identical --
# so this is a different valid ordering, not nondeterminism.
export UTU_PREFILL_CUDA_GRAPH="${UTU_PREFILL_CUDA_GRAPH:-0}"

# 必须用本 package 的 launch 入口（而非 python -m sglang.launch_server）：
# YoutuVLMoEConfig.text_config 返回 self，会导致 sglang 的
# normalize_rope_scaling_compat 无限递归 RecursionError。launch.py 在 sglang
# 任何 config 加载之前施加防环 patch，再走标准 run_server 流程。
#
# 激活 SGLang conda env（提供 sglang / torch / transformers）。
# test_utuvl_sglang.sh 在 start_sglang 之后才为 client 激活 env，serve 子进程
# 继承的 PATH 可能指向其他 conda env 的 python（无 sglang），所以这里必须自行激活。
#
# 重要：仅靠 `conda activate` 不可靠——当继承的 PATH 已前置了另一个 conda env
# (如 eval env) 时，conda activate 会设 CONDA_PREFIX 但不把 env/bin 前置到 PATH
# (conda 的 deactivate/activate 逻辑被既有 conda env 干扰)，导致 `python` 仍解析到
# 错误 env 而 ModuleNotFoundError: No module named 'sglang'。所以这里无条件把
# env/bin 前置到 PATH（最可靠），并显式用 env 的 python 解释器。
__conda_sh="$(cd "${__conda_env}/../.." && pwd)/etc/profile.d/conda.sh"
if [[ -f "${__conda_sh}" ]]; then
    set +e +u
    source "${__conda_sh}" 2>/dev/null || true
    conda activate "${__conda_env}" >/dev/null 2>&1 || true
    set -euo pipefail
fi
# 无条件前置 env/bin，确保 `python` 解析到 SGLang env（不依赖 conda activate 的 PATH 副作用）
export PATH="${__conda_env}/bin:${PATH}"
# 显式 pin python 解释器，双重保险
__py="${__conda_env}/bin/python"

# flashinfer import happens before SGLang can start.  Fail early with the
# actionable package versions instead of emitting a deep import traceback.
# No cubin package is also valid (FlashInfer can use JIT/artifact paths), but
# an installed cubin package must match flashinfer-python exactly.
if [[ "${SGLANG_SKIP_FLASHINFER_PREFLIGHT:-0}" != "1" ]]; then
    if ! "${__py}" - <<'PY'
import sys
from importlib.metadata import PackageNotFoundError, version

def package_version(*names):
    for name in names:
        try:
            return version(name)
        except PackageNotFoundError:
            pass
    return None

flashinfer_version = package_version("flashinfer-python", "flashinfer")
cubin_version = package_version("flashinfer-cubin")
if flashinfer_version is None:
    print("[ERROR] flashinfer-python is not installed in the selected SGLANG_ENV.", file=sys.stderr)
    sys.exit(1)
if cubin_version is not None and cubin_version != flashinfer_version:
    print(
        "[ERROR] Incompatible FlashInfer packages in SGLANG_ENV: "
        f"flashinfer-python={flashinfer_version}, flashinfer-cubin={cubin_version}.",
        file=sys.stderr,
    )
    print(
        "[HINT] Remove/replace the stale flashinfer-cubin package so it matches "
        "flashinfer-python, then verify with: python -m flashinfer show-config",
        file=sys.stderr,
    )
    sys.exit(2)
PY
    then
        echo "[HINT] Do not use FLASHINFER_DISABLE_VERSION_CHECK=1 for a benchmark run unless this exact package pair has been validated." >&2
        exit 1
    fi
fi

__extra_server_args=()
if [[ -n "${MOE_CONTEXT_LENGTH}" ]]; then
    echo "[INFO] overriding context-length=${MOE_CONTEXT_LENGTH} (config max_position_embeddings may be smaller)"
    export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN="${SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN:-1}"
    __extra_server_args+=(--context-length "${MOE_CONTEXT_LENGTH}")
fi
if [[ -n "${MOE_CUDA_GRAPH_CONFIG}" ]]; then
    if ! "${__py}" - "${MOE_CUDA_GRAPH_CONFIG}" <<'PY'
import json
import sys

try:
    value = json.loads(sys.argv[1])
except json.JSONDecodeError as exc:
    print(f"[ERROR] Invalid CUDA_GRAPH_CONFIG / --cuda-graph-config JSON: {exc}", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(value, dict):
    print("[ERROR] CUDA_GRAPH_CONFIG must be a JSON object.", file=sys.stderr)
    raise SystemExit(1)
PY
    then
        exit 1
    fi
    __extra_server_args+=(--cuda-graph-config "${MOE_CUDA_GRAPH_CONFIG}")
fi
if [[ "${MOE_DISABLE_CHUNKED_PREFIX_CACHE}" == "1" ]]; then
    __extra_server_args+=(--disable-chunked-prefix-cache)
fi
if [[ "${MOE_DISABLE_OVERLAP_SCHEDULE}" == "1" ]]; then
    __extra_server_args+=(--disable-overlap-schedule)
fi
if [[ "${MOE_DISABLE_CUDA_GRAPH}" == "1" ]]; then
    __extra_server_args+=(--disable-cuda-graph)
fi
# Optional FA3 decode KV sharding; page_size=1 is required by the bridge.
if [[ -n "${DCP_SIZE:-}" && "${DCP_SIZE}" != "1" ]]; then
    __extra_server_args+=(--dcp-size "${DCP_SIZE}")
fi
# External DP replicas (TP*DP GPUs). No --enable-dp-attention: that path
# hits a cross-rank multimodal shared-memory broadcast bug on image inputs.
if [[ -n "${MOE_DP_SIZE}" && "${MOE_DP_SIZE}" -gt 1 ]]; then
    echo "[INFO] enabling external DP: tp=${MOE_TP_SIZE} ep=${MOE_EP_SIZE} dp=${MOE_DP_SIZE} (gpus=$((MOE_TP_SIZE * MOE_DP_SIZE)))"
    __extra_server_args+=(--dp "${MOE_DP_SIZE}")
fi

"${__py}" -m sglang_adapt.launch \
    --model-path "${MODEL_PATH}" \
    --tp-size "${MOE_TP_SIZE}" \
    --ep-size "${MOE_EP_SIZE}" \
    --trust-remote-code \
    --dtype "${MOE_DTYPE}" \
    --kv-cache-dtype "${MOE_KV_CACHE_DTYPE}" \
    ${__extra_server_args[@]+"${__extra_server_args[@]}"} \
    --chat-template "${MODEL_PATH}/chat_template.jinja" \
    --host 0.0.0.0 \
    --port "${MOE_PORT}" \
    --mem-fraction-static "${MOE_MEM_FRACTION_STATIC}" \
    --served-model-name "${MOE_SERVED_MODEL_NAME}" \
    --chunked-prefill-size "${MOE_CHUNKED_PREFILL_SIZE}" \
    --max-prefill-tokens "${MOE_MAX_PREFILL_TOKENS}" \
    --page-size 1
