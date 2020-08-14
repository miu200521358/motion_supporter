# -*- coding: utf-8 -*-
#
import math
import numpy as np
import logging
import os
import traceback
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor

from module.MOptions import MMultiSplitOptions, MOptionsDataSet
from mmd.PmxData import PmxModel # noqa
from mmd.VmdData import VmdMotion, VmdBoneFrame, VmdCameraFrame, VmdInfoIk, VmdLightFrame, VmdMorphFrame, VmdShadowFrame, VmdShowIkFrame # noqa
from mmd.VmdWriter import VmdWriter
from module.MMath import MRect, MVector3D, MVector4D, MQuaternion, MMatrix4x4 # noqa
from utils import MUtils, MServiceUtils, MBezierUtils # noqa
from utils.MLogger import MLogger # noqa
from utils.MException import SizingException

logger = MLogger(__name__, level=1)


class ConvertMultiSplitService():
    def __init__(self, options: MMultiSplitOptions):
        self.options = options

    def execute(self):
        logging.basicConfig(level=self.options.logging_level, format="%(message)s [%(module_name)s]")

        try:
            service_data_txt = "多段分割処理実行\n------------------------\nexeバージョン: {version_name}\n".format(version_name=self.options.version_name) \

            service_data_txt = "{service_data_txt}　VMD: {vmd}\n".format(service_data_txt=service_data_txt,
                                    vmd=os.path.basename(self.options.motion.path)) # noqa
            service_data_txt = "{service_data_txt}　モデル: {model}({model_name})\n".format(service_data_txt=service_data_txt,
                                    model=os.path.basename(self.options.motion.path), model_name=self.options.model.name) # noqa
            service_data_txt = "{service_data_txt}　対象ボーン: {target_bones}\n".format(service_data_txt=service_data_txt,
                                    target_bones=",".join(self.options.target_bones)) # noqa

            # 処理に成功しているか
            result = self.convert_multi_split()

            # 最後に出力
            VmdWriter(MOptionsDataSet(self.options.motion, None, self.options.model, self.options.output_path, False, False, [], None, 0, [])).write()

            logger.info("出力終了: %s", os.path.basename(self.options.output_path), decoration=MLogger.DECORATION_BOX, title="成功")

            return result
        except SizingException as se:
            logger.error("多段分割処理が処理できないデータで終了しました。\n\n%s", se.message, decoration=MLogger.DECORATION_BOX)
        except Exception:
            logger.critical("多段分割処理が意図せぬエラーで終了しました。\n\n%s", traceback.format_exc(), decoration=MLogger.DECORATION_BOX)
        finally:
            logging.shutdown()

    # 多段分割処理実行
    def convert_multi_split(self):
        logger.info("多段分割", decoration=MLogger.DECORATION_LINE)

        motion = self.options.motion
        model = self.options.model

        for bone_name in self.options.target_bones:
            if bone_name not in model.bones or bone_name not in motion.bones:
                continue

            fnos = motion.get_bone_fnos(bone_name)
            # ローカルX軸
            local_x_axis = model.get_local_x_axis(bone_name)
            prev_sep_fno = 0

            # 事前に細分化
            self.prepare_split_stance(motion, bone_name)
            logger.info("-- 準備完了【%s】", bone_name)

            for fno in fnos:
                bf = motion.bones[bone_name][fno]

                if model.bones[bone_name].getRotatable():
                    # 回転を分ける
                    x_qq, y_qq, z_qq, _ = MServiceUtils.separate_local_qq(fno, bone_name, bf.rotation, local_x_axis)

                    rx_bf = VmdBoneFrame(fno)
                    rx_bf.set_name("{0}RX".format(bf.name))
                    rx_bf.rotation = x_qq
                    motion.regist_bf(rx_bf, rx_bf.name, fno)

                    ry_bf = VmdBoneFrame(fno)
                    ry_bf.set_name("{0}RY".format(bf.name))
                    ry_bf.rotation = y_qq
                    motion.regist_bf(ry_bf, ry_bf.name, fno)

                    rz_bf = VmdBoneFrame(fno)
                    rz_bf.set_name("{0}RZ".format(bf.name))
                    rz_bf.rotation = z_qq
                    motion.regist_bf(rz_bf, rz_bf.name, fno)
                
                if model.bones[bone_name].getTranslatable():
                    # 移動を分ける
                    mx_bf = VmdBoneFrame(fno)
                    mx_bf.set_name("{0}MX".format(bf.name))
                    mx_bf.position.setX(bf.position.x())
                    motion.regist_bf(mx_bf, mx_bf.name, fno)

                    my_bf = VmdBoneFrame(fno)
                    my_bf.set_name("{0}MY".format(bf.name))
                    my_bf.position.setY(bf.position.y())
                    motion.regist_bf(my_bf, my_bf.name, fno)

                    mz_bf = VmdBoneFrame(fno)
                    mz_bf.set_name("{0}MZ".format(bf.name))
                    mz_bf.position.setZ(bf.position.z())
                    motion.regist_bf(mz_bf, mz_bf.name, fno)

                if fno // 2000 > prev_sep_fno and fnos[-1] > 0:
                    logger.info("-- %sフレーム目:終了(%s％)【%s】", fno, round((fno / fnos[-1]) * 100, 3), bone_name)
                    prev_sep_fno = fno // 2000

            # 元のボーン削除
            del motion.bones[bone_name]

    # スタンス用細分化
    def prepare_split_stance(self, motion: VmdMotion, target_bone_name: str):
        fnos = motion.get_bone_fnos(target_bone_name)

        for fidx, fno in enumerate(fnos):
            if fidx == 0:
                continue

            prev_bf = motion.bones[target_bone_name][fnos[fidx - 1]]
            bf = motion.bones[target_bone_name][fno]
            diff_degree = abs(prev_bf.rotation.toDegree() - bf.rotation.toDegree())

            if diff_degree >= 150:
                # 回転量が約150度以上の場合、半分に分割しておく
                half_fno = prev_bf.fno + round((bf.fno - prev_bf.fno) / 2)

                if prev_bf.fno < half_fno < bf.fno:
                    # キーが追加できる状態であれば、追加
                    half_bf = motion.calc_bf(target_bone_name, half_fno)
                    motion.regist_bf(half_bf, target_bone_name, half_fno)


