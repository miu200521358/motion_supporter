# -*- coding: utf-8 -*-
#

from datetime import datetime
import sys
import os
import json
import glob
import traceback
from pathlib import Path
import re

from utils.MLogger import MLogger # noqa

logger = MLogger(__name__)


# リソースファイルのパス
def resource_path(relative):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative)
    return os.path.join(relative)


# ファイル履歴読み込み
def read_history(mydir_path):
    # ファイル履歴
    file_hitories = {"parent_vmd": [], "parent_pmx": [], "noise_vmd": [], "max": 50}

    # 履歴JSONファイルがあれば読み込み
    try:
        with open(os.path.join(mydir_path, 'history.json'), 'r') as f:
            file_hitories = json.load(f)
            # キーが揃っているかチェック
            for key in ["parent_vmd", "parent_pmx", "noise_vmd"]:
                if key not in file_hitories:
                    file_hitories[key] = []
            # 最大件数は常に上書き
            file_hitories["max"] = 50
    except Exception:
        file_hitories = {"parent_vmd": [], "parent_pmx": [], "noise_vmd": [], "max": 50}

    return file_hitories


def save_history(mydir_path, file_hitories):
    # 入力履歴を保存
    try:
        with open(os.path.join(mydir_path, 'history.json'), 'w') as f:
            json.dump(file_hitories, f, ensure_ascii=False)
    except Exception:
        logger.error("履歴ファイル保存失敗", traceback.format_exc())


# パス解決
def get_mydir_path(exec_path):
    logger.test("sys.argv %s", sys.argv)
    
    dir_path = Path(exec_path).parent if hasattr(sys, "frozen") else Path(__file__).parent
    logger.test("get_mydir_path: %s", get_mydir_path)

    return dir_path


# ディレクトリパス
def get_dir_path(base_file_path, is_print=True):
    if os.path.exists(base_file_path):
        file_path_list = [base_file_path]
    else:
        file_path_list = [p for p in glob.glob(base_file_path) if os.path.isfile(p)]

    if len(file_path_list) == 0:
        return ""

    try:
        # ファイルパスをオブジェクトとして解決し、親を取得する
        return str(Path(file_path_list[0]).resolve().parents[0])
    except Exception as e:
        logger.error("ファイルパスの解析に失敗しました。\nパスに使えない文字がないか確認してください。\nファイルパス: {0}\n\n{1}".format(base_file_path, e.with_traceback(sys.exc_info()[2])))
        raise e
    

# 全親移植VMD出力ファイルパス生成
# base_file_path: モーションVMDパス
# pmx_path: 変換先モデルPMXパス
# output_parent_vmd_path: 出力ファイルパス
def get_output_parent_vmd_path(base_file_path: str, pmx_path: str, output_parent_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_parent_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_parent_vmd_file_name, motion_parent_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_parent_vmd_path = os.path.join(motion_parent_vmd_dir_path, "{0}_{1}_{2:%Y%m%d_%H%M%S}{3}".format(motion_parent_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_parent_vmd_output_path(output_parent_vmd_path, motion_parent_vmd_dir_path, motion_parent_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_parent_vmd_path, 'w')
            os.remove(new_output_parent_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_parent_vmd_path

    return output_parent_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_parent_vmd_output_path(output_parent_vmd_path: str, motion_parent_vmd_dir_path: str, motion_parent_vmd_file_name: str, motion_parent_vmd_ext: str, rep_pmx_file_name: str):
    if not output_parent_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_parent_vmd_file_name = escape_filepath(os.path.join(motion_parent_vmd_dir_path, motion_parent_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_parent_vmd_ext = escape_filepath(motion_parent_vmd_ext)

    new_output_parent_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_parent_vmd_file_name, \
                                               escaped_rep_pmx_file_name, r"_?\w*_L\d+_\d{8}_\d{6}", escaped_motion_parent_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_parent_vmd_pattern, output_parent_vmd_path) is not None
    

# ゆらぎ複製VMD出力ファイルパス生成
# base_file_path: モーションVMDパス
# pmx_path: 変換先モデルPMXパス
# output_noise_vmd_path: 出力ファイルパス
def get_output_noise_vmd_path(base_file_path: str, output_noise_vmd_path: str, noise_size: int, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path):
        return ""

    # モーションVMDディレクトリパス
    motion_noise_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_noise_vmd_file_name, _ = os.path.splitext(os.path.basename(base_file_path))

    # 出力ファイルパス生成
    new_output_noise_vmd_path = os.path.join(motion_noise_vmd_dir_path, "{0}_N{1}_{2:%Y%m%d_%H%M%S}_nxxx{3}".format(motion_noise_vmd_file_name, noise_size, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_noise_vmd_output_path(output_noise_vmd_path, motion_noise_vmd_dir_path, motion_noise_vmd_file_name, noise_size, ".vmd"):

        try:
            open(new_output_noise_vmd_path, 'w')
            os.remove(new_output_noise_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_noise_vmd_path

    return output_noise_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_noise_vmd_output_path(output_noise_vmd_path: str, motion_noise_vmd_dir_path: str, motion_noise_vmd_file_name: str, noise_size: int, motion_noise_vmd_ext: str):
    if not output_noise_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_noise_vmd_file_name = escape_filepath(os.path.join(motion_noise_vmd_dir_path, motion_noise_vmd_file_name))
    escaped_motion_noise_vmd_ext = escape_filepath(motion_noise_vmd_ext)

    new_output_noise_vmd_pattern = re.compile(r'^%s_N\d+_\d{8}_\d{6}_nxxx%s$' % (escaped_motion_noise_vmd_file_name, escaped_motion_noise_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_noise_vmd_pattern, output_noise_vmd_path) is not None


def escape_filepath(path: str):
    path = path.replace("\\", "\\\\")
    path = path.replace("*", "\\*")
    path = path.replace("+", "\\+")
    path = path.replace(".", "\\.")
    path = path.replace("?", "\\?")
    path = path.replace("{", "\\{")
    path = path.replace("}", "\\}")
    path = path.replace("(", "\\(")
    path = path.replace(")", "\\)")
    path = path.replace("[", "\\[")
    path = path.replace("]", "\\]")
    path = path.replace("{", "\\{")
    path = path.replace("^", "\\^")
    path = path.replace("$", "\\$")
    path = path.replace("-", "\\-")
    path = path.replace("|", "\\|")
    path = path.replace("/", "\\/")

    return path
