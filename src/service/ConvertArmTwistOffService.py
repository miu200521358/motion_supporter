# -*- coding: utf-8 -*-
#
import math
import numpy as np
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MArmTwistOffOptions, MOptionsDataSet
from mmd.PmxData import PmxModel, Bone # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MParams import BoneLinks # noqa
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException, MKilledException

logger = MLogger(__name__, level=1)


RADIANS_01 = math.cos(math.radians(0.1))
RADIANS_05 = math.cos(math.radians(0.5))
RADIANS_1 = math.cos(math.radians(1))
RADIANS_2 = math.cos(math.radians(2))
RADIANS_5 = math.cos(math.radians(5))
RADIANS_8 = math.cos(math.radians(8))
RADIANS_12 = math.cos(math.radians(12))
RADIANS_15 = math.cos(math.radians(15))

class ConvertArmTwistOffService():
    def __init__(self, options: MArmTwistOffOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "捩りOFF変換処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　不要キー削除: {center_rotation}\n".format(service_data_txt=service_data_txt,
                                    center_rotation=self.options.remove_unnecessary_flg) # noqa

            logger.info(service_data_txt, decoration=MLogger.DECORATION_BOX)

            # 処理に成功しているか
            result = self.convert_twist_off()

            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.model, self.options.output_path, False, False, [], None, 0, [])).write()

            logger.info("出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功")

            return result
        except SizingException as se:
            logger.error("捩りOFF変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("捩りOFF変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 捩りOFF変換処理実行
    def convert_twist_off(self):
        futures = []

        with ThreadPoolExecutor(thread_name_prefix="twist_off", max_workers=self.options.max_workers) as executor:
            futures.append(executor.submit(self.convert_target_twist_off, "右"))
            futures.append(executor.submit(self.convert_target_twist_off, "左"))

        concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

        for f in futures:
            if not f.result():
                return False

        return True

    # 不要キー削除
    def remove_unnecessary_bf(self, bone_name: str):
        try:
            self.options.motion.remove_unnecessary_bf(0, bone_name, self.options.model.bones[bone_name].getRotatable(), \
                                                      self.options.model.bones[bone_name].getTranslatable())

            return True
        except MKilledException as ke:
            raise ke
        except SizingException as se:
            logger.error("捩りOFF変換処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
            return se
        except Exception as e:
            import traceback
            logger.critical("捩りOFF変換処理が意図せぬエラーで終了しました。\n\n%s", traceback.print_exc(), decoration=MLogger.DECORATION_BOX)
            raise e

    # 1つのボーンに対する捩りOFF変換処理
    def convert_target_twist_off(self, direction: str):
        motion = self.options.motion
        model = self.options.model

        bone_name = f"{direction}腕系"
        arm_bone_name = f"{direction}腕"
        arm_twist_bone_name = f"{direction}腕捩"
        elbow_bone_name = f"{direction}ひじ"
        wrist_twist_bone_name = f"{direction}手捩"
        wrist_bone_name = f"{direction}手首"
        finger_bone_name = f"{direction}人指先実体"
        finger2_bone_name = f"{direction}小指先実体"

        logger.info(f"-- 捩りOFF変換準備:開始【{bone_name}】")

        # モデルの手首までのボーンのリンク
        finger_links = model.create_link_2_top_one(finger_bone_name, is_defined=False)
        finger2_links = model.create_link_2_top_one(finger2_bone_name, is_defined=False)
        arm2wrist_links = finger_links.to_links(arm_bone_name)
        
        # 差異の大きい箇所にFKキーフレ追加
        fnos = motion.get_differ_fnos(0, list(arm2wrist_links.all().keys()), limit_degrees=20, limit_length=0.5)

        # 先に空のキーを登録しておく
        prev_sep_fno = 0
        for fno in fnos:
            for link_name in list(arm2wrist_links.all().keys()):
                if link_name in motion.bones:
                    bf = motion.calc_bf(link_name, fno)
                    motion.regist_bf(bf, link_name, fno)

            if fno // 500 > prev_sep_fno:
                logger.count(f"【キーフレ追加 - {bone_name}】", fno, fnos)
                prev_sep_fno = fno // 500

        logger.info("-- 捩りOFF変換準備:終了【%s】", bone_name)

        # 捩りありの状態で一旦保持
        org_motion = motion.copy()

        prev_sep_fno = 0
        for fno in fnos:
            # 腕に腕捩りの結果を加算
            arm_bf = motion.calc_bf(arm_bone_name, fno)
            arm_twist_bf = motion.calc_bf(arm_twist_bone_name, fno)

            arm_bf.rotation = arm_bf.rotation * arm_twist_bf.rotation
            arm_twist_bf.rotation = MQuaternion()

            motion.regist_bf(arm_bf, arm_bone_name, fno)
            motion.regist_bf(arm_twist_bf, arm_twist_bone_name, fno)

            # 手首に手首捩りの結果を加算
            wrist_bf = motion.calc_bf(wrist_bone_name, fno)
            wrist_twist_bf = motion.calc_bf(wrist_twist_bone_name, fno)

            # 手捩りの方が根元に近いので、先にかけ算
            wrist_bf.rotation = wrist_twist_bf.rotation * wrist_bf.rotation
            wrist_twist_bf.rotation = MQuaternion()

            motion.regist_bf(wrist_bf, wrist_bone_name, fno)
            motion.regist_bf(wrist_twist_bf, wrist_twist_bone_name, fno)


            if fno // 500 > prev_sep_fno:
                logger.count("【捩りOFF変換 - {0}】".format(bone_name), fno, fnos)
                prev_sep_fno = fno // 500
        
        # 腕捩ボーンを削除
        if arm_twist_bone_name in motion.bones:
            del motion.bones[arm_twist_bone_name]

        # 手捩ボーンを削除
        if wrist_twist_bone_name in motion.bones:
            del motion.bones[wrist_twist_bone_name]

        if self.options.remove_unnecessary_flg:
            futures = []

            with ThreadPoolExecutor(thread_name_prefix="remove", max_workers=self.options.max_workers) as executor:
                for bone_name in [f"{direction}腕", f"{direction}ひじ", f"{direction}手首"]:
                    futures.append(executor.submit(self.remove_unnecessary_bf, bone_name))

            concurrent.futures.wait(futures, timeout=None, return_when=concurrent.futures.FIRST_EXCEPTION)

            for f in futures:
                if not f.result():
                    return False
