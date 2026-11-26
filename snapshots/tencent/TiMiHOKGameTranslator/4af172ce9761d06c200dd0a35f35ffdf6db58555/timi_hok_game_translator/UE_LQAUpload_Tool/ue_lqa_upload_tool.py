#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
UE LQA Dump 数据上传工具
==========================

一个通用的、由配置驱动的 LQA UI-dump 数据上传工具

它会扫描数据目录下的 dump 记录 (由 LQA 采集工具生成, 每条记录是一个子目录,
内含一份快照 JSON + 一张截图 PNG, 可选包含背景 PNG / 贴图 PNG),
把 JSON 规范化为 LQA 平台期望的结构, 然后通过平台 HTTP API 逐条上传

平台 API 约定
-------------
- POST /api/user/login     仅用于开发环境的自动登录 (未配置 token 时使用)
- POST /api/data/entity    创建数据实体, 返回 data_id
- POST /api/upload_file    上传文件, 返回远端 file_path
- PATCH /api/data/entity   关联截图 / module_id / resource_version

鉴权方式
-------------
- 如果配置了 token, 则每个请求都会携带 ``LQA-Authorization`` 请求头
- 如果未配置 token, 则回退到开发环境自动登录接口
  (``POST /api/user/login``), 方便对接本地开发服务器

所有行为均通过 ``LQAConfig.ini`` 控制 (参见随附的示例配置)
服务器地址、凭据和本地路径都不会硬编码在代码中
"""

import argparse
import configparser
import glob
import json
import logging
import os
import sys

import requests


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #
class Config:
    """运行时配置, 从 INI 文件加载"""

    def __init__(self, ini_path):
        self.ini_path = ini_path
        parser = configparser.ConfigParser()
        if not parser.read(ini_path, encoding="utf-8"):
            raise FileNotFoundError(f"配置文件不存在或无法读取: {ini_path}")

        # [server]
        self.host = parser.get("server", "host", fallback="").strip().rstrip("/")
        self.token = parser.get("server", "token", fallback="").strip()

        # [project]
        self.project_id = parser.getint("project", "project_id")
        self.job_id = parser.getint("project", "job_id")
        module_id = parser.get("project", "module_id", fallback="").strip()
        self.module_id = int(module_id) if module_id else None
        resource_version = parser.get("project", "resource_version", fallback="").strip()
        self.resource_version = resource_version or None

        # [data]
        self.root_path = parser.get("data", "root_path").strip()
        # flat = 仅遍历一级子目录
        # recursive = 遍历整棵目录树, 并挑选出所有包含 dump 的目录
        self.scan_mode = parser.get("data", "scan_mode", fallback="recursive").strip().lower()

        # [options]
        self.require_background = parser.getboolean("options", "require_background", fallback=False)
        self.embed_background = parser.getboolean("options", "embed_background", fallback=False)
        self.require_texture = parser.getboolean("options", "require_texture", fallback=False)
        self.retry_times = parser.getint("options", "retry_times", fallback=1)

        if not self.host:
            raise ValueError("配置项 [server].host 不能为空")


# --------------------------------------------------------------------------- #
# 平台客户端
# --------------------------------------------------------------------------- #
class LQAClient:
    """LQA 平台 HTTP API 的轻量封装"""

    def __init__(self, cfg):
        self.cfg = cfg
        self.session = requests.Session()
        self._auth_header = {"LQA-Authorization": cfg.token} if cfg.token else {}

    def login_if_needed(self):
        """未配置 token 时, 尝试调用开发环境自动登录接口"""
        if self.cfg.token:
            logging.info("使用 Token 鉴权, 跳过登录")
            return True
        url = self.cfg.host + "/api/user/login"
        try:
            resp = self.session.post(url, timeout=30)
            logging.info("dev 自动登录: HTTP %s", resp.status_code)
            return resp.status_code == 200
        except requests.RequestException as exc:
            logging.error("dev 自动登录失败: %s", exc)
            return False

    def upload_json(self, json_content):
        """创建数据实体, 返回其 data_id (失败时返回 None)"""
        url = self.cfg.host + "/api/data/entity"
        payload = {
            "project_id": self.cfg.project_id,
            "job_id": self.cfg.job_id,
            "data": json_content,
        }
        try:
            resp = self.session.post(url, headers=self._auth_header, json=payload, timeout=120)
        except requests.RequestException as exc:
            logging.error("upload_json 请求异常: %s", exc)
            return None
        if resp.status_code != 200:
            logging.error("upload_json HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        if body.get("code") != 0:
            logging.error("upload_json 业务错误: %s", body.get("msg"))
            return None
        return body["data"]["data"]["id"]

    def upload_file(self, file_path):
        """上传文件, 返回远端 file_path (失败时返回 None)"""
        url = self.cfg.host + "/api/upload_file"
        try:
            with open(file_path, "rb") as fp:
                resp = self.session.post(
                    url, headers=self._auth_header, files={"file": fp}, timeout=120
                )
        except (requests.RequestException, OSError) as exc:
            logging.error("upload_file 请求异常: %s", exc)
            return None
        if resp.status_code != 200:
            logging.error("upload_file HTTP %s: %s", resp.status_code, resp.text[:200])
            return None
        body = resp.json()
        if body.get("code") != 0:
            logging.error("upload_file 业务错误: %s", body.get("msg"))
            return None
        return body["data"]["file_path"]

    def update_data(self, data_id, shot_img_path):
        """为一个数据实体关联截图, 以及可选的 module_id / resource_version"""
        url = self.cfg.host + "/api/data/entity"
        payload = {"id": int(data_id), "shot_img_path": shot_img_path}
        if self.cfg.module_id is not None:
            payload["module_id"] = self.cfg.module_id
        if self.cfg.resource_version is not None:
            payload["resource_version"] = self.cfg.resource_version
        try:
            resp = self.session.patch(url, headers=self._auth_header, json=payload, timeout=60)
        except requests.RequestException as exc:
            logging.error("update_data 请求异常: %s", exc)
            return False
        if resp.status_code != 200:
            logging.error("update_data HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        body = resp.json()
        if body.get("code") != 0:
            logging.error("update_data 业务错误: %s", body.get("msg"))
            return False
        return True


# --------------------------------------------------------------------------- #
# 工具函数
# --------------------------------------------------------------------------- #
# 会破坏严格 JSON 解析器的非有限数值 token, 统一替换为 "0"
_NAN_INF_TOKENS = ("-nan(ind)", "nan(ind)", "-nan", "nan", "-inf", "inf")


def sanitize_json_text(text):
    """把 nan/inf token (部分 C++ 序列化器会输出) 替换为 0"""
    for token in _NAN_INF_TOKENS:
        text = text.replace(token, "0")
    return text


def normalise_content(content, json_name):
    """
    把原始 dump 字典重整为 LQA 平台期望的结构

    所有转换都是防御式的: 仅当某个键存在时才移动/重命名它,
    因此同一份代码对包含或不包含这些字段的 dump 都适用
    """
    if "meta" in content:
        content["gameData"] = content.pop("meta")
    game_data = content.setdefault("gameData", {})
    if "version" in game_data:
        game_data["resourceVersion"] = game_data.pop("version")
    if "device" in game_data:
        content["phoneType"] = game_data.pop("device")
    content["name"] = json_name
    return content


def png_to_hex(png_path):
    with open(png_path, "rb") as fp:
        return fp.read().hex()


def find_record_assets(directory, cfg):
    """
    检查一个目录, 判断它是否是有效的 dump 记录

    返回 (json_file, screenshot_file, background_file), 其中 background_file
    可能为 None; 若该目录不是有效记录, 则返回 (None, None, None)
    """
    if not os.path.isdir(directory):
        return None, None, None

    json_files = glob.glob(os.path.join(directory, "*.json"))
    screenshot_files = glob.glob(os.path.join(directory, "LQA_ScreenShot_*.png"))
    background_files = glob.glob(os.path.join(directory, "*_BG.png"))
    texture_files = glob.glob(os.path.join(directory, "Texture_*.png"))

    # 不要把我们自己的产物 (upload.json) 当作 dump 快照
    json_files = [f for f in json_files if os.path.basename(f).lower() != "upload.json"]

    if not json_files or not screenshot_files:
        return None, None, None
    if cfg.require_background and not background_files:
        return None, None, None
    if cfg.require_texture and not texture_files:
        return None, None, None

    background = background_files[0] if background_files else None
    return json_files[0], screenshot_files[0], background


def discover_records(cfg):
    """逐个产出配置根目录下所有有效的记录目录"""
    root = cfg.root_path
    if not os.path.isdir(root):
        logging.error("数据根目录不存在: %s", root)
        return []

    candidates = []
    if cfg.scan_mode == "flat":
        for entry in sorted(os.listdir(root)):
            abs_path = os.path.join(root, entry)
            if os.path.isdir(abs_path):
                candidates.append(abs_path)
    else:  # recursive
        for current, dirs, _files in os.walk(root):
            candidates.append(current)

    records = []
    for directory in candidates:
        json_file, shot_file, bg_file = find_record_assets(directory, cfg)
        if json_file:
            records.append((directory, json_file, shot_file, bg_file))

    # 按创建时间排序, 保证多次运行结果稳定可复现
    records.sort(key=lambda item: os.path.getctime(item[0]))
    return records


def process_record(client, cfg, directory, json_file, shot_file, bg_file):
    """上传单条记录, 成功则返回平台 data_id, 失败返回 None"""
    json_name = os.path.basename(json_file)
    try:
        with open(json_file, "r", encoding="utf8") as fp:
            raw = sanitize_json_text(fp.read())
        content = json.loads(raw)
    except (OSError, ValueError) as exc:
        logging.error("读取/解析 JSON 失败 %s: %s", json_file, exc)
        return None

    content = normalise_content(content, json_name)

    if cfg.embed_background and bg_file:
        try:
            content["bg_data"] = png_to_hex(bg_file)
        except OSError as exc:
            logging.warning("背景图读取失败, 跳过 bg_data %s: %s", bg_file, exc)

    for attempt in range(1, cfg.retry_times + 1):
        data_id = client.upload_json(content)
        if not data_id:
            logging.warning("创建数据实体失败 (第 %d/%d 次): %s", attempt, cfg.retry_times, directory)
            continue
        remote_shot = client.upload_file(shot_file)
        if not remote_shot:
            logging.warning("截图上传失败 (第 %d/%d 次): %s", attempt, cfg.retry_times, directory)
            continue
        if client.update_data(data_id, remote_shot):
            logging.info("上传成功: data_id=%s  %s", data_id, directory)
            return data_id
        logging.warning("更新数据实体失败 (第 %d/%d 次): %s", attempt, cfg.retry_times, directory)
    return None


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser(description="LQA UI-dump 上传工具")
    default_ini = os.path.join(os.path.dirname(os.path.abspath(__file__)), "LQAConfig.ini")
    parser.add_argument("-c", "--config", default=default_ini,
                        help="配置文件路径 (默认: 脚本同目录的 LQAConfig.ini)")
    parser.add_argument("--root", default=None,
                        help="覆盖配置中的数据根目录 [data].root_path")
    parser.add_argument("-v", "--verbose", action="store_true", help="输出调试日志")
    return parser.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        cfg = Config(args.config)
    except (FileNotFoundError, ValueError, configparser.Error) as exc:
        logging.error("配置加载失败: %s", exc)
        return 2

    if args.root:
        cfg.root_path = args.root

    logging.info("平台地址: %s", cfg.host)
    logging.info("数据根目录: %s (模式: %s)", cfg.root_path, cfg.scan_mode)

    client = LQAClient(cfg)
    if not client.login_if_needed():
        logging.error("鉴权失败, 终止")
        return 1

    records = discover_records(cfg)
    if not records:
        logging.warning("未发现任何有效的 dump 记录目录")
        return 0
    logging.info("发现 %d 条待上传记录", len(records))

    results = {}
    for directory, json_file, shot_file, bg_file in records:
        data_id = process_record(client, cfg, directory, json_file, shot_file, bg_file)
        if data_id:
            results[str(data_id)] = directory

    # 持久化 data_id -> 源目录的映射 (与已有内容合并)
    out_path = os.path.join(cfg.root_path, "upload.json")
    existing = {}
    if os.path.exists(out_path):
        try:
            with open(out_path, "r", encoding="utf-8") as fp:
                existing = json.load(fp)
        except (OSError, ValueError):
            existing = {}
    existing.update(results)
    try:
        with open(out_path, "w", encoding="utf-8") as fp:
            json.dump(existing, fp, ensure_ascii=False, indent=4)
        logging.info("结果映射已写入: %s", out_path)
    except OSError as exc:
        logging.error("写入结果映射失败: %s", exc)

    logging.info("完成: 成功 %d / 总计 %d", len(results), len(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
