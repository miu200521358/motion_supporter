# -*- coding: utf-8 -*-
#
import math
import numpy as np
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MMorphConditionOptions, MOptionsDataSet
from mmd.PmxData import PmxModel, Bone  # noqa
from mmd.VmdData import (
    VmdMotion,
    VmdBoneFrame,
    VmdCameraFrame,
    VmdInfoIk,
    VmdLightFrame,
    VmdMorphFrame,
    VmdShadowFrame,
    VmdShowIkFrame,
)  # noqa
from mmd.VmdWriter import VmdWriter
from module.MParams import BoneLinks  # noqa
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4  # noqa
from utils import MServiceUtils, MBezierUtils  # noqa
from utils.MLogger import MLogger  # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


class ConvertMorphConditionService:
    def __init__(self, options: MMorphConditionOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "モーフ条件調整変換処理実行\n------------------------\nexeバージョン: {version_name}\n".format(
                version_name=self.options.version_name
            )
            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(
                service_data_txt=service_data_txt, vmd=os.path.basename(self.options.motion.path)
            )  # noqa

            selections = [
                "　　【{0}】が【{1}{2}】だったら【{3}】倍にする".format(morph_set[0], morph_set[1], morph_set[2], morph_set[3])
                for morph_set in self.options.target_morphs
            ]

            service_data_txt = "{service_data_txt}　モーフ条件調整: \n{target_morphs}".format(
                service_data_txt=service_data_txt, target_morphs="\n".join(selections)
            )  # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_morph_condition()

            model = PmxModel()
            model.name = "モーフ条件調整モデル"

            # 最後に出力
            VmdWriter(
                MOptionsDataSet(
                    self.options.motion,
                    None,
                    model,
                    self.options.output_path,
                    False,
                    False,
                    [],
                    None,
                    0,
                    [],
                )
            ).write()

            logger.info(
                "出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功"
            )

            return result
        except SizingException as se:
            logger.error("モーフ条件調整変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical(
                "モーフ条件調整変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX
            )
        finally:
            logging.shutdown()

    # モーフ条件調整変換処理実行
    def convert_morph_condition(self):
        futures = []

        with ThreadPoolExecutor(
            thread_name_prefix="morph_condition", max_workers=self.options.max_workers
        ) as executor:
            for target_morph in self.options.target_morphs:
                if target_morph[0] in self.options.motion.morphs:
                    futures.append(executor.submit(self.convert_target_morph_condition, target_morph))
                else:
                    logger.warning(
                        "モーションに存在しないモーフ名（%s）が条件になっているため、処理をスキップします", target_morph[0], decoration=MLogger.DECORATION_BOX
                    )

        concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        for f in futures:
            if not f.result():
                return False

        return True

    # 1つのボーンに対するモーフ条件調整変換処理
    def convert_target_morph_condition(self, target_morph: list):
        org_morph_name, condition_value, condition_name, ratio = target_morph

        motion = self.options.motion

        prev_sep_fno = 0
        fnos = list(motion.morphs[org_morph_name].keys())
        for fno, morph in motion.morphs[org_morph_name].items():
            condition_result = False
            if condition_name == "より大きい(＞)":
                condition_result = bool(np.all(np.greater(morph.ratio, condition_value)))
            elif condition_name == "以上(≧)":
                condition_result = bool(np.all(np.greater_equal(morph.ratio, condition_value)))
            elif condition_name == "等しい(＝)":
                # 厳密にイコールだと誤差が出る可能性があるので、クローズで比較する
                condition_result = bool(np.all(np.isclose(morph.ratio, condition_value)))
            elif condition_name == "以下(≦)":
                condition_result = bool(np.all(np.less_equal(morph.ratio, condition_value)))
            elif condition_name == "より小さい(＜)":
                condition_result = bool(np.all(np.less(morph.ratio, condition_value)))

            if condition_result:
                logger.info(
                    "-- モーフ条件調整:【%s: %sF】【%s x %s → %s】",
                    org_morph_name,
                    fno,
                    round(morph.ratio, 3),
                    ratio,
                    round(morph.ratio * ratio, 3),
                )
                morph.ratio *= ratio

            if fno // 500 > prev_sep_fno and fno > 0:
                logger.count(f"【モーフ条件調整 - {org_morph_name}】", fno, fnos)
                prev_sep_fno = fno // 500

        logger.info("-- モーフ条件調整:終了【%s】", org_morph_name)

        # bone_name = ik_bone.name

        # logger.info("-- モーフ条件調整変換準備:開始【%s】", bone_name)

        # org_motion = motion.copy()

        # # モデルのIKボーンのリンク
        # target_links = ik_model.create_link_2_top_one(bone_name, is_defined=False)

        # arm_bone_name = "{0}腕".format(bone_name[0])

        # # モデルの人差し指先ボーンのリンク
        # wrist_bone_name = "{0}手首".format(bone_name[0])
        # wrist_twist_bone_name = "{0}手捩".format(bone_name[0])

        # # モデルのIKリンク
        # if not (
        #     ik_bone.ik.target_index in ik_model.bone_indexes
        #     and ik_model.bone_indexes[ik_bone.ik.target_index] in ik_model.morphs
        # ):
        #     raise SizingException("{0} のTargetが有効なINDEXではありません。PMXの構造を確認してください。".format(bone_name))

        # # IKエフェクタ
        # effector_bone_name = ik_model.bone_indexes[ik_bone.ik.target_index]
        # effector_links = ik_model.create_link_2_top_one(effector_bone_name, is_defined=False)
        # ik_links = BoneLinks()

        # # 末端にエフェクタ
        # effector_bone = ik_model.morphs[effector_bone_name].copy()
        # effector_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)
        # ik_links.append(effector_bone)

        # target_morphs = [bone_name]
        # twist_morphs = []

        # # 回転移管先ボーン(手首)
        # transferee_bone = self.get_transferee_bone(ik_bone, effector_bone)
        # # 移管先までのリンク
        # transferee_links = ik_model.create_link_2_top_one(transferee_bone.name, is_defined=False)

        # for ik_link in ik_bone.ik.link:
        #     # IKリンクを末端から順に追加
        #     if not (
        #         ik_link.bone_index in ik_model.bone_indexes
        #         and ik_model.bone_indexes[ik_link.bone_index] in ik_model.morphs
        #     ):
        #         raise SizingException("{0} のLinkに無効なINDEXが含まれています。PMXの構造を確認してください。".format(bone_name))

        #     link_bone = ik_model.morphs[ik_model.bone_indexes[ik_link.bone_index]].copy()

        #     if link_bone.fixed_axis != MVector3D():
        #         # 捩り系として保持
        #         twist_morphs.append(link_bone.name)
        #         # 捩り系は無視
        #         continue

        #     # 単位角
        #     link_bone.degree_limit = math.degrees(ik_bone.ik.limit_radian)

        #     # # 角度制限
        #     # if ik_link.limit_angle == 1:
        #     #     link_bone.limit_min = ik_link.limit_min
        #     #     link_bone.limit_max = ik_link.limit_max

        #     ik_links.append(link_bone)
        #     target_morphs.append(link_bone.name)

        # # 精度優先で全打ち
        # fnos = motion.get_bone_fnos(*(list(ik_links.all().keys()) + target_morphs + twist_morphs))
        # fnos = [f for f in range(fnos[-1] + 1)]

        # prev_sep_fno = 0
        # for fno in fnos:
        #     for link_name in list(ik_links.all().keys())[1:]:
        #         bf = motion.calc_bf(link_name, fno)

        #         if link_name == arm_bone_name:
        #             for twist_bone in twist_morphs:
        #                 # 腕は腕捩りの結果を加算する
        #                 twist_bf = motion.calc_bf(twist_bone, fno)
        #                 bf.rotation = bf.rotation * twist_bf.rotation

        #                 # 捩りボーンをクリアする
        #                 twist_bf.rotation = MQuaternion()
        #                 motion.regist_bf(twist_bf, twist_bone, fno)

        #         motion.regist_bf(bf, link_name, fno)

        #     # 手捩りボーンを手首に乗せる
        #     if wrist_twist_bone_name in motion.morphs:
        #         wrist_twist_bf = motion.calc_bf(wrist_twist_bone_name, fno)
        #         wrist_bf = motion.calc_bf(wrist_bone_name, fno)
        #         wrist_bf.rotation = wrist_twist_bf.rotation * wrist_bf.rotation

        #         motion.regist_bf(wrist_bf, wrist_bf.name, fno)

        #         wrist_twist_bf.rotation = MQuaternion()
        #         motion.regist_bf(wrist_twist_bf, wrist_twist_bf.name, fno)

        #     # 腕IKも設定
        #     bf = motion.calc_bf(bone_name, fno)
        #     motion.regist_bf(bf, bone_name, fno)

        #     if fno // 500 > prev_sep_fno and fnos[-1] > 0:
        #         logger.count(f"【キーフレ追加 - {bone_name}】", fno, fnos)
        #         prev_sep_fno = fno // 500

        # logger.info("-- モーフ条件調整変換準備:終了【%s】", bone_name)

        # fk_motion = motion.copy()

        # # IKボーンを削除
        # if bone_name in motion.morphs:
        #     del motion.morphs[bone_name]

        # # if bone_name in fk_motion.morphs:
        # #     del fk_motion.morphs[bone_name]

        # # 捩りボーンを削除
        # for twist_bone in twist_morphs:
        #     if twist_bone in fk_motion.morphs:
        #         del fk_motion.morphs[twist_bone]

        #     if twist_bone in motion.morphs:
        #         del motion.morphs[twist_bone]

        # if wrist_twist_bone_name in fk_motion.morphs:
        #     del fk_motion.morphs[wrist_twist_bone_name]

        # if wrist_twist_bone_name in motion.morphs:
        #     del motion.morphs[wrist_twist_bone_name]

        # prev_sep_fno = 0
        # for fidx, fno in enumerate(fnos):
        #     # グローバル位置計算(元モーションの位置)
        #     target_ik_global_3ds = MServiceUtils.calc_global_pos(ik_model, target_links, org_motion, fno)
        #     target_effector_pos = target_ik_global_3ds[bone_name]

        #     # IK計算実行
        #     MServiceUtils.calc_IK(
        #         ik_model, effector_links, fk_motion, fno, target_effector_pos, ik_links, max_count=10
        #     )

        #     # 現在のエフェクタ位置
        #     now_global_3ds = MServiceUtils.calc_global_pos(ik_model, transferee_links, fk_motion, fno)
        #     now_effector_pos = now_global_3ds[transferee_bone.name]
        #     logger.debug(
        #         "(%s) target_effector_pos: %s [%s] ------------------", fno, bone_name, target_effector_pos.to_log()
        #     )
        #     logger.debug("(%s) now_effector_pos: %s [%s]", fno, bone_name, now_effector_pos.to_log())

        #     for link_name in list(ik_links.all().keys())[1:]:
        #         fk_bf = fk_motion.calc_bf(link_name, fno)
        #         logger.debug("確定bf(%s): %s [%s]", fno, link_name, fk_bf.rotation.toEulerAngles4MMD().to_log())

        #         # 確定した角度をそのまま登録
        #         bf = motion.calc_bf(link_name, fno)
        #         bf.rotation = fk_bf.rotation.copy()
        #         motion.regist_bf(bf, link_name, fno)

        #     if fno // 500 > prev_sep_fno:
        #         logger.count("【モーフ条件調整変換 - {0}】".format(bone_name), fno, fnos)
        #         prev_sep_fno = fno // 500

        # # 終わったら手首FK再計算
        # self.recalc_wrist_fk(ik_bone, target_links, effector_links, fnos, org_motion, effector_bone)

        return True
