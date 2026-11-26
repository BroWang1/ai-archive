FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBUG_MODE=False \
    TZ=Asia/Shanghai

# opencv 运行所需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        tzdata \
    && ln -sf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data/lqa

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn gevent

# 默认 OCR 引擎 rapidocr: 离线可用、体积小 (约 15MB), 开箱即用
ARG OCR_ENGINE=rapidocr
RUN set -eux; \
    case "$OCR_ENGINE" in \
        rapidocr)  pip install --no-cache-dir rapidocr-onnxruntime ;; \
        paddleocr) pip install --no-cache-dir paddlepaddle paddleocr ;; \
        easyocr)   pip install --no-cache-dir easyocr ;; \
        none)      echo "不安装本地 OCR, 需在运行时指向外部 OCR 服务" ;; \
        *)         echo "未知 OCR_ENGINE=$OCR_ENGINE" >&2; exit 1 ;; \
    esac

COPY . .

# 预热: 构建期完成模型加载/下载, 避免首个请求超时
# 运行期默认 provider 跟随构建期引擎 (OCR_ENGINE=none 时即 OCR_PROVIDER=none)
ENV OCR_PROVIDER=${OCR_ENGINE}
RUN if [ "$OCR_ENGINE" != "none" ]; then \
        python -c "from common.ocr_provider import get_provider; print(get_provider().test_connection())" || true; \
    fi

EXPOSE 8086

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8086/health',timeout=5).status==200 else 1)" || exit 1

CMD ["gunicorn", "-c", "config/gunicorn_config.py", "portal:app", "--preload"]
