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
import _pickle as cPickle

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
    base_file_hitories = {"parent_vmd": [], "parent_pmx": [], "noise_vmd": [], "multi_split_vmd": [], "multi_split_pmx": [], \
                          "multi_join_vmd": [], "multi_join_pmx": [], "leg_fk2ik_vmd": [], "leg_fk2ik_pmx": [], "arm_ik2fk_vmd": [], "arm_ik2fk_pmx": [], "arm_ik2fk_pmx_fk": [], \
                          "smooth_vmd": [], "smooth_pmx": [], "arm_twist_off_vmd": [], "arm_twist_off_pmx": [], "max": 50}
    file_hitories = cPickle.loads(cPickle.dumps(base_file_hitories, -1))

    # 履歴JSONファイルがあれば読み込み
    try:
        with open(os.path.join(mydir_path, 'history.json'), 'r', encoding="utf-8") as f:
            file_hitories = json.load(f)
            # キーが揃っているかチェック
            for key in base_file_hitories.keys():
                if key not in file_hitories:
                    file_hitories[key] = []
            # 最大件数は常に上書き
            file_hitories["max"] = 50
    except Exception:
        # UTF-8で読み込めなかった場合、デフォルトで読み込んでUTF-8変換
        try:
            with open(os.path.join(mydir_path, 'history.json'), 'r') as f:
                file_hitories = json.load(f)
                # キーが揃っているかチェック
                for key in base_file_hitories.keys():
                    if key not in file_hitories:
                        file_hitories[key] = []
                # 最大件数は常に上書き
                file_hitories["max"] = 50
            
            # 一旦UTF-8で出力
            save_history(mydir_path, file_hitories)

            # UTF-8で読み込みし直し
            return read_history(mydir_path)
        except Exception:
            file_hitories = cPickle.loads(cPickle.dumps(base_file_hitories, -1))

    return file_hitories


def save_history(mydir_path, file_hitories):
    # 入力履歴を保存
    try:
        with open(os.path.join(mydir_path, 'history.json'), 'w', encoding="utf-8") as f:
            json.dump(file_hitories, f, ensure_ascii=False)
    except Exception as e:
        logger.error("履歴ファイルの保存に失敗しました", e, decoration=MLogger.DECORATION_BOX)


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
    new_output_parent_vmd_path = os.path.join(motion_parent_vmd_dir_path, "{0}_{1}Z_{2:%Y%m%d_%H%M%S}{3}".format(motion_parent_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

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
                                               escaped_rep_pmx_file_name, r"Z_\d{8}_\d{6}", escaped_motion_parent_vmd_ext))
    
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
    new_output_noise_vmd_path = os.path.join(motion_noise_vmd_dir_path, "{0}_N{1}_{2:%Y%m%d_%H%M%S}_axxx_nxxx{3}".format(motion_noise_vmd_file_name, noise_size, datetime.now(), ".vmd"))

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

    new_output_noise_vmd_pattern = re.compile(r'^%s_N\d+_\d{8}_\d{6}_axxx_nxxx%s$' % (escaped_motion_noise_vmd_file_name, escaped_motion_noise_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_noise_vmd_pattern, output_noise_vmd_path) is not None


# IK焼き込みVMD出力ファイルパス生成
# base_file_path: モーションVMDパス
# pmx_path: 変換先モデルPMXパス
# output_arm_ik2fk_vmd_path: 出力ファイルパス
def get_output_arm_ik2fk_vmd_path(base_file_path: str, pmx_path: str, output_arm_ik2fk_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_arm_ik2fk_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_arm_ik2fk_vmd_file_name, motion_arm_ik2fk_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_arm_ik2fk_vmd_path = os.path.join(motion_arm_ik2fk_vmd_dir_path, "{0}_{1}_{2:%Y%m%d_%H%M%S}{3}".format(motion_arm_ik2fk_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_arm_ik2fk_vmd_output_path(output_arm_ik2fk_vmd_path, motion_arm_ik2fk_vmd_dir_path, motion_arm_ik2fk_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_arm_ik2fk_vmd_path, 'w')
            os.remove(new_output_arm_ik2fk_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_arm_ik2fk_vmd_path

    return output_arm_ik2fk_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_arm_ik2fk_vmd_output_path(output_arm_ik2fk_vmd_path: str, motion_arm_ik2fk_vmd_dir_path: str, motion_arm_ik2fk_vmd_file_name: str, motion_arm_ik2fk_vmd_ext: str, rep_pmx_file_name: str):
    if not output_arm_ik2fk_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_arm_ik2fk_vmd_file_name = escape_filepath(os.path.join(motion_arm_ik2fk_vmd_dir_path, motion_arm_ik2fk_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_arm_ik2fk_vmd_ext = escape_filepath(motion_arm_ik2fk_vmd_ext)

    new_output_arm_ik2fk_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_arm_ik2fk_vmd_file_name, \
                                              escaped_rep_pmx_file_name, r"_?\w*_L\d+_\d{8}_\d{6}", escaped_motion_arm_ik2fk_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_arm_ik2fk_vmd_pattern, output_arm_ik2fk_vmd_path) is not None
    

def get_output_multi_split_vmd_path(base_file_path: str, pmx_path: str, output_multi_split_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_multi_split_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_multi_split_vmd_file_name, motion_multi_split_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_multi_split_vmd_path = os.path.join(motion_multi_split_vmd_dir_path, "{0}_{1}D_{2:%Y%m%d_%H%M%S}{3}".format(motion_multi_split_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_multi_split_vmd_output_path(output_multi_split_vmd_path, motion_multi_split_vmd_dir_path, motion_multi_split_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_multi_split_vmd_path, 'w')
            os.remove(new_output_multi_split_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_multi_split_vmd_path

    return output_multi_split_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_multi_split_vmd_output_path(output_multi_split_vmd_path: str, motion_multi_split_vmd_dir_path: str, motion_multi_split_vmd_file_name: str, \
                                        motion_multi_split_vmd_ext: str, rep_pmx_file_name: str):
    if not output_multi_split_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_multi_split_vmd_file_name = escape_filepath(os.path.join(motion_multi_split_vmd_dir_path, motion_multi_split_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_multi_split_vmd_ext = escape_filepath(motion_multi_split_vmd_ext)

    new_output_multi_split_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_multi_split_vmd_file_name, \
                                                    escaped_rep_pmx_file_name, r"D_\d{8}_\d{6}", escaped_motion_multi_split_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_multi_split_vmd_pattern, output_multi_split_vmd_path) is not None
    

# 分割ボーン置換組み合わせファイル
def get_output_split_bone_path(base_file_path: str, pmx_path: str):
    # モーションVMDパスの拡張子リスト
    if os.path.exists(base_file_path):
        file_path_list = [base_file_path]
    else:
        file_path_list = [p for p in glob.glob(base_file_path) if os.path.isfile(p)]

    if len(file_path_list) == 0 or (len(file_path_list) > 0 and not os.path.exists(file_path_list[0])) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_vmd_dir_path = get_dir_path(file_path_list[0])
    # モーションVMDファイル名・拡張子
    motion_vmd_file_name, motion_vmd_ext = os.path.splitext(os.path.basename(file_path_list[0]))
    # 変換先モデルファイル名・拡張子
    pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_bone_path = os.path.join(motion_vmd_dir_path, "{0}_{1}{2}".format(motion_vmd_file_name, pmx_file_name, ".csv"))

    return new_output_bone_path
    

# 接地設定ファイル
def get_output_leg_ground_path(base_file_path: str, pmx_path: str):
    # モーションVMDパスの拡張子リスト
    if os.path.exists(base_file_path):
        file_path_list = [base_file_path]
    else:
        file_path_list = [p for p in glob.glob(base_file_path) if os.path.isfile(p)]

    if len(file_path_list) == 0 or (len(file_path_list) > 0 and not os.path.exists(file_path_list[0])) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_vmd_dir_path = get_dir_path(file_path_list[0])
    # モーションVMDファイル名・拡張子
    motion_vmd_file_name, motion_vmd_ext = os.path.splitext(os.path.basename(file_path_list[0]))
    # 変換先モデルファイル名・拡張子
    pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_bone_path = os.path.join(motion_vmd_dir_path, "{0}_{1}{2}".format(motion_vmd_file_name, pmx_file_name, ".csv"))

    return new_output_bone_path


def get_output_multi_join_vmd_path(base_file_path: str, pmx_path: str, output_multi_join_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_multi_join_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_multi_join_vmd_file_name, motion_multi_join_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_multi_join_vmd_path = os.path.join(motion_multi_join_vmd_dir_path, "{0}_{1}J_{2:%Y%m%d_%H%M%S}{3}".format(motion_multi_join_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_multi_join_vmd_output_path(output_multi_join_vmd_path, motion_multi_join_vmd_dir_path, motion_multi_join_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_multi_join_vmd_path, 'w')
            os.remove(new_output_multi_join_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_multi_join_vmd_path

    return output_multi_join_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_multi_join_vmd_output_path(output_multi_join_vmd_path: str, motion_multi_join_vmd_dir_path: str, \
                                       motion_multi_join_vmd_file_name: str, motion_multi_join_vmd_ext: str, rep_pmx_file_name: str):
    if not output_multi_join_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_multi_join_vmd_file_name = escape_filepath(os.path.join(motion_multi_join_vmd_dir_path, motion_multi_join_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_multi_join_vmd_ext = escape_filepath(motion_multi_join_vmd_ext)

    new_output_multi_join_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_multi_join_vmd_file_name, \
                                                   escaped_rep_pmx_file_name, r"J_\d{8}_\d{6}", escaped_motion_multi_join_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_multi_join_vmd_pattern, output_multi_join_vmd_path) is not None
    

# 統合ボーン置換組み合わせファイル
def get_output_join_bone_path(base_file_path: str, pmx_path: str):
    # モーションVMDパスの拡張子リスト
    if os.path.exists(base_file_path):
        file_path_list = [base_file_path]
    else:
        file_path_list = [p for p in glob.glob(base_file_path) if os.path.isfile(p)]

    if len(file_path_list) == 0 or (len(file_path_list) > 0 and not os.path.exists(file_path_list[0])) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_vmd_dir_path = get_dir_path(file_path_list[0])
    # モーションVMDファイル名・拡張子
    motion_vmd_file_name, motion_vmd_ext = os.path.splitext(os.path.basename(file_path_list[0]))
    # 変換先モデルファイル名・拡張子
    pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_bone_path = os.path.join(motion_vmd_dir_path, "{0}_{1}{2}".format(motion_vmd_file_name, pmx_file_name, ".csv"))

    return new_output_bone_path
    

# 全親移植VMD出力ファイルパス生成
# base_file_path: モーションVMDパス
# pmx_path: 変換先モデルPMXパス
# output_leg_fk2ik_vmd_path: 出力ファイルパス
def get_output_leg_fk2ik_vmd_path(base_file_path: str, pmx_path: str, output_leg_fk2ik_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_leg_fk2ik_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_leg_fk2ik_vmd_file_name, motion_leg_fk2ik_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_leg_fk2ik_vmd_path = os.path.join(motion_leg_fk2ik_vmd_dir_path, "{0}_{1}L_{2:%Y%m%d_%H%M%S}{3}".format(motion_leg_fk2ik_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_leg_fk2ik_vmd_output_path(output_leg_fk2ik_vmd_path, motion_leg_fk2ik_vmd_dir_path, motion_leg_fk2ik_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_leg_fk2ik_vmd_path, 'w')
            os.remove(new_output_leg_fk2ik_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_leg_fk2ik_vmd_path

    return output_leg_fk2ik_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_leg_fk2ik_vmd_output_path(output_leg_fk2ik_vmd_path: str, motion_leg_fk2ik_vmd_dir_path: str, motion_leg_fk2ik_vmd_file_name: str, motion_leg_fk2ik_vmd_ext: str, rep_pmx_file_name: str):
    if not output_leg_fk2ik_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_leg_fk2ik_vmd_file_name = escape_filepath(os.path.join(motion_leg_fk2ik_vmd_dir_path, motion_leg_fk2ik_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_leg_fk2ik_vmd_ext = escape_filepath(motion_leg_fk2ik_vmd_ext)

    new_output_leg_fk2ik_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_leg_fk2ik_vmd_file_name, \
                                                  escaped_rep_pmx_file_name, r"L_\d{8}_\d{6}", escaped_motion_leg_fk2ik_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_leg_fk2ik_vmd_pattern, output_leg_fk2ik_vmd_path) is not None


# スムージングVMD出力ファイルパス生成
# base_file_path: モーションスムージングVMDパス
# pmx_path: 変換先モデルPMXパス
# output_smooth_vmd_path: 出力ファイルパス
def get_output_smooth_vmd_path(base_file_path: str, pmx_path: str, output_smooth_vmd_path: str, interpolation: int, loop_cnt: int, is_force=False):
    # モーションスムージングVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションスムージングVMDディレクトリパス
    motion_smooth_vmd_dir_path = get_dir_path(base_file_path)
    # モーションスムージングVMDファイル名・拡張子
    motion_smooth_vmd_file_name, motion_smooth_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 補間方法
    suffix = "{0}{1}{2}".format(
        ("F" if interpolation == 0 else ""),
        ("C" if interpolation == 1 else ""),
        ("V" if interpolation == 2 else ""),
    )

    if len(suffix) > 0:
        suffix = "_{0}".format(suffix)
    
    suffix = "{0}_L{1}".format(suffix, loop_cnt)

    # 出力ファイルパス生成
    new_output_smooth_vmd_path = os.path.join(motion_smooth_vmd_dir_path, "{0}_{1}{2}_{3:%Y%m%d_%H%M%S}{4}".format(motion_smooth_vmd_file_name, rep_pmx_file_name, suffix, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_smooth_vmd_output_path(output_smooth_vmd_path, motion_smooth_vmd_dir_path, motion_smooth_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_smooth_vmd_path, 'w')
            os.remove(new_output_smooth_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_smooth_vmd_path

    return output_smooth_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_smooth_vmd_output_path(output_smooth_vmd_path: str, motion_smooth_vmd_dir_path: str, motion_smooth_vmd_file_name: str, motion_smooth_vmd_ext: str, rep_pmx_file_name: str):
    if not output_smooth_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_smooth_vmd_file_name = escape_filepath(os.path.join(motion_smooth_vmd_dir_path, motion_smooth_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_smooth_vmd_ext = escape_filepath(motion_smooth_vmd_ext)

    new_output_smooth_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_smooth_vmd_file_name, \
                                               escaped_rep_pmx_file_name, r"_?\w*_L\d+_\d{8}_\d{6}", escaped_motion_smooth_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_smooth_vmd_pattern, output_smooth_vmd_path) is not None
    

# 捩りOFFVMD出力ファイルパス生成
# base_file_path: モーションVMDパス
# pmx_path: 変換先モデルPMXパス
# output_arm_twist_off_vmd_path: 出力ファイルパス
def get_output_arm_twist_off_vmd_path(base_file_path: str, pmx_path: str, output_arm_twist_off_vmd_path: str, is_force=False):
    # モーションVMDパスの拡張子リスト
    if not os.path.exists(base_file_path) or not os.path.exists(pmx_path):
        return ""

    # モーションVMDディレクトリパス
    motion_arm_twist_off_vmd_dir_path = get_dir_path(base_file_path)
    # モーションVMDファイル名・拡張子
    motion_arm_twist_off_vmd_file_name, motion_arm_twist_off_vmd_ext = os.path.splitext(os.path.basename(base_file_path))
    # 変換先モデルファイル名・拡張子
    rep_pmx_file_name, _ = os.path.splitext(os.path.basename(pmx_path))

    # 出力ファイルパス生成
    new_output_arm_twist_off_vmd_path = os.path.join(motion_arm_twist_off_vmd_dir_path, "{0}_{1}T_{2:%Y%m%d_%H%M%S}{3}".format(motion_arm_twist_off_vmd_file_name, rep_pmx_file_name, datetime.now(), ".vmd"))

    # ファイルパス自体が変更されたか、自動生成ルールに則っている場合、ファイルパス変更
    if is_force or is_auto_arm_twist_off_vmd_output_path(output_arm_twist_off_vmd_path, motion_arm_twist_off_vmd_dir_path, motion_arm_twist_off_vmd_file_name, ".vmd", rep_pmx_file_name):

        try:
            open(new_output_arm_twist_off_vmd_path, 'w')
            os.remove(new_output_arm_twist_off_vmd_path)
        except Exception:
            logger.warning("出力ファイルパスの生成に失敗しました。以下の原因が考えられます。\n" \
                           + "・ファイルパスが255文字を超えている\n" \
                           + "・ファイルパスに使えない文字列が含まれている（例) \\　/　:　*　?　\"　<　>　|）" \
                           + "・出力ファイルパスの親フォルダに書き込み権限がない" \
                           + "・出力ファイルパスに書き込み権限がない")

        return new_output_arm_twist_off_vmd_path

    return output_arm_twist_off_vmd_path


# 自動生成ルールに則ったパスか
def is_auto_arm_twist_off_vmd_output_path(output_arm_twist_off_vmd_path: str, motion_arm_twist_off_vmd_dir_path: str, motion_arm_twist_off_vmd_file_name: str, motion_arm_twist_off_vmd_ext: str, rep_pmx_file_name: str):
    if not output_arm_twist_off_vmd_path:
        # 出力パスがない場合、置き換え対象
        return True

    # 新しく設定しようとしている出力ファイルパスの正規表現
    escaped_motion_arm_twist_off_vmd_file_name = escape_filepath(os.path.join(motion_arm_twist_off_vmd_dir_path, motion_arm_twist_off_vmd_file_name))
    escaped_rep_pmx_file_name = escape_filepath(rep_pmx_file_name)
    escaped_motion_arm_twist_off_vmd_ext = escape_filepath(motion_arm_twist_off_vmd_ext)

    new_output_arm_twist_off_vmd_pattern = re.compile(r'^%s_%s%s%s$' % (escaped_motion_arm_twist_off_vmd_file_name, \
                                               escaped_rep_pmx_file_name, r"T_\d{8}_\d{6}", escaped_motion_arm_twist_off_vmd_ext))
    
    # 自動生成ルールに則ったファイルパスである場合、合致あり
    return re.match(new_output_arm_twist_off_vmd_pattern, output_arm_twist_off_vmd_path) is not None
    

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
